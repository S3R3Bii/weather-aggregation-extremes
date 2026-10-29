"""Exact retrospective aggregation, unknown-slot bounds and whole-year resampling."""

import argparse
import calendar
import csv
import gzip
import json
from datetime import datetime
from fractions import Fraction
import numpy as np
from config import (
    ROOT,
    DEVELOPMENT_YEARS,
    EVALUATION_YEARS,
    THRESHOLDS,
    SEED,
    REPLICATES,
)


def ratio(a, b):
    return Fraction(a, b) if b else None


def fractions(row, values):
    for key, value in values.items():
        row[key + "_exact"] = "NA" if value is None else str(value)
        row[key] = "NA" if value is None else format(float(value), ".17g")
    return row


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def confusion(slots, threshold):
    values = [int(v) for v in slots if v != -9999]
    n = len(values)
    total = sum(values)
    positive = sum(v > threshold * 10 for v in values)
    mean_positive = total > threshold * 10 * n if n else None
    tp = positive if mean_positive else 0
    fp = n - positive if mean_positive else 0
    fn = 0 if mean_positive else positive
    tn = 0 if mean_positive else n - positive
    assert tp + fp + fn + tn == n
    return {
        "expected_slots": len(slots),
        "observed_slots": n,
        "unknown_slots": len(slots) - n,
        "temperature_sum_tenths": total,
        "positive_slots": positive,
        "positive_lower": positive,
        "positive_upper": positive + len(slots) - n,
        "monthly_view_positive_slots": n if mean_positive else 0,
        "mean_classification": (
            "UNDEFINED"
            if mean_positive is None
            else "POSITIVE" if mean_positive else "NONPOSITIVE"
        ),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
    }


def run_bounds(slots, threshold):
    best_lower = best_upper = lower = upper = 0
    for v in slots:
        positive = v != -9999 and v > threshold * 10
        lower = lower + 1 if positive else 0
        upper = upper + 1 if positive or v == -9999 else 0
        best_lower = max(best_lower, lower)
        best_upper = max(best_upper, upper)
    return best_lower, best_upper


def quantile(values, percent):
    if not len(values):
        return "NA"
    ordered = sorted(int(v) for v in values)
    index = (percent * len(ordered) + 99) // 100 - 1
    return ordered[index]


def count_rates(row):
    return fractions(
        row,
        {
            "precision": ratio(row["tp"], row["tp"] + row["fp"]),
            "recall": ratio(row["tp"], row["tp"] + row["fn"]),
            "hidden_positive_fraction": ratio(row["fn"], row["positive_slots"]),
        },
    )


COUNT_FIELDS = [
    "expected_slots",
    "observed_slots",
    "unknown_slots",
    "temperature_sum_tenths",
    "positive_slots",
    "positive_lower",
    "positive_upper",
    "monthly_view_positive_slots",
    "tp",
    "fp",
    "fn",
    "tn",
]


