"""Check every displayed table/headline, qualification, approved byte and bounded PDF exclusion."""

import csv
import hashlib
import json
import re
import unicodedata
from pypdf import PdfReader
from config import ROOT

LABELS = {
    "atlanta": "Atlanta",
    "chicago": "Chicago O'Hare",
    "dallas": "Dallas/Fort Worth",
    "miami": "Miami",
    "minneapolis": "Minneapolis",
    "new_york": "New York JFK",
    "phoenix": "Phoenix",
    "seattle": "Seattle--Tacoma",
}


def read(name):
    with (ROOT / name).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main():
    scope = json.loads((ROOT / "paper/PUBLICATION_SCOPE.json").read_text())
    assert (
        scope["scope"] == "independent-program-study"
        and scope["formal_submission_target"] is False
        and len(scope["public_files"]) == 5
    )
    for name, digest in scope["public_files"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    certs = {
        n: json.loads((ROOT / f"results/{n}.json").read_text())
        for n in [
            "SOURCE_CHECK",
            "INDEPENDENT_SOURCE_CHECK",
            "DEVELOPMENT_INDEPENDENT_CHECK",
            "EVALUATION_INDEPENDENT_CHECK",
            "REPRODUCTION",
            "FIGURE_CHECK",
        ]
    }
    assert all(j["status"] == "PASS" for j in certs.values())
    tex = (ROOT / "paper/main.tex").read_text(encoding="utf-8")
    checks = 0

    def require(text):
        nonlocal checks
        assert text in tex, text
        checks += 1

    coverage = read("results/source_coverage.csv")
    phases = read("results/evaluation_phase.csv")
    primary = [r for r in phases if r["threshold_c"] == "30"]
    ci = read("results/evaluation_bootstrap_intervals.csv")
    assert len(primary) == 8 and len(phases) == 24
    for r in primary:
        label = LABELS[r["city"]]
        require(
            " & ".join(
                [
                    label,
                    r["station"].replace("-", "/"),
                    f"{sum(int(x['unknown_slots']) for x in coverage if x['city']==r['city']):,}",
                    f"{int(r['unknown_slots']):,}",
                ]
            )
        )
        require(
            " & ".join(
                [
                    label,
                    f"{int(r['observed_slots']):,}",
                    f"{int(r['unknown_slots']):,}",
                    f"{int(r['positive_slots']):,}",
                    f"{100*int(r['fn'])/int(r['positive_slots']):.1f}\\%",
                    f"[{float(r['mean_annual_positive_slots']):.3f}, {float(r['mean_annual_possible_positive_slots']):.3f}]",
                ]
            )
        )
        interval = next(
            x for x in ci if x["city"] == r["city"] and x["threshold_c"] == "30"
        )
        require(
            " & ".join(
                [
                    label,
                    f"{float(r['mean_annual_positive_slots']):.3f}",
                    f"[{float(interval['positive_q05']):.3f}, {float(interval['positive_q95']):.3f}]",
                ]
            )
        )
        require(
            " & ".join(
                [
                    label,
                    f"{int(r['observed_p99_tenths_c'])/10:.1f}",
                    f"{int(r['observed_max_tenths_c'])/10:.1f}",
                    r["longest_confirmed_annual_slot_run"],
                    r["longest_possible_annual_slot_run"],
                ]
            )
        )
    totals = {
        k: sum(int(r[k]) for r in primary)
        for k in [
            "positive_slots",
            "tp",
            "fp",
            "fn",
            "tn",
            "observed_slots",
            "unknown_slots",
            "expected_slots",
            "monthly_view_positive_slots",
        ]
    }
    assert totals == {
        "positive_slots": 49423,
        "tp": 22781,
        "fp": 8059,
        "fn": 26642,
        "tn": 492289,
        "observed_slots": 549771,
        "unknown_slots": 11253,
        "expected_slots": 561024,
        "monthly_view_positive_slots": 30840,
    }
    for v in totals.values():
        require(f"{v:,}")
    require(f"{100*totals['fn']/totals['positive_slots']:.1f}\\%")
    assert sum(int(r["fn"]) == int(r["positive_slots"]) for r in primary) == 6
    r = next(r for r in primary if r["city"] == "minneapolis")
    assert int(r["unknown_slots"]) == 10966
    require(f"{100*int(r['unknown_slots'])/int(r['expected_slots']):.1f}\\%")
    require("110.75")
    require("1,481.5")
    require("1,279.5--1,282.25")
    for year, unknown in [(2020, 3666), (2021, 3641), (2022, 3605)]:
        assert (
            next(
                int(r["unknown_slots"])
                for r in coverage
                if r["city"] == "minneapolis" and int(r["year"]) == year
            )
            == unknown
        )
        require(f"{unknown:,}")
    source = certs["SOURCE_CHECK"]
    assert source["source_rows"] - source["observed_temperature_slots"] == 11029
    assert source["expected_calendar_slots"] - source["source_rows"] == 313
    for v in [
        source["source_rows"],
        source["expected_calendar_slots"],
        source["observed_temperature_slots"],
        source["unknown_slots"],
        11029,
        313,
        certs["INDEPENDENT_SOURCE_CHECK"]["selected_source_field_checks"],
        certs["INDEPENDENT_SOURCE_CHECK"]["projected_scalar_checks"],
        certs["DEVELOPMENT_INDEPENDENT_CHECK"]["exact_scalar_checks"]
        + certs["EVALUATION_INDEPENDENT_CHECK"]["exact_scalar_checks"],
        certs["DEVELOPMENT_INDEPENDENT_CHECK"]["reported_float_checks"]
        + certs["EVALUATION_INDEPENDENT_CHECK"]["reported_float_checks"],
        certs["REPRODUCTION"]["exact_csv_fields_or_json_documents"],
        certs["FIGURE_CHECK"]["plotted_values"],
    ]:
        require(f"{v:,}")
    assert (
        certs["FIGURE_CHECK"]["heatmap_annotation_text_checks"]
        == certs["FIGURE_CHECK"]["heatmap_annotation_contrast_checks"]
        == 96
    )
    assert certs["REPRODUCTION"]["frozen_dependencies"] == 18
    for phrase in [
        "eighteen-dependency freeze",
        "inputs were not blinded",
        "not an out-of-sample forecast",
        "not a confidence interval",
        "individual observation quality is unverified",
        "not product-safety limits, manufacturer setpoints",
        "not demonstrated continuous physical duration",
        "do not bound the hypothetical complete-month mean",
        "Year exchangeability",
        "year boundary",
        "climate trends",
        "quality-bearing observations",
        "not a correction for gaps",
        "merge notice",
        "no accessibility conformance",
        "exact to three decimals",
    ]:
        require(phrase)
    commands = [
        "python -m pip install -r requirements.txt",
        "python -m unittest discover -s tests -v",
        "python src/check_reproduction.py",
        "python src/verify_figures.py",
        "python src/verify_paper.py",
        "python src/verify_public_package.py",
    ]
    for command in commands:
        require(command)
    reader = PdfReader(ROOT / "paper/manuscript.pdf")
    assert len(reader.pages) == 8 and not reader.is_encrypted
    pages = [
        unicodedata.normalize("NFKC", p.extract_text() or "") for p in reader.pages
    ]
    headings = [
        "Decision and verified finding",
        "1. Fixed source panel and complete accounting",
        "2. Exact aggregation, unknown slots and protected sequence",
        "3. Every airport in the primary held comparison",
        "4. Seasonal detail and the meaning of the monthly view",
        "5. Every threshold and conditional whole-year resampling",
        "6. Missingness, empirical tails and sample runs",
        "7. Reproduction and independent evidence",
    ]
    for text, title in zip(pages, headings):
        assert title in re.sub(r"\s+", " ", text), title
    text = " ".join(pages)
    normalized = re.sub(r"\s+", " ", text)
    for token in commands + [
        "49,423",
        "26,642",
        "53.9%",
        "8,059",
        "10,966",
        "1,282.25",
        "330,561",
        "5,258,275",
    ]:
        assert token in normalized, token
        checks += 1
    assert not re.search(
        r"(?:[Cc]:\\[Uu]sers\\|/[Uu]sers/|/[Hh]ome/|github_pat_|ghp_[A-Za-z0-9]{20,})",
        text,
    )
    for name in scope["public_files"]:
        if not name.endswith(".pdf"):
            continue
        doc = PdfReader(ROOT / name)
        assert not doc.is_encrypted and not doc.attachments
        catalog = doc.trailer["/Root"]
        assert not any(k in catalog for k in ["/AA", "/AcroForm", "/Collection"])
        names = catalog.get("/Names", {})
        names = names.get_object() if hasattr(names, "get_object") else names
        assert "/JavaScript" not in names
        if "/OpenAction" in catalog:
            assert isinstance(catalog["/OpenAction"], list)
        for page in doc.pages:
            assert "/AA" not in page
            for ref in page.get("/Annots", []):
                annotation = ref.get_object()
                assert "/AA" not in annotation
                action = annotation.get("/A")
                if action:
                    action = action.get_object()
                    assert action["/S"] in ["/URI", "/GoTo"]
                    if action["/S"] == "/URI":
                        assert str(action["/URI"]).startswith("https://")
    for name in [
        "monthly_aggregation_gap",
        "monthly_reported_tail",
        "threshold_year_ranges",
    ]:
        assert (ROOT / f"paper/images/{name}.pdf").read_bytes() == (
            ROOT / f"figures/{name}.pdf"
        ).read_bytes()
    result = {
        "status": "PASS",
        "manuscript_pages": 8,
        "numeric_table_and_text_checks": checks,
        "public_file_hashes_checked": 5,
        "pdfs_checked": 4,
        "scope": "Every displayed source/primary/interval/tail row; pooled confusion and missingness headlines; all check counts and qualification/command support; rendered semantic headings/numbers; five exact approved files and bounded private-path/token scan",
        "pdf_security": "No active code, attachments, forms or additional actions; ordinary HTTPS links/navigation only. Rendered layout checked separately.",
    }
    (ROOT / "results/PAPER_CHECK.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
