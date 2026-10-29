"""Complete independent whitespace-field and source-locator reconciliation, without production parsing."""

import argparse
import csv
import gzip
import hashlib
import itertools
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from config import ROOT


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("originals", type=Path)
    p.add_argument("--station-history", required=True, type=Path)
    a = p.parse_args()
    m = json.loads((ROOT / "data/source/manifest.json").read_text())
    assert sha(ROOT / m["public_file"]) == m["public_sha256"]
    objects = {r["file"]: r for r in m["objects"]}
    seen_files = set()
    nrows = 0
    counts = Counter()
    with gzip.open(ROOT / m["public_file"], "rt", encoding="utf-8", newline="") as f:
        for name, group in itertools.groupby(
            csv.DictReader(f), key=lambda r: r["source_file"]
        ):
            assert name not in seen_files
            seen_files.add(name)
            meta = objects[name]
            payload = (a.originals / name).read_bytes()
            assert hashlib.sha256(payload).hexdigest() == meta["sha256"]
            plain = gzip.decompress(payload)
            assert hashlib.sha256(plain).hexdigest() == meta["uncompressed_sha256"]
            expected = {}
            times = set()
            for line_number, line in enumerate(plain.decode("ascii").splitlines(), 1):
                values = line.split()
                assert len(values) == 12
                y, mo, d, h, t = map(int, values[:5])
                assert y == meta["year"] and (t == -9999 or -1000 <= t <= 700)
                stamp = datetime.strptime(f"{y:04d}{mo:02d}{d:02d}{h:02d}", "%Y%m%d%H")
                assert stamp not in times
                times.add(stamp)
                expected[line_number] = {
                    "source_file": name,
                    "source_line": str(line_number),
                    "station": meta["station"],
                    "year": str(y),
                    "month": str(mo),
                    "day": str(d),
                    "hour": str(h),
                    "temperature_tenths": str(t),
                }
                counts[meta["station"], y, "rows"] += 1
                counts[meta["station"], y, "missing"] += t == -9999
            checked = set()
            for row in group:
                i = int(row["source_line"])
                assert i not in checked
                checked.add(i)
                assert expected[i] == row, (name, i)
                nrows += 1
            assert len(checked) == len(expected) == meta["source_rows"]
            assert (
                meta["bytes"]
                == len(payload)
                == int(meta["object_headers"]["Content-Length"])
            )
    assert seen_files == set(objects) and nrows == m["source_rows"]
    with (ROOT / "results/source_coverage.csv").open(encoding="utf-8") as f:
        coverage = list(csv.DictReader(f))
    for r in coverage:
        sid = r["station"]
        y = int(r["year"])
        hours = int((datetime(y + 1, 1, 1) - datetime(y, 1, 1)).total_seconds() / 3600)
        n = counts[sid, y, "rows"]
        missing = counts[sid, y, "missing"]
        assert [
            int(r[k])
            for k in [
                "expected_utc_slots",
                "source_rows",
                "explicit_missing_temperature",
                "absent_slots",
                "observed_temperature_slots",
                "unknown_slots",
            ]
        ] == [hours, n, missing, hours - n, n - missing, hours - n + missing]
    with a.station_history.open(encoding="utf-8-sig", newline="") as f:
        history = list(csv.DictReader(f))
    station_rows = json.loads((ROOT / "data/stations.json").read_text())
    assert len(station_rows) == 8
    for r in station_rows:
        match = [h for h in history if (h["USAF"], h["WBAN"]) == (r["usaf"], r["wban"])]
        assert len(match) == 1
        h = match[0]
        assert (r["name"], r["latitude"], r["longitude"]) == (
            h["STATION NAME"],
            h["LAT"],
            h["LON"],
        )
        assert h["BEGIN"] <= "20100101" and h["END"] >= "20241231"
    cert = {
        "status": "PASS",
        "source_rows": nrows,
        "source_objects": len(objects),
        "selected_source_field_checks": nrows * 5,
        "projected_scalar_checks": nrows * 8,
        "station_year_checks": len(coverage),
        "station_metadata_rows_checked": 8,
        "station_history_sha256": sha(a.station_history),
        "public_source_sha256": m["public_sha256"],
        "public_manifest_sha256": hashlib.sha256(
            (ROOT / "data/source/manifest.json").read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest(),
        "methods": "Independent whitespace parse and strptime calendars; every raw selected field/line locator/public cell, compressed/uncompressed hash, missing/absent calendar count and station metadata reconciled",
        "limits": "Reported source facts checked; absent full Lite quality flags and continuous physical exposure remain unverified",
    }
    (ROOT / "results/INDEPENDENT_SOURCE_CHECK.json").write_text(
        json.dumps(cert, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(cert))


if __name__ == "__main__":
    main()
