"""Complete calendar/source accounting; thresholds and held analytic metrics are not computed."""

import csv, gzip, hashlib, json, calendar
from collections import Counter
from datetime import datetime
from config import ROOT, YEARS


def load_source():
    m = json.loads((ROOT / "data/source/manifest.json").read_text())
    path = ROOT / m["public_file"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == m["public_sha256"]
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        return m, list(csv.DictReader(f))


def main():
    m, rows = load_source()
    seen = set()
    counts = Counter()
    files = Counter()
    stations = {
        r["usaf"] + "-" + r["wban"]: r
        for r in json.loads((ROOT / "data/stations.json").read_text())
    }
    objects = {r["file"]: r for r in m["objects"]}
    assert len(objects) == 120 and len(stations) == 8
    for r in rows:
        sid = r["station"]
        year = int(r["year"])
        stamp = datetime(year, int(r["month"]), int(r["day"]), int(r["hour"]))
        key = sid, stamp
        assert sid in stations and year in YEARS and key not in seen
        seen.add(key)
        t = int(r["temperature_tenths"])
        assert t == -9999 or -1000 <= t <= 700
        obj = objects[r["source_file"]]
        assert (
            obj["station"] == sid
            and obj["year"] == year
            and 1 <= int(r["source_line"]) <= obj["source_rows"]
        )
        files[r["source_file"]] += 1
        counts[sid, year, "rows"] += 1
        counts[sid, year, "missing"] += t == -9999
    assert len(rows) == m["source_rows"] and all(
        files[k] == v["source_rows"] for k, v in objects.items()
    )
    coverage = []
    for sid, station in sorted(stations.items()):
        for year in YEARS:
            expected = (366 if calendar.isleap(year) else 365) * 24
            present = counts[sid, year, "rows"]
            missing = counts[sid, year, "missing"]
            assert present <= expected
            coverage.append(
                {
                    "city": station["city"],
                    "station": sid,
                    "year": year,
                    "expected_utc_slots": expected,
                    "source_rows": present,
                    "explicit_missing_temperature": missing,
                    "absent_slots": expected - present,
                    "observed_temperature_slots": present - missing,
                    "unknown_slots": expected - present + missing,
                }
            )
    with (ROOT / "results/source_coverage.csv").open(
        "w", encoding="utf-8", newline=""
    ) as f:
        w = csv.DictWriter(f, fieldnames=list(coverage[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(coverage)
    cert = {
        "status": "PASS",
        "source_rows": len(rows),
        "source_objects": len(objects),
        "station_years": len(coverage),
        "expected_calendar_slots": sum(r["expected_utc_slots"] for r in coverage),
        "observed_temperature_slots": sum(
            r["observed_temperature_slots"] for r in coverage
        ),
        "unknown_slots": sum(r["unknown_slots"] for r in coverage),
        "all_inputs_not_blinded": True,
        "this_command_computes_no_threshold_or_tail_summaries": True,
        "scope": "Exact source fields/locators/units/calendar/duplicate/sentinel accounting; all missing slots retained without station or year exclusion; full QC flags unavailable in Lite",
    }
    (ROOT / "results/SOURCE_CHECK.json").write_text(
        json.dumps(cert, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(cert))


if __name__ == "__main__":
    main()
