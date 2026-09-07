"""Figure generation for the README and the app's network-health page.

One function per figure, each taking a warehouse connection and returning a
matplotlib Figure. Rendering is separated from querying so a chart can be
rebuilt against new data without touching its layout.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from analysis import queries  # noqa: E402

# Utility-locate blue (AWWA marks potable water in blue) against corrosion
# rust, which is the actual failure mode of the pipes this is about.
INK = "#132029"
MUTED = "#657785"
GRID = "#D5DFE6"
BLUE = "#0B5FBF"
RUST = "#AB4318"
GREEN = "#12705A"
SAND = "#C9A227"

plt.rcParams.update(
    {
        "figure.dpi": 140,
        "savefig.dpi": 140,
        "savefig.bbox": "tight",
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 9,
        "text.color": INK,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        # Room for the subtitle _subtitle() writes just under the title.
        "axes.titlepad": 22,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": GRID,
        "grid.linewidth": 0.7,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    }
)


def _despine(ax, keep=("left", "bottom")) -> None:
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(side in keep)


def _subtitle(ax, text: str) -> None:
    ax.text(0.0, 1.012, text, transform=ax.transAxes, fontsize=8.5, color=MUTED, va="bottom")


def fig_material_rate(con) -> plt.Figure:
    """Cast iron survives normalisation: it is a minority of the network by
    length and the large majority of the failures."""
    df = queries.rate_by_material(con).sort_values("rate_per_100km")

    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    colors = [RUST if m == "CI" else BLUE for m in df["material"]]
    bars = ax.barh(df["material"], df["rate_per_100km"], color=colors, height=0.62)

    for bar, (_, row) in zip(bars, df.iterrows(), strict=True):
        ax.text(
            bar.get_width() + 0.5,
            bar.get_y() + bar.get_height() / 2,
            f"{row.rate_per_100km:.1f}   "
            f"({row.pct_of_breaks:.0f}% of breaks, {row.pct_of_network:.0f}% of network)",
            va="center",
            fontsize=8,
            color=MUTED,
        )

    ax.set_xlim(0, df["rate_per_100km"].max() * 1.75)
    ax.set_xlabel("Breaks per 100 km per year")
    ax.set_ylabel("")
    # Computed, not hardcoded, so the headline cannot drift from the data.
    ci = df.loc[df["material"] == "CI", "rate_per_100km"]
    pvc = df.loc[df["material"] == "PVC", "rate_per_100km"]
    if len(ci) and len(pvc) and pvc.iloc[0] > 0:
        ax.set_title(
            f"Cast iron fails {ci.iloc[0] / pvc.iloc[0]:.0f}× more than PVC, per kilometre"
        )
    else:
        ax.set_title("Failure rate by pipe material, normalised by length")
    _subtitle(ax, "City of Kitchener distribution mains, 2010–2025 complete years")
    ax.grid(axis="y", visible=False)
    _despine(ax)
    fig.tight_layout()
    return fig


def fig_age_vs_cohort(con) -> plt.Figure:
    """The confounding result. Read alone, the age curve says failure risk
    *falls* after 60 years. Holding material constant and cutting by install
    decade shows why: mid-century cast iron is the problem, not age itself."""
    age = queries.hazard_by_age(con)
    cohort = queries.hazard_by_cohort(con, material="CI")

    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.8))

    ax = axes[0]
    ax.plot(age["age_band_start"], age["rate_per_100km"], color=BLUE, lw=2, marker="o", ms=4)
    peak = age.loc[age["rate_per_100km"].idxmax()]
    descent = age[age["age_band_start"] > peak.age_band_start].iloc[0]
    ax.annotate(
        "declines past 60 — vintage,\nnot age (see right)",
        xy=(descent.age_band_start, descent.rate_per_100km),
        xytext=(2, peak.rate_per_100km * 0.80),
        fontsize=8,
        color=RUST,
        va="center",
        ha="left",
        arrowprops={"arrowstyle": "->", "color": RUST, "lw": 1, "connectionstyle": "arc3,rad=0.28"},
    )
    ax.set_xlabel("Pipe age (years)")
    ax.set_ylabel("Breaks per 100 km per year")
    ax.set_title("Apparent hazard by age")
    _subtitle(ax, "All materials")
    ax.set_ylim(0, None)
    _despine(ax)

    ax = axes[1]
    colors = [RUST if d in ("1950s", "1960s") else BLUE for d in cohort["install_decade"]]
    ax.bar(cohort["install_decade"], cohort["rate_per_100km"], color=colors, width=0.66)
    for _, row in cohort.iterrows():
        ax.text(
            row.install_decade,
            row.rate_per_100km + 0.8,
            f"{row.rate_per_100km:.0f}",
            ha="center",
            fontsize=8,
            color=MUTED,
        )
    ax.set_xlabel("Installation decade")
    ax.set_ylabel("")
    ax.set_title("Cast iron hazard by cohort")
    _subtitle(ax, "Cast iron only — thin-wall spun CI of the 1950s–60s is the worst vintage")
    ax.set_ylim(0, cohort["rate_per_100km"].max() * 1.22)
    ax.grid(axis="x", visible=False)
    _despine(ax)

    fig.tight_layout()
    return fig


def fig_repeat_failure(con) -> plt.Figure:
    """Break history is the strongest single predictor, and it survives holding
    material and cohort constant -- so it is not just a proxy for old CI."""
    overall = queries.repeat_failure(con)
    controlled = queries.repeat_failure(con, material="CI", decades=("1950s", "1960s"))

    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    x = np.arange(len(overall))
    width = 0.38

    ax.bar(x - width / 2, overall["rate_per_100km"], width, label="All pipes", color=BLUE)
    ax.bar(
        x + width / 2,
        controlled["rate_per_100km"],
        width,
        label="Cast iron, 1950s–60s only",
        color=RUST,
    )

    for i, (a, b) in enumerate(
        zip(overall["rate_per_100km"], controlled["rate_per_100km"], strict=True)
    ):
        ax.text(i - width / 2, a + 0.8, f"{a:.1f}", ha="center", fontsize=8, color=MUTED)
        ax.text(i + width / 2, b + 0.8, f"{b:.1f}", ha="center", fontsize=8, color=MUTED)

    ax.set_xticks(x)
    ax.set_xticklabels(["0", "1", "2", "3 or more"])
    ax.set_xlabel("Prior breaks on the same segment (as of 1 January)")
    ax.set_ylabel("Breaks per 100 km per year")
    ax.set_title("A pipe that has broken before breaks again")
    _subtitle(
        ax,
        "12× gradient overall; 2.4× within a single material and cohort, so it is real signal",
    )
    ax.legend(frameon=False, fontsize=8.5, loc="upper left")
    ax.set_ylim(0, max(overall["rate_per_100km"].max(), controlled["rate_per_100km"].max()) * 1.2)
    ax.grid(axis="x", visible=False)
    _despine(ax)
    fig.tight_layout()
    return fig


def fig_seasonality(con) -> plt.Figure:
    """More than half of all breaks land in the winter quarter."""
    df = queries.seasonality(con)
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    colors = [RUST if m in (12, 1, 2) else BLUE for m in df["month"]]
    ax.bar(df["month"], df["breaks"], color=colors, width=0.68)
    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(months)
    ax.set_ylabel("Breaks recorded, 2000–2026")
    ax.set_xlabel("")
    winter_pct = df.loc[df["month"].isin([12, 1, 2]), "pct_of_breaks"].sum()
    ax.set_title(f"{winter_pct:.0f}% of breaks fall in December–February")
    _subtitle(ax, "A uniform distribution would put 25% there")

    ax2 = ax.twinx()
    ax2.plot(df["month"], df["mean_temp_c"], color=MUTED, lw=1.6, ls="--", marker="o", ms=3)
    ax2.set_ylabel("Mean daily temperature (°C)", color=MUTED)
    ax2.grid(False)
    ax2.tick_params(axis="y", colors=MUTED)
    for side in ("top", "left", "bottom"):
        ax2.spines[side].set_visible(False)
    ax2.spines["right"].set_color(GRID)

    ax.grid(axis="x", visible=False)
    _despine(ax)
    fig.tight_layout()
    return fig


def fig_winter_severity(con) -> plt.Figure:
    """Frost depth, not freeze-thaw cycling, is what tracks the annual total."""
    df = queries.winter_severity_vs_breaks(con)
    r = df["freezing_degree_days"].corr(df["breaks"])

    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.scatter(df["freezing_degree_days"], df["breaks"], s=42, color=BLUE, zorder=3, alpha=0.85)

    slope, intercept = np.polyfit(df["freezing_degree_days"], df["breaks"], 1)
    xs = np.linspace(df["freezing_degree_days"].min(), df["freezing_degree_days"].max(), 50)
    ax.plot(xs, slope * xs + intercept, color=RUST, lw=1.6, zorder=2)

    for _, row in df.iterrows():
        if row.panel_year in (2014, 2015, 2012, 2024):
            ax.annotate(
                str(int(row.panel_year)),
                xy=(row.freezing_degree_days, row.breaks),
                xytext=(6, 4),
                textcoords="offset points",
                fontsize=8,
                color=INK if row.panel_year in (2014, 2015) else MUTED,
                fontweight="bold" if row.panel_year in (2014, 2015) else "normal",
            )

    ax.set_xlabel("Freezing degree-days, 1 Nov – 31 Mar (°C·days below freezing)")
    ax.set_ylabel("Breaks that year")
    ax.set_title(f"Colder winters break more pipe (r = {r:.2f})")
    _subtitle(
        ax,
        "2014–15, the two hardest winters on record here, are the two worst break years",
    )
    _despine(ax)
    fig.tight_layout()
    return fig


def fig_break_map(con) -> plt.Figure:
    """Where breaks concentrate. Deliberately a density view, not a pin map --
    the product question is which pipes are at risk, and a pin per incident
    reads as 'where has the city dug' rather than 'where should it dig next'."""
    df = queries.break_locations(con)

    fig, ax = plt.subplots(figsize=(6.4, 6.4))
    hb = ax.hexbin(
        df["longitude"],
        df["latitude"],
        gridsize=42,
        cmap="YlGnBu",
        mincnt=1,
        linewidths=0.2,
        edgecolors="white",
    )
    cbar = fig.colorbar(hb, ax=ax, shrink=0.62, pad=0.02)
    cbar.set_label("Breaks since 2000", fontsize=8.5, color=MUTED)
    cbar.outline.set_visible(False)
    cbar.ax.tick_params(colors=MUTED, labelsize=8)

    ax.set_aspect(1 / np.cos(np.radians(df["latitude"].mean())))
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.2f}°"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.2f}°"))
    ax.set_title(f"Break density, {len(df):,} incidents since 2000")
    _subtitle(
        ax,
        "Failure clusters rather than spreading evenly — which is what makes ranking worth doing",
    )
    ax.grid(visible=False)
    _despine(ax, keep=())
    fig.tight_layout()
    return fig


def fig_concentration(con) -> plt.Figure:
    """The product thesis in one line: failure is concentrated, so a ranked
    inspection list is worth building.

    Explicitly a hindsight bound. Pipes are ranked by breaks already observed,
    so this is the ceiling a perfect ranking would have hit, not a claim about
    what the model can forecast. Phase 4 measures that against a held-out year.
    """
    curve = queries.concentration_curve(con)

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.plot(curve["pct_network_km"], curve["pct_breaks_captured"], color=BLUE, lw=2.2, zorder=3)
    ax.plot([0, 100], [0, 100], color=MUTED, lw=1.2, ls="--", zorder=2, label="Random ranking")

    for target in (5, 10):
        row = curve.iloc[(curve["pct_network_km"] - target).abs().idxmin()]
        ax.plot([target, target], [0, row.pct_breaks_captured], color=RUST, lw=1, ls=":", zorder=4)
        ax.plot([0, target], [row.pct_breaks_captured] * 2, color=RUST, lw=1, ls=":", zorder=4)
        ax.scatter([target], [row.pct_breaks_captured], s=34, color=RUST, zorder=5)
        ax.annotate(
            f"worst {target}% of length holds {row.pct_breaks_captured:.0f}% of breaks",
            xy=(target, row.pct_breaks_captured),
            xytext=(target + 6, row.pct_breaks_captured - 9),
            fontsize=8.5,
            color=RUST,
        )

    ax.set_xlim(0, 100)
    ax.set_ylim(0, 102)
    ax.set_xlabel("Cumulative share of network length (%), worst pipe first")
    ax.set_ylabel("Cumulative share of breaks (%)")
    ax.set_title("Failure is concentrated in a small share of the network")
    _subtitle(
        ax,
        "Hindsight bound — pipes ranked by breaks already observed, not by forecast",
    )
    ax.legend(frameon=False, fontsize=8.5, loc="lower right")
    _despine(ax)
    fig.tight_layout()
    return fig


FIGURES = {
    "01_material_rate": fig_material_rate,
    "02_age_vs_cohort": fig_age_vs_cohort,
    "03_repeat_failure": fig_repeat_failure,
    "04_seasonality": fig_seasonality,
    "05_winter_severity": fig_winter_severity,
    "06_break_map": fig_break_map,
    "07_concentration": fig_concentration,
}
