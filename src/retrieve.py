"""Capture the fixed NOAA archive objects and publish only selected time/temperature facts."""

import argparse
import csv
import gzip
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from config import ROOT, YEARS

BASE = "https://noaa-isd-pds.s3.amazonaws.com/isd-lite/data/"
FIELDS = [
    "source_file",
    "source_line",
    "station",
    "year",
    "month",
    "day",
    "hour",
    "temperature_tenths",
]


def save(path, value):
    path.write_bytes((json.dumps(value, indent=2, ensure_ascii=True) + "\n").encode())


def parse_line(line, year):
    assert len(line) >= 61 and len(line.split()) == 12, "Unexpected Lite schema"
    parts = [
        int(line[0:4]),
        int(line[5:7]),
        int(line[8:11]),
        int(line[11:13]),
        int(line[13:19]),
    ]
    y, m, d, h, t = parts
    assert y == year
    stamp = datetime(y, m, d, h)
    assert (
        t == -9999 or -1000 <= t <= 700
    ), "Nonmissing temperature outside fixed broad sanity guard"
    return stamp, t


def head(url):
    with urlopen(Request(url, method="HEAD"), timeout=60) as response:
        assert response.status == 200
        return {
            k: response.headers.get(k)
            for k in ["ETag", "Last-Modified", "Content-Length"]
        }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("originals", type=Path)
    p.add_argument("--resume", action="store_true")
    a = p.parse_args()
    raw = a.originals.resolve()
    assert not raw.is_relative_to(ROOT)
    raw.mkdir(parents=True, exist_ok=a.resume)
    progress = raw / "CAPTURE_PROGRESS.json"
    objects = []
    if a.resume:
        previous = json.loads(progress.read_text())
        assert previous["state"] != "COMPLETE"
        objects = previous["objects"]
        for item in objects:
            assert (
                hashlib.sha256((raw / item["file"]).read_bytes()).hexdigest()
                == item["sha256"]
            )
    else:
        save(progress, {"state": "STARTED", "objects": objects})
    known = {x["file"]: x for x in objects}
    stations = json.loads((ROOT / "data/stations.json").read_text())
    selected = []
    seen = set()
    for station in stations:
        sid = station["usaf"] + "-" + station["wban"]
        for year in YEARS:
            name = f"{sid}-{year}.gz"
            url = BASE + str(year) + "/" + name
            if name in known:
                item = known[name]
                assert item["url"] == url
                data = (raw / name).read_bytes()
            else:
                assert not (raw / name).exists(), "Unregistered existing original"
                with urlopen(
                    Request(
                        url,
                        headers={
                            "User-Agent": "IndependentWeatherAggregationResearch/1.0"
                        },
                    ),
                    timeout=90,
                ) as response:
                    assert response.status == 200
                    data = response.read()
                    headers = {
                        k: response.headers.get(k)
                        for k in ["ETag", "Last-Modified", "Content-Length"]
                    }
                (raw / name).write_bytes(data)
                item = {
                    "city": station["city"],
                    "station": sid,
                    "year": year,
                    "file": name,
                    "url": url,
                    "captured_utc": datetime.now(timezone.utc).isoformat(),
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "object_headers": headers,
                }
                objects.append(item)
                known[name] = item
                save(progress, {"state": "CAPTURING", "objects": objects})
            plain = gzip.decompress(data)
            lines = plain.decode("ascii").splitlines()
            item["uncompressed_sha256"] = hashlib.sha256(plain).hexdigest()
            item["source_rows"] = len(lines)
            for number, line in enumerate(lines, 1):
                stamp, t = parse_line(line, year)
                key = sid, stamp
                assert key not in seen, "Duplicate station/hour"
                seen.add(key)
                selected.append(
                    [
                        name,
                        number,
                        sid,
                        stamp.year,
                        stamp.month,
                        stamp.day,
                        stamp.hour,
                        t,
                    ]
                )
            save(progress, {"state": "CAPTURING", "objects": objects})
        print(json.dumps({"station": sid, "captured_files": len(objects)}), flush=True)
    for item in objects:
        current = head(item["url"])
        assert (
            current == item["object_headers"]
        ), "Object metadata changed; preserve snapshot rather than refresh"
        assert int(current["Content-Length"]) == item["bytes"]
        item["final_head_verified_utc"] = datetime.now(timezone.utc).isoformat()
    selected.sort(key=lambda r: (r[2], r[3], r[4], r[5], r[6]))
    buffer = io.StringIO(newline="")
    w = csv.writer(buffer, lineterminator="\n")
    w.writerow(FIELDS)
    w.writerows(selected)
    out = ROOT / "data/source/temperature_slots.csv.gz"
    out.write_bytes(gzip.compress(buffer.getvalue().encode(), mtime=0))
    m = {
        "source": "NOAA ISD-Lite historical NODD archive",
        "objects": objects,
        "station_count": len(stations),
        "object_count": len(objects),
        "source_rows": len(selected),
        "public_file": "data/source/temperature_slots.csv.gz",
        "public_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "boundary": "Selected time/temperature/locator facts only; full originals/documents excluded. Near-hour readings are not continuous exposure duration, product condition or latest weather; Lite omits full quality flags.",
    }
    save(ROOT / "data/source/manifest.json", m)
    save(
        progress,
        {
            "state": "COMPLETE",
            "objects": objects,
            "selected_rows": len(selected),
            "public_sha256": m["public_sha256"],
        },
    )
    print(
        json.dumps(
            {
                "status": "CAPTURED",
                "objects": len(objects),
                "source_rows": len(selected),
            }
        )
    )


if __name__ == "__main__":
    main()
