"""Plot RTT and connection setup time vs. number of clients,
baseline (plain learning switch) vs. the controller with tiered queues.

Matched runs (20 messages/client, ~1000-byte messages, 3 runs) are read
from:

    experiments/results/compare_baseline_<n>clients.csv
    experiments/results/compare_ours_<n>clients.csv

Baseline files exist for 10, 25, 50 and 100 clients.  Older
``baseline_<n>clients.csv`` runs used only 5 short messages per client;
they are only drawn (dashed grey) for counts that have no matched
baseline, so they are not compared against the 20-message curves.

The matched 100-client baseline may also exist as
``baseline_100clients.csv`` (it predates the ``compare_baseline_*``
naming convention), so that file is accepted as a fallback.

Output:

    experiments/results/comparison_rtt.png
    experiments/results/comparison_connection_setup.png
"""

import csv
import statistics
import sys
from pathlib import Path

import matplotlib.pyplot as plt

RESULTS = Path(__file__).resolve().parent / "results"
CLIENT_COUNTS = [10, 25, 50, 100]

SERIES = {
    "baseline": {
        "label": "Baseline (normal users, 20 msgs/client, 3 runs)",
        "prefix": "compare_baseline",
        "color": "#1f77b4",
        "marker": "o",
        "linestyle": "-",
    },
    "ours": {
        "label": "Policy (normal users, 20 msgs/client, 3 runs)",
        "prefix": "compare_ours",
        "color": "#d62728",
        "marker": "o",
        "linestyle": "-",
    },
}

HISTORICAL = {
    "label": "Baseline (historical: 5 short msgs/client, not comparable)",
    "prefix": "baseline",
    "color": "#7f7f7f",
    "marker": "s",
    "linestyle": "--",
}


def avg(filename, column):
    with open(filename, newline="") as f:
        # The comparison curves are normal-tier traffic.  A --priority run
        # also writes pri1, which belongs in the separate priority plot.
        rows = [r for r in csv.DictReader(f)
                if r["status"] == "SUCCESS"
                and not r["username"].startswith("pri")]
    return statistics.mean(float(r[column]) for r in rows) if rows else None


def series_avg(prefix, count, column):
    path = RESULTS / f"{prefix}_{count}clients.csv"
    if not path.exists():
        return None
    return avg(path, column)


def collect(column):
    """Return matched points and historical baseline points."""
    matched = {setup: ([], []) for setup in SERIES}
    historical = ([], [])

    for count in CLIENT_COUNTS:
        for setup, meta in SERIES.items():
            value = series_avg(meta["prefix"], count, column)
            if value is None and setup == "baseline" and count == 100:
                # The matched 100-client baseline predates the
                # compare_baseline_* naming convention.
                value = series_avg("baseline", count, column)
            if value is not None:
                matched[setup][0].append(count)
                matched[setup][1].append(value)

        # Only use the historical baseline where no matched baseline exists.
        has_matched_baseline = (
            (RESULTS / f"compare_baseline_{count}clients.csv").exists()
            or (count == 100
                and (RESULTS / f"baseline_{count}clients.csv").exists())
        )
        if not has_matched_baseline:
            value = series_avg(HISTORICAL["prefix"], count, column)
            if value is not None:
                historical[0].append(count)
                historical[1].append(value)

    return matched, historical


def plot(column, ylabel, outfile):
    matched, historical = collect(column)

    if not any(matched[s][0] for s in SERIES) and not historical[0]:
        sys.exit(f"No input CSVs found for {column!r}; nothing to plot.")

    fig, ax = plt.subplots(figsize=(8.0, 5.2))
    handles = {}

    if historical[0]:
        handles["historical"], = ax.plot(
            historical[0], historical[1],
            marker=HISTORICAL["marker"], linestyle=HISTORICAL["linestyle"],
            color=HISTORICAL["color"], markerfacecolor="white",
            markeredgecolor=HISTORICAL["color"], linewidth=1.5,
            label=HISTORICAL["label"], zorder=2)

    for setup in ("baseline", "ours"):
        counts, values = matched[setup]
        if not counts:
            continue
        meta = SERIES[setup]
        handles[setup], = ax.plot(
            counts, values, marker=meta["marker"],
            linestyle=meta["linestyle"], color=meta["color"],
            linewidth=2, markersize=6, label=meta["label"], zorder=3)
        # Put the baseline labels above its points and the policy labels to
        # the right; the two curves nearly coincide at 25 clients.
        dx, dy, ha = ((0, 10, "center") if setup == "baseline"
                      else (12, -2, "left"))
        for count, value in zip(counts, values):
            ax.annotate(f"{value:.0f}", (count, value),
                        textcoords="offset points", xytext=(dx, dy),
                        ha=ha, fontsize=7, color=meta["color"])

    ax.set_xlim(left=0, right=max(CLIENT_COUNTS) * 1.15)
    plotted_values = [v for setup in SERIES for v in matched[setup][1]]
    plotted_values += historical[1]
    if plotted_values:
        ax.set_ylim(0, max(plotted_values) * 1.12)
    else:
        ax.set_ylim(bottom=0)
    ax.set_xticks(CLIENT_COUNTS)
    ax.set_xlabel("Concurrent clients")
    ax.set_ylabel(ylabel)
    ax.set_title(f"{ylabel} vs. number of clients")
    ax.grid(True, alpha=0.3)

    order = [k for k in ("baseline", "ours", "historical") if k in handles]
    ax.legend([handles[k] for k in order],
              [handles[k].get_label() for k in order],
              loc="upper left", fontsize=8)

    fig.text(
        0.5, 0.01,
        "Matched runs use 20 messages of ~1000 bytes per client over 3 runs. "
        "Comparison curves show normal-batch users only; the priority user "
        "is in the separate priority plot. "
        + (f"The historical baseline points ({'/'.join(map(str, historical[0]))}) "
           "used 5 short messages per client and are not directly comparable; "
           "no matched baseline data exists for those client counts."
           if historical[0] else ""),
        ha="center", va="bottom", fontsize=7, color="#444444", wrap=True)
    fig.subplots_adjust(bottom=0.22)

    fig.savefig(outfile, dpi=200, bbox_inches="tight")
    plt.close(fig)

    for setup in ("baseline", "ours"):
        for c, v in zip(*matched[setup]):
            print(f"{SERIES[setup]['label']:>50} {c:>4} clients: {v:.3f} {ylabel}")
    for c, v in zip(*historical):
        print(f"{HISTORICAL['label']:>50} {c:>4} clients: {v:.3f} {ylabel}")
    print(f"Saved {outfile}\n")


def main():
    plot("rtt_ms", "Average RTT (ms)", RESULTS / "comparison_rtt.png")
    plot("connection_setup_ms", "Connection Setup Time (ms)",
         RESULTS / "comparison_connection_setup.png")


if __name__ == "__main__":
    main()
