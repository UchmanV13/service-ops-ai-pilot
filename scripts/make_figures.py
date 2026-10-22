"""Static figures for the readout (docs/figures/*.png).

Palette: reference categorical slots 1-3 (blue, orange, aqua), validated all-pairs
for CVD; aqua is below 3:1 on the surface so every series is also direct-labeled.

    python scripts/make_figures.py
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "docs" / "figures"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e0", "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 1, "lines.linewidth": 2,
    "lines.solid_capstyle": "round", "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlecolor": INK,
    "axes.titlelocation": "left", "axes.titlepad": 22,
})


def load(p):
    return json.loads((ROOT / "outputs" / p).read_text())


def save(fig, name):
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / name, dpi=160, bbox_inches="tight")
    plt.close(fig)


def sub(ax, text):
    ax.text(0, 1.02, text, transform=ax.transAxes, color=INK2, fontsize=9, va="bottom")


def main():
    p1, p2 = load("pilot1/results.json"), load("pilot2/results.json")
    lc = load("learning_curve.json")

    # 1. automation threshold sweep: coverage vs automated error, both pilots (descriptive)
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for res, split, color, label in ((p1, "test", BLUE, "Pilot 1 test"), (p2, "holdout_v2", ORANGE, "Pilot 2 holdout")):
        pts = [x for x in res["threshold_sweep"][split] if x["auto_error"] is not None and x["n_auto"] >= 30]
        xs = [x["coverage"] * 100 for x in pts]
        ys = [x["auto_error"] * 100 for x in pts]
        ax.plot(xs, ys, color=color, label=label)
        ax.annotate(label, (xs[0], ys[0]), xytext=(6, 0), textcoords="offset points", color=INK, fontsize=9, va="center")
    lam = p1["thresholds"]["ensemble"]["auto_threshold"]
    pt = min(p1["threshold_sweep"]["test"], key=lambda x: abs(x["lambda"] - lam))
    ax.plot([pt["coverage"] * 100], [pt["auto_error"] * 100], "o", ms=8, color=BLUE, mec=SURFACE, mew=2)
    ax.annotate(f"Pilot 1 certified threshold {lam:.3f}\n(chosen on validation)", (pt["coverage"] * 100, pt["auto_error"] * 100),
                xytext=(10, 14), textcoords="offset points", fontsize=8.5, color=INK2)
    ax.axhline(5, color=MUTED, lw=1)
    ax.text(ax.get_xlim()[1], 5.15, "G3 limit: 5% automated error", color=MUTED, fontsize=8, ha="right")
    ax.set_xlabel("Tickets automated (%)")
    ax.set_ylabel("Error among automated tickets (%)")
    ax.set_title("Automation trade-off as the confidence threshold moves")
    sub(ax, "Descriptive sweep on each pilot's held-out set; only Pilot 1's point was certified in advance")
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(0, 0.93))
    save(fig, "fig1_threshold_sweep.png")

    # 2. critical threshold trade-off (Pilot 2 holdout)
    cs = p2["critical_sweep_holdout"]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    xs = [c["escalation_precision"] * 100 for c in cs]
    ys = [c["critical_recall"] * 100 for c in cs]
    ax.plot(xs, ys, color=BLUE, marker="o", ms=7, mec=SURFACE, mew=2)
    tau = p2["thresholds"]["ensemble"]["critical_threshold"]
    near = min(cs, key=lambda c: abs(c["tau"] - tau))["tau"]
    for c in cs:
        if c["tau"] in (near, 0.2, 0.5, 1.01):
            lab = "hard rules only" if c["tau"] > 1 else (f"τ = {c['tau']:g}" + (f" (≈ chosen τ {tau:g})" if c["tau"] == near else ""))
            ax.annotate(lab, (c["escalation_precision"] * 100, c["critical_recall"] * 100), xytext=(6, -12), textcoords="offset points",
                        fontsize=8.5, color=INK2)
    ax.axhline(98, color=MUTED, lw=1)
    ax.text(max(xs), 98.25, "G1 target: 98% recall", color=MUTED, fontsize=8, ha="right")
    ax.set_xlabel("Escalation precision: share of escalations that were truly critical (%)")
    ax.set_ylabel("Critical recall (%)")
    ax.set_title("Catching every critical ticket costs specialist time")
    sub(ax, "Pilot 2 holdout, 158 critical tickets of 1,500; each point is a critical-score threshold τ")
    save(fig, "fig2_critical_tradeoff.png")

    # 3. learning curve
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    xs = [r["phrasings_per_intent"] for r in lc]
    ys = [r["holdout_intent_accuracy"] * 100 for r in lc]
    ax.plot(xs, ys, color=BLUE, marker="o", ms=7, mec=SURFACE, mew=2)
    for x, y in zip(xs, ys):
        ax.annotate(f"{y:.0f}%", (x, y), xytext=(0, 8), textcoords="offset points", ha="center", fontsize=9, color=INK)
    ax.set_xticks(xs)
    ax.set_ylim(55, 95)
    ax.set_xlabel("Distinct phrasings per intent in the training data")
    ax.set_ylabel("Intent accuracy on Pilot 2 holdout (%)")
    ax.set_title("More phrasing variety keeps paying off, with diminishing returns")
    sub(ax, "TF-IDF + embedding ensemble retrained at each size; holdout phrasings never seen")
    save(fig, "fig3_learning_curve.png")

    # 4. economics components, both pilots
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2), sharey=True)
    keys = ["automation_savings", "assisted_triage_savings", "spot_checks", "wrong_automation", "inappropriate_automation",
            "misroutes", "false_escalations", "missed_critical", "maintenance"]
    labels = ["Automation savings", "Assisted triage", "Spot checks", "Wrong automation", "Inappropriate automation",
              "Misroutes", "False escalations", "Missed critical", "Maintenance"]
    for ax, res, title in ((axes[0], p1, "Pilot 1 (10% automated)"), (axes[1], p2, "Pilot 2 (nothing automated)")):
        comp = res["economics"]["test_base"]["components_usd_per_1000"]
        vals = [comp.get(k, 0) for k in keys]
        y = list(range(len(keys)))[::-1]
        ax.barh(y, vals, height=0.6, color=[BLUE if v >= 0 else ORANGE for v in vals])
        for yy, v in zip(y, vals):
            if abs(v) > 0.5:
                ax.text(v + (25 if v >= 0 else -25), yy, f"{'+' if v > 0 else '−'}${abs(v):,.0f}", va="center",
                        ha="left" if v >= 0 else "right", fontsize=8.5, color=INK)
        ax.axvline(0, color=INK2, lw=1)
        net = res["economics"]["test_base"]["net_usd_per_1000"]
        ax.set_title(f"{title}: net {'−' if net < 0 else '+'}${abs(net):,.0f}", fontsize=11)
        ax.set_xlim(-1900, 950)
        ax.set_xlabel("USD per 1,000 tickets vs all-human baseline")
        ax.grid(axis="y", visible=False)
    axes[0].set_yticks(list(range(len(keys)))[::-1])
    axes[0].set_yticklabels(labels)
    fig.suptitle("Where the money goes (illustrative cost assumptions)", x=0.01, ha="left", fontweight="bold", color=INK)
    fig.text(0.01, 0.905, "Blue: savings. Orange: costs. Missed critical tickets and false escalations dominate both pilots.",
             color=INK2, fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    save(fig, "fig4_economics.png")

    # 5. calibration: reliability, calibrated vs raw ensemble (Pilot 2 holdout)
    fig, ax = plt.subplots(figsize=(5.4, 5.0))
    ax.plot([0, 100], [0, 100], color=MUTED, lw=1)
    for key, color, label in (("ensemble_uncalibrated", ORANGE, "Before temperature scaling"), ("ensemble", BLUE, "After")):
        tab = p2["calibration"][key]["reliability"]
        xs = [t["confidence"] * 100 for t in tab]
        ys = [t["accuracy"] * 100 for t in tab]
        ax.plot(xs, ys, color=color, marker="o", ms=6, mec=SURFACE, mew=2,
                label=f"{label} (ECE {p2['calibration'][key]['ece'] * 100:.1f} pts)")
    ax.set_xlabel("Stated confidence (%)")
    ax.set_ylabel("Actual accuracy (%)")
    ax.set_title("Calibration of the intent model")
    sub(ax, "Pilot 2 holdout; on the diagonal = confidence means what it says")
    ax.legend(frameon=False, loc="upper left", fontsize=8.5)
    save(fig, "fig5_calibration.png")

    # 6. pilot comparison of key metrics
    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    mets = [("intent_accuracy", "Intent accuracy"), ("routing_accuracy", "Routing accuracy"), ("critical_recall", "Critical recall"),
            ("escalation_precision", "Escalation precision")]
    h1 = p1["arms"]["ensemble"]["test"]
    h2 = p2["arms"]["ensemble"]["holdout_v2"]
    import numpy as np
    y = np.arange(len(mets))[::-1]
    v1 = [h1[k]["rate"] * 100 for k, _ in mets]
    v2 = [h2[k]["rate"] * 100 for k, _ in mets]
    ax.barh(y + 0.17, v1, height=0.32, color=BLUE, label="Pilot 1 (test)")
    ax.barh(y - 0.17, v2, height=0.32, color=ORANGE, label="Pilot 2 (new holdout)")
    for yy, a, b in zip(y, v1, v2):
        ax.text(a + 1, yy + 0.17, f"{a:.1f}%", va="center", fontsize=8.5, color=INK)
        ax.text(b + 1, yy - 0.17, f"{b:.1f}%", va="center", fontsize=8.5, color=INK)
    ax.set_yticks(y)
    ax.set_yticklabels([m[1] for m in mets])
    ax.set_xlim(0, 112)
    ax.set_xlabel("%")
    ax.grid(axis="y", visible=False)
    ax.set_title("Pilot 1 vs Pilot 2")
    sub(ax, "Each pilot scored once on data it never trained or calibrated on")
    ax.legend(frameon=False, loc="lower right", fontsize=8.5)
    save(fig, "fig6_pilot_comparison.png")
    print("figures:", sorted(p.name for p in FIG.glob("*.png")))


if __name__ == "__main__":
    main()
