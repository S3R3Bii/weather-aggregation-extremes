"""Independently compare plotted artists to all relevant verified source-derived tables."""

import csv
import hashlib
import json
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgb
from config import ROOT
from make_figures import build


def read(name):
    with (ROOT / name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    assert (
        json.loads((ROOT / "results/EVALUATION_INDEPENDENT_CHECK.json").read_text())[
            "status"
        ]
        == "PASS"
    )
    phases = read("results/evaluation_phase.csv")
    monthly = read("results/evaluation_monthly.csv")
    intervals = read("results/evaluation_bootstrap_intervals.csv")
    primary = [r for r in phases if r["threshold_c"] == "30"]
    figures = build()
    checks = 0
    ax = figures[0][1].axes[0]
    for i, r in enumerate(primary):
        for prefix, field in [("visible", "tp"), ("hidden", "fn")]:
            bar = next(a for a in ax.patches if a.get_gid() == prefix + "-" + str(i))
            assert abs(bar.get_width() - int(r[field]) / 8) <= 1e-12
            checks += 1
        line = next(a for a in ax.lines if a.get_gid() == "unknown-" + str(i))
        assert np.allclose(
            line.get_xdata(),
            [int(r["positive_slots"]) / 8, int(r["positive_upper"]) / 8],
            rtol=0,
            atol=1e-12,
        )
        checks += 2
    heatmap_axis = figures[1][1].axes[0]
    heatmap = heatmap_axis.images[0]
    matrix = heatmap.get_array()
    contrast_ratios = []
    assert len(heatmap_axis.texts) == 96
    for text in heatmap_axis.texts:
        j, i = map(int, text.get_position())
        value = float(matrix[i, j])
        assert text.get_text() == f"{value:.1f}"

        def luminance(rgb):
            linear = [
                c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                for c in rgb[:3]
            ]
            return sum(x * w for x, w in zip(linear, [0.2126, 0.7152, 0.0722]))

        a = luminance(heatmap.get_cmap()(heatmap.norm(value)))
        b = luminance(to_rgb(text.get_color()))
        contrast = (max(a, b) + 0.05) / (min(a, b) + 0.05)
        assert contrast >= 4.5
        contrast_ratios.append(contrast)
    assert matrix.shape == (8, 12)
    assert (
        figures[1][1].axes[0].images[0].norm.vmin == 0
        and figures[1][1].axes[0].images[0].norm.vmax == 100
    )
    assert np.nanmin(matrix) >= 0 and np.nanmax(matrix) <= 100
    for i, r in enumerate(primary):
        for j in range(12):
            part = [
                x
                for x in monthly
                if x["city"] == r["city"]
                and x["threshold_c"] == "30"
                and int(x["month"]) == j + 1
            ]
            n = sum(int(x["observed_slots"]) for x in part)
            e = sum(int(x["positive_slots"]) for x in part)
            if n:
                assert abs(float(matrix[i, j]) - 100 * e / n) <= 1e-12
            else:
                assert np.ma.is_masked(matrix[i, j]) or np.isnan(matrix[i, j])
            checks += 1
    for ax, r in zip(figures[2][1].axes, primary):
        city = r["city"]
        line = next(x for x in ax.lines if x.get_gid() == "mean-" + city)
        bars = next(x for x in ax.collections if x.get_gid() == "interval-" + city)
        assert list(line.get_xdata()) == [25, 30, 35]
        for i, t in enumerate(["25", "30", "35"]):
            point = next(
                x for x in phases if x["city"] == city and x["threshold_c"] == t
            )
            ci = next(
                x for x in intervals if x["city"] == city and x["threshold_c"] == t
            )
            assert (
                abs(line.get_ydata()[i] - float(point["mean_annual_positive_slots"]))
                <= 1e-12
            )
            assert np.allclose(
                bars.get_segments()[i],
                [
                    [int(t), float(ci["positive_q05"])],
                    [int(t), float(ci["positive_q95"])],
                ],
                rtol=0,
                atol=1e-12,
            )
            checks += 3
    for name, fig in figures:
        assert (ROOT / f"figures/{name}.pdf").read_bytes().startswith(b"%PDF-")
        assert "<svg" in (ROOT / f"figures/{name}.svg").read_text(encoding="utf-8")
        plt.close(fig)
    result = {
        "status": "PASS",
        "plotted_values": checks,
        "heatmap_annotation_text_checks": 96,
        "heatmap_annotation_contrast_checks": 96,
        "heatmap_contrast_minimum_required": 4.5,
        "heatmap_scale": "Natural 0–100 percent range; no value clipping",
        "figure_hashes": {
            f"figures/{name}.{ext}": hashlib.sha256(
                (ROOT / f"figures/{name}.{ext}").read_bytes()
            ).hexdigest()
            for name, fig in figures
            for ext in ["pdf", "svg", "png"]
        },
        "scope": "All primary bar widths and missing bounds; all96month/airport proportions; every24threshold point and48year-resampling endpoints checked on artists against independently verified tables. Rendered readability checked separately.",
    }
    (ROOT / "results/FIGURE_CHECK.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "PASS", "plotted_values": checks}))


if __name__ == "__main__":
    main()
