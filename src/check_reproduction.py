"""Isolated exact replay from selected public temperature facts; private raw originals stay outside."""

import csv
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from config import ROOT


def read(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main():
    freeze = json.loads((ROOT / "results/CODE_FREEZE.json").read_text())
    for name, digest in freeze["sha256"].items():
        data = (ROOT / name).read_bytes()
        if not name.endswith(".gz"):
            data = data.replace(b"\r\n", b"\n")
        assert hashlib.sha256(data).hexdigest() == digest, name
    source = json.loads((ROOT / "results/INDEPENDENT_SOURCE_CHECK.json").read_text())
    m = json.loads((ROOT / "data/source/manifest.json").read_text())
    assert (
        source["status"] == "PASS"
        and source["public_source_sha256"] == m["public_sha256"]
    )
    assert (
        source["public_manifest_sha256"]
        == hashlib.sha256(
            (ROOT / "data/source/manifest.json").read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
    )
    targets = ["results/source_coverage.csv", "results/SOURCE_CHECK.json"]
    for phase in ["development", "evaluation"]:
        targets.extend(
            [
                f"results/{phase}_{kind}.csv"
                for kind in [
                    "monthly",
                    "annual",
                    "phase",
                    "bootstrap_indices",
                    "bootstrap_draws",
                    "bootstrap_intervals",
                ]
            ]
        )
        targets.extend(
            [
                f"results/{phase.upper()}_{kind}.json"
                for kind in ["CHECK", "INDEPENDENT_CHECK"]
            ]
        )
    count = 0
    with tempfile.TemporaryDirectory(prefix="weather32-replay-") as temp:
        out = Path(temp)
        for folder in ["src", "data"]:
            shutil.copytree(ROOT / folder, out / folder)
        (out / "results").mkdir()
        commands = [
            ["ingest.py"],
            ["analyze.py", "development"],
            ["verify_analysis.py", "development"],
            ["analyze.py", "evaluation"],
            ["verify_analysis.py", "evaluation"],
        ]
        for args in commands:
            subprocess.run(
                [sys.executable, str(out / "src" / args[0]), *args[1:]],
                check=True,
                capture_output=True,
                text=True,
            )
        for name in targets:
            if name.endswith(".csv"):
                a = read(ROOT / name)
                b = read(out / name)
                assert a == b, name
                count += sum(len(r) for r in a)
            else:
                assert json.loads((ROOT / name).read_text()) == json.loads(
                    (out / name).read_text()
                ), name
                count += 1
    result = {
        "status": "PASS",
        "exact_csv_fields_or_json_documents": count,
        "frozen_dependencies": len(freeze["sha256"]),
        "scope": "Isolated source calendar, all threshold/month/year/phase/run/tail outputs and every year-block replicate/interval, with independent SQL reconstruction; no network or private source originals required",
        "limits": "Hash-bound private-original certificate retained; public replay cannot inspect full excluded raw files or recover absent Lite QC flags/continuous exposure",
    }
    (ROOT / "results/REPRODUCTION.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
