"""Three original figures with complete reported-slot, missingness and resampling semantics."""

import calendar
import csv
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from config import ROOT

LABELS = {
    "atlanta": "Atlanta",
    "chicago": "Chicago O’Hare",
    "dallas": "Dallas/Fort Worth",
    "miami": "Miami",
    "minneapolis": "Minneapolis",
    "new_york": "New York JFK",
    "phoenix": "Phoenix",
    "seattle": "Seattle–Tacoma",
}


def read(name):
    with (ROOT / name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def readable_color(rgba):
    linear = [
        c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgba[:3]
    ]
    background = sum(c * weight for c, weight in zip(linear, [0.2126, 0.7152, 0.0722]))
    dark_rgb = [17 / 255, 24 / 255, 39 / 255]
    dark = sum(
        (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4) * weight
        for c, weight in zip(dark_rgb, [0.2126, 0.7152, 0.0722])
    )
    return (
        "white"
        if 1.05 / (background + 0.05) >= (background + 0.05) / (dark + 0.05)
        else "#111827"
    )


def build():
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "axes.titlesize": 13,
            "axes.labelsize": 11,
            "svg.fonttype": "none",
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )
    phases = read("results/evaluation_phase.csv")
    monthly = read("results/evaluation_monthly.csv")
    intervals = read("results/evaluation_bootstrap_intervals.csv")
    primary = [r for r in phases if r["threshold_c"] == "30"]
    cities = [r["city"] for r in primary]
    fig1, ax = plt.subplots(figsize=(8, 5.1), layout="constrained")
    y = np.arange(8)
    visible = np.array([int(r["tp"]) / 8 for r in primary])
    hidden = np.array([int(r["fn"]) / 8 for r in primary])
    observed = visible + hidden
    p = ax.barh(y, visible, color="#0369a1", label="Visible in monthly-mean view")
    q = ax.barh(
        y, hidden, left=visible, color="#b45309", label="Hidden by monthly mean"
    )
    for i, (a, b) in enumerate(zip(p.patches, q.patches)):
        a.set_gid("visible-" + str(i))
        b.set_gid("hidden-" + str(i))
    for i, r in enumerate(primary):
        upper = float(r["mean_annual_possible_positive_slots"])
        (line,) = ax.plot(
            [observed[i], upper],
            [i, i],
            color="#6b7280",
            lw=2.2,
            marker="|",
            markersize=10,
            label="Possible added unknown slots" if i == 0 else None,
        )
        line.set_gid("unknown-" + str(i))
    ax.set_yticks(y, [LABELS[c] for c in cities])
    ax.invert_yaxis()
    ax.set_xlim(left=0)
    ax.set_xlabel("Reported hourly slots >30°C per year (2017–2024 average)")
    ax.set_title(
        "Monthly means hide part of the reported hot-slot count", loc="left", pad=14
    )
    ax.grid(axis="x", alpha=0.17)
    ax.set_axisbelow(True)
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    figures = [("monthly_aggregation_gap", fig1)]

    matrix = np.empty((8, 12))
    denominators = np.empty((8, 12), dtype=int)
    for i, city in enumerate(cities):
        for month in range(1, 13):
            part = [
                r
                for r in monthly
                if r["city"] == city
                and r["threshold_c"] == "30"
                and int(r["month"]) == month
            ]
            n = sum(int(r["observed_slots"]) for r in part)
            e = sum(int(r["positive_slots"]) for r in part)
            matrix[i, month - 1] = 100 * e / n if n else np.nan
            denominators[i, month - 1] = n
    fig2, ax = plt.subplots(figsize=(8, 4.8), layout="constrained")
    img = ax.imshow(matrix, cmap="YlOrRd", vmin=0, vmax=100, aspect="auto")
    img.set_gid("monthly_positive_fraction")
    ax.set_yticks(range(8), [LABELS[c] for c in cities])
    ax.set_xticks(range(12), list(calendar.month_abbr)[1:])
    for i in range(8):
        for j in range(12):
            ax.text(
                j,
                i,
                "NA" if np.isnan(matrix[i, j]) else f"{matrix[i,j]:.1f}",
                ha="center",
                va="center",
                fontsize=9,
                color=readable_color(img.get_cmap()(img.norm(matrix[i, j]))),
            )
    ax.set_title(
        "Seasonality in the reported readings, not product exposure", loc="left", pad=14
    )
    fig2.colorbar(
        img,
        ax=ax,
        orientation="horizontal",
        fraction=0.07,
        pad=0.08,
        label="Readings >30°C (% of observed temperatures; 2017–2024)",
    )
    figures.append(("monthly_reported_tail", fig2))

    fig3, axes = plt.subplots(2, 4, figsize=(8, 5.4), layout="constrained")
    for ax, city in zip(axes.flat, cities):
        part = [
            next(r for r in phases if r["city"] == city and r["threshold_c"] == str(t))
            for t in [25, 30, 35]
        ]
        ci = [
            next(
                r for r in intervals if r["city"] == city and r["threshold_c"] == str(t)
            )
            for t in [25, 30, 35]
        ]
        x = [25, 30, 35]
        means = [float(r["mean_annual_positive_slots"]) for r in part]
        low = [float(r["positive_q05"]) for r in ci]
        high = [float(r["positive_q95"]) for r in ci]
        bars = ax.vlines(x, low, high, color="#94a3b8", lw=3)
        bars.set_gid("interval-" + city)
        (line,) = ax.plot(x, means, "o-", color="#0369a1", lw=1.5, markersize=4)
        line.set_gid("mean-" + city)
        ax.set_xticks(x)
        ax.set_ylim(bottom=0)
        ax.grid(alpha=0.15)
        ax.set_title(LABELS[city], fontsize=10.5, loc="left")
    fig3.supxlabel("Illustrative outdoor threshold (°C)", fontsize=11)
    fig3.supylabel("Observed positive hourly slots per year", fontsize=11)
    fig3.suptitle(
        "All thresholds with conditional whole-year resampling ranges\n2017–2024; vertical scales vary by airport",
        x=0.04,
        ha="left",
        fontsize=12,
    )
    figures.append(("threshold_year_ranges", fig3))
    return figures


def main():
    for name, fig in build():
        fig.savefig(
            ROOT / f"figures/{name}.pdf",
            metadata={
                "CreationDate": None,
                "ModDate": None,
                "Creator": "Study32 reproducible Python figure",
            },
        )
        fig.savefig(ROOT / f"figures/{name}.svg")
        fig.savefig(ROOT / f"figures/{name}.png", dpi=150)
        path = ROOT / f"figures/{name}.svg"
        path.write_bytes(
            (
                "\n".join(
                    line.rstrip()
                    for line in path.read_text(encoding="utf-8").splitlines()
                )
                + "\n"
            ).encode()
        )
        plt.close(fig)
    print("Created three original PDF/SVG/PNG figures")


if __name__ == "__main__":
    main()
