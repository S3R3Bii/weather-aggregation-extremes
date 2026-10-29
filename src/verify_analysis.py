# Independent SQLite calendar, aggregation, run-island, order-statistic and bootstrap checks.
import argparse
import csv
import gzip
import json
import sqlite3
from datetime import datetime, timedelta
from fractions import Fraction
import numpy as np
from config import ROOT, DEVELOPMENT_YEARS, EVALUATION_YEARS, SEED


def read(name):
    with (ROOT / name).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def verify(which):
    years = DEVELOPMENT_YEARS if which == "development" else EVALUATION_YEARS
    stations = json.loads((ROOT / "data/stations.json").read_text())
    mapping = {r["usaf"] + "-" + r["wban"]: r["city"] for r in stations}
    actual = {}
    with gzip.open(
        ROOT / "data/source/temperature_slots.csv.gz",
        "rt",
        encoding="utf-8",
        newline="",
    ) as f:
        for r in csv.DictReader(f):
            if int(r["year"]) not in years:
                continue
            key = (r["station"], *(int(r[k]) for k in ["year", "month", "day", "hour"]))
            assert key not in actual
            value = int(r["temperature_tenths"])
            actual[key] = None if value == -9999 else value
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE grid(station TEXT,year INT,month INT,idx INT,temp INT)")
    for sid in mapping:
        for year in years:
            stamp = datetime(year, 1, 1)
            end = datetime(year + 1, 1, 1)
            batch = []
            idx = 0
            while stamp < end:
                value = actual.get((sid, year, stamp.month, stamp.day, stamp.hour))
                batch.append((sid, year, stamp.month, idx, value))
                idx += 1
                stamp += timedelta(hours=1)
            db.executemany("INSERT INTO grid VALUES(?,?,?,?,?)", batch)
    db.execute("CREATE INDEX panel ON grid(station,year,month)")
    monthly = read(f"results/{which}_monthly.csv")
    annual = read(f"results/{which}_annual.csv")
    phase_rows = read(f"results/{which}_phase.csv")
    month_lookup = {
        (r["station"], int(r["year"]), int(r["month"]), int(r["threshold_c"])): r
        for r in monthly
    }
    year_lookup = {
        (r["station"], int(r["year"]), int(r["threshold_c"])): r for r in annual
    }
    phase_lookup = {(r["station"], int(r["threshold_c"])): r for r in phase_rows}
    exact_checks = 0
    float_checks = 0
    computed_annual = {}
    computed_phase = {}

    def scalar(row, key, value):
        nonlocal exact_checks
        assert row[key] == str(value), (which, key, row[key], value)
        exact_checks += 1

    def fraction(row, key, value):
        nonlocal exact_checks, float_checks
        assert row[key + "_exact"] == ("NA" if value is None else str(value)), (
            which,
            key,
        )
        exact_checks += 1
        if value is None:
            assert row[key] == "NA"
        else:
            assert abs(float(row[key]) - float(value)) <= 1e-12, (which, key, "float")
        float_checks += 1

    def rates(row, c):
        fraction(
            row,
            "precision",
            Fraction(c["tp"], c["tp"] + c["fp"]) if c["tp"] + c["fp"] else None,
        )
        fraction(
            row,
            "recall",
            Fraction(c["tp"], c["positive_slots"]) if c["positive_slots"] else None,
        )
        fraction(
            row,
            "hidden_positive_fraction",
            Fraction(c["fn"], c["positive_slots"]) if c["positive_slots"] else None,
        )

    def tail(sid, year=None):
        condition = "station=?" + (" AND year=?" if year is not None else "")
        params = (sid, year) if year is not None else (sid,)
        n, maximum = db.execute(
            "SELECT COUNT(temp),MAX(temp) FROM grid WHERE " + condition, params
        ).fetchone()
        result = {}
        for percent in [95, 99]:
            if n:
                offset = (n * percent - 1) // 100
                result["observed_p" + str(percent) + "_tenths_c"] = db.execute(
                    "SELECT temp FROM grid WHERE "
                    + condition
                    + " AND temp IS NOT NULL ORDER BY temp LIMIT 1 OFFSET ?",
                    (*params, offset),
                ).fetchone()[0]
            else:
                result["observed_p" + str(percent) + "_tenths_c"] = "NA"
        result["observed_max_tenths_c"] = maximum if n else "NA"
        return result

    count_fields = [
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
    for sid, city in sorted(mapping.items(), key=lambda v: v[1]):
        annual_tails = {y: tail(sid, y) for y in years}
        phase_tails = tail(sid)
        for threshold in [25, 30, 35]:
            for year in years:
                # Group SQL computes every monthly denominator and threshold class from the full grid.
                result = db.execute(
                    """SELECT month,COUNT(*),COUNT(temp),COALESCE(SUM(temp),0),
                    COALESCE(SUM(CASE WHEN temp>? THEN 1 ELSE 0 END),0)
                    FROM grid WHERE station=? AND year=? GROUP BY month ORDER BY month""",
                    (threshold * 10, sid, year),
                ).fetchall()
                expected_months = []
                for month, expected, n, total, e in result:
                    predicted = total > threshold * 10 * n if n else None
                    c = {
                        "expected_slots": expected,
                        "observed_slots": n,
                        "unknown_slots": expected - n,
                        "temperature_sum_tenths": total,
                        "positive_slots": e,
                        "positive_lower": e,
                        "positive_upper": e + expected - n,
                        "monthly_view_positive_slots": n if predicted else 0,
                        "tp": e if predicted else 0,
                        "fp": n - e if predicted else 0,
                        "fn": 0 if predicted else e,
                        "tn": 0 if predicted else n - e,
                    }
                    row = month_lookup[sid, year, month, threshold]
                    for key, value in {
                        "phase": which,
                        "city": city,
                        "station": sid,
                        "year": year,
                        "month": month,
                        "threshold_c": threshold,
                        **c,
                        "mean_classification": (
                            "UNDEFINED"
                            if predicted is None
                            else "POSITIVE" if predicted else "NONPOSITIVE"
                        ),
                    }.items():
                        scalar(row, key, value)
                    rates(row, c)
                    fraction(
                        row, "monthly_mean_c", Fraction(total, n * 10) if n else None
                    )
                    expected_months.append(c)
                c = {key: sum(v[key] for v in expected_months) for key in count_fields}
                # Independent run-length calculation uses SQL window islands, not a streaming run counter.
                for mode, expression in [
                    ("confirmed", "temp>?"),
                    ("possible", "temp>? OR temp IS NULL"),
                ]:
                    query = (
                        """WITH flags AS (SELECT idx,CASE WHEN ("""
                        + expression
                        + """) THEN 1 ELSE 0 END AS positive
                      FROM grid WHERE station=? AND year=?), islands AS (
                      SELECT idx,positive,SUM(CASE WHEN positive=0 THEN 1 ELSE 0 END) OVER(ORDER BY idx) AS island FROM flags)
                      SELECT COALESCE(MAX(n),0) FROM (SELECT COUNT(*) AS n FROM islands WHERE positive=1 GROUP BY island)"""
                    )
                    c["longest_" + mode + "_positive_slot_run"] = db.execute(
                        query, (threshold * 10, sid, year)
                    ).fetchone()[0]
                c.update(annual_tails[year])
                row = year_lookup[sid, year, threshold]
                for key, value in {
                    "phase": which,
                    "city": city,
                    "station": sid,
                    "year": year,
                    "threshold_c": threshold,
                    **c,
                }.items():
                    scalar(row, key, value)
                rates(row, c)
                computed_annual[city, year, threshold] = c
            c = {
                key: sum(computed_annual[city, y, threshold][key] for y in years)
                for key in count_fields
            }
            c.update(
                longest_confirmed_annual_slot_run=max(
                    computed_annual[city, y, threshold][
                        "longest_confirmed_positive_slot_run"
                    ]
                    for y in years
                ),
                longest_possible_annual_slot_run=max(
                    computed_annual[city, y, threshold][
                        "longest_possible_positive_slot_run"
                    ]
                    for y in years
                ),
                **phase_tails,
            )
            row = phase_lookup[sid, threshold]
            for key, value in {
                "phase": which,
                "city": city,
                "station": sid,
                "threshold_c": threshold,
                "years": len(years),
                **c,
            }.items():
                scalar(row, key, value)
            rates(row, c)
            for key, field in [
                ("mean_annual_positive_slots", "positive_slots"),
                ("mean_annual_hidden_positive_slots", "fn"),
                ("mean_annual_possible_positive_slots", "positive_upper"),
            ]:
                fraction(row, key, Fraction(c[field], len(years)))
            computed_phase[city, threshold] = c
    assert (
        len(monthly) == 8 * len(years) * 12 * 3
        and len(annual) == 8 * len(years) * 3
        and len(phase_rows) == 24
    )
    indices = read(f"results/{which}_bootstrap_indices.csv")
    draws = read(f"results/{which}_bootstrap_draws.csv")
    intervals = read(f"results/{which}_bootstrap_intervals.csv")
    assert len(indices) == 500 and len(draws) == 12000 and len(intervals) == 24
    expected_indices = np.random.default_rng(SEED).integers(
        0, len(years), size=(500, len(years))
    )
    for i, row in enumerate(indices):
        scalar(row, "draw", i)
        for j, k in enumerate(expected_indices[i]):
            scalar(row, "year_" + str(j), years[int(k)])
    computed_draws = {}
    for row in draws:
        city = row["city"]
        threshold = int(row["threshold_c"])
        i = int(row["draw"])
        selected = [int(indices[i]["year_" + str(j)]) for j in range(len(years))]
        a = Fraction(
            sum(
                computed_annual[city, y, threshold]["positive_slots"] for y in selected
            ),
            len(years),
        )
        b = Fraction(
            sum(computed_annual[city, y, threshold]["fn"] for y in selected), len(years)
        )
        scalar(row, "phase", which)
        fraction(row, "mean_annual_positive_slots", a)
        fraction(row, "mean_annual_hidden_positive_slots", b)
        key = city, threshold
        computed_draws.setdefault(key, {"positive": [], "hidden_positive": []})
        computed_draws[key]["positive"].append(a)
        computed_draws[key]["hidden_positive"].append(b)
    for row in intervals:
        key = row["city"], int(row["threshold_c"])
        scalar(row, "phase", which)
        scalar(row, "replicates", 500)
        scalar(row, "resampled_years", len(years))
        for name, values in computed_draws[key].items():
            ordered = sorted(values)
            fraction(row, name + "_q05", ordered[24])
            fraction(row, name + "_q95", ordered[474])
    cert = {
        "status": "PASS",
        "phase": which,
        "monthly_rows": len(monthly),
        "annual_rows": len(annual),
        "phase_rows": len(phase_rows),
        "bootstrap_draws": len(draws),
        "exact_scalar_checks": exact_checks,
        "reported_float_checks": float_checks,
        "methods": "Independent full UTC calendar; SQLite grouped integer sums, window-island run lengths and sorted order statistics; exact rational confusion/means; all shared year indices and every replicate/percentile reconstructed without production helpers",
        "limits": "Arithmetic scope only; no full Lite QC validation, continuous physical duration, product response, exchangeable-years proof or future-climate coverage",
    }
    (ROOT / f"results/{which.upper()}_INDEPENDENT_CHECK.json").write_text(
        json.dumps(cert, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(cert))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=["development", "evaluation"])
    a = p.parse_args()
    verify(a.phase)