def main(which):
    years = DEVELOPMENT_YEARS if which == "development" else EVALUATION_YEARS
    station_rows = json.loads((ROOT / "data/stations.json").read_text())
    station_map = {r["usaf"] + "-" + r["wban"]: r["city"] for r in station_rows}
    arrays = {
        (sid, y): np.full(
            (366 if calendar.isleap(y) else 365) * 24, -9999, dtype=np.int16
        )
        for sid in station_map
        for y in years
    }
    with gzip.open(
        ROOT / "data/source/temperature_slots.csv.gz",
        "rt",
        encoding="utf-8",
        newline="",
    ) as f:
        for r in csv.DictReader(f):
            y = int(r["year"])
            if y not in years:
                continue
            stamp = datetime(y, int(r["month"]), int(r["day"]), int(r["hour"]))
            index = int((stamp - datetime(y, 1, 1)).total_seconds() // 3600)
            arrays[r["station"], y][index] = int(r["temperature_tenths"])
    monthly = []
    annual = []
    phases = []
    for sid, city in sorted(station_map.items(), key=lambda item: item[1]):
        for y in years:
            slots = arrays[sid, y]
            valid = slots[slots != -9999]
            q95 = quantile(valid, 95)
            q99 = quantile(valid, 99)
            maximum = int(max(valid)) if len(valid) else "NA"
            for threshold in THRESHOLDS:
                current = []
                for month in range(1, 13):
                    begin = int(
                        (datetime(y, month, 1) - datetime(y, 1, 1)).total_seconds()
                        // 3600
                    )
                    end = begin + calendar.monthrange(y, month)[1] * 24
                    c = confusion(slots[begin:end], threshold)
                    row = count_rates(
                        {
                            "phase": which,
                            "city": city,
                            "station": sid,
                            "year": y,
                            "month": month,
                            "threshold_c": threshold,
                            **c,
                        }
                    )
                    fractions(
                        row,
                        {
                            "monthly_mean_c": ratio(
                                c["temperature_sum_tenths"], 10 * c["observed_slots"]
                            )
                        },
                    )
                    monthly.append(row)
                    current.append(c)
                sums = {k: sum(c[k] for c in current) for k in COUNT_FIELDS}
                lo, hi = run_bounds(slots, threshold)
                annual.append(
                    count_rates(
                        {
                            "phase": which,
                            "city": city,
                            "station": sid,
                            "year": y,
                            "threshold_c": threshold,
                            **sums,
                            "longest_confirmed_positive_slot_run": lo,
                            "longest_possible_positive_slot_run": hi,
                            "observed_p95_tenths_c": q95,
                            "observed_p99_tenths_c": q99,
                            "observed_max_tenths_c": maximum,
                        }
                    )
                )
        pooled = np.concatenate(
            [arrays[sid, y][arrays[sid, y] != -9999] for y in years]
        )
        for threshold in THRESHOLDS:
            selected = [
                r for r in annual if r["city"] == city and r["threshold_c"] == threshold
            ]
            sums = {k: sum(r[k] for r in selected) for k in COUNT_FIELDS}
            row = count_rates(
                {
                    "phase": which,
                    "city": city,
                    "station": sid,
                    "threshold_c": threshold,
                    "years": len(years),
                    **sums,
                    "longest_confirmed_annual_slot_run": max(
                        r["longest_confirmed_positive_slot_run"] for r in selected
                    ),
                    "longest_possible_annual_slot_run": max(
                        r["longest_possible_positive_slot_run"] for r in selected
                    ),
                    "observed_p95_tenths_c": quantile(pooled, 95),
                    "observed_p99_tenths_c": quantile(pooled, 99),
                    "observed_max_tenths_c": int(max(pooled)) if len(pooled) else "NA",
                }
            )
            fractions(
                row,
                {
                    "mean_annual_positive_slots": Fraction(
                        sums["positive_slots"], len(years)
                    ),
                    "mean_annual_hidden_positive_slots": Fraction(
                        sums["fn"], len(years)
                    ),
                    "mean_annual_possible_positive_slots": Fraction(
                        sums["positive_upper"], len(years)
                    ),
                },
            )
            phases.append(row)
    rng = np.random.default_rng(SEED)
    indices = rng.integers(0, len(years), size=(REPLICATES, len(years)))
    index_rows = [
        {"draw": i, **{f"year_{j}": years[int(k)] for j, k in enumerate(row)}}
        for i, row in enumerate(indices)
    ]
    draws = []
    intervals = []
    for phase_row in phases:
        city = phase_row["city"]
        threshold = phase_row["threshold_c"]
        lookup = {
            r["year"]: r
            for r in annual
            if r["city"] == city and r["threshold_c"] == threshold
        }
        pos = []
        hidden = []
        for i, index in enumerate(indices):
            a = Fraction(
                sum(lookup[years[int(k)]]["positive_slots"] for k in index), len(years)
            )
            b = Fraction(sum(lookup[years[int(k)]]["fn"] for k in index), len(years))
            pos.append(a)
            hidden.append(b)
            draws.append(
                fractions(
                    {"phase": which, "city": city, "threshold_c": threshold, "draw": i},
                    {
                        "mean_annual_positive_slots": a,
                        "mean_annual_hidden_positive_slots": b,
                    },
                )
            )
        row = {
            "phase": which,
            "city": city,
            "threshold_c": threshold,
            "replicates": REPLICATES,
            "resampled_years": len(years),
        }
        for name, values in [("positive", pos), ("hidden_positive", hidden)]:
            ordered = sorted(values)
            low = ordered[(5 * REPLICATES + 99) // 100 - 1]
            high = ordered[(95 * REPLICATES + 99) // 100 - 1]
            fractions(row, {name + "_q05": low, name + "_q95": high})
        intervals.append(row)
    for name, rows in [
        ("monthly", monthly),
        ("annual", annual),
        ("phase", phases),
        ("bootstrap_indices", index_rows),
        ("bootstrap_draws", draws),
        ("bootstrap_intervals", intervals),
    ]:
        write_csv(ROOT / f"results/{which}_{name}.csv", rows)
    cert = {
        "status": "COMPUTED_PENDING_INDEPENDENT_CHECK",
        "phase": which,
        "monthly_rows": len(monthly),
        "annual_rows": len(annual),
        "phase_rows": len(phases),
        "bootstrap_draw_rows": len(draws),
        "bootstrap_index_rows": len(index_rows),
        "seed": SEED,
        "replicates": REPLICATES,
        "scope": "Exact reported-slot aggregation; no continuous duration, product condition, forecast or future-climate claim",
    }
    (ROOT / f"results/{which.upper()}_CHECK.json").write_text(
        json.dumps(cert, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(cert))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=["development", "evaluation"])
    a = p.parse_args()
    main(a.phase)
