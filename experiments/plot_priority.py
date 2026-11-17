"""Plot priority-tier user RTT vs. normal-tier user RTT under load.

Input: one or more CSVs produced by run_clients.py with the --prefix
option, e.g. users named pri1... (priority tier) and norm1... (normal
tier). Users named auto... (no tier info) are treated as normal.

Usage:

    python experiments/plot_priority.py \
        experiments/results/priority_load_run1.csv \
        [more CSVs ...]

Output:

    experiments/results/priority_vs_normal_rtt.png
"""

import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

RESULTS = Path(__file__).resolve().parent / "results"
GROUPS = {"priority": "Priority tier (queue 1)",
          "normal": "Normal tier (queue 0)"}
PREFIXES = {"pri": "priority", "norm": "normal", "auto": "normal"}
COLORS = {"priority": "#2a7ab9", "normal": "#d62728"}


def group_of(username):
    for prefix, group in PREFIXES.items():
        if username.startswith(prefix):
            return group
    return None


def main():
    files = sys.argv[1:]

    if not files:
        sys.exit("Usage: plot_priority.py <csv> [csv ...]")

    rtts = defaultdict(list)
    users = defaultdict(set)
    per_run = defaultdict(list)

    for name in files:
        run_rtts = defaultdict(list)
        with open(name, newline="") as f:
            for row in csv.DictReader(f):
                if row["status"] != "SUCCESS":
                    continue
                group = group_of(row["username"])
                if group:
                    rtt = float(row["rtt_ms"])
                    rtts[group].append(rtt)
                    users[group].add(row["username"])
                    run_rtts[group].append(rtt)

        for group, values in run_rtts.items():
            if values:
                per_run[group].append(statistics.mean(values))

    missing = [g for g in GROUPS if not rtts[g]]
    if missing:
        sys.exit(f"No RTT data for: {', '.join(missing)}. "
                 "Run run_clients.py with --prefix pri / --prefix norm.")

    labels = []
    values = []
    errors = []

    for group, label in GROUPS.items():
        values.append(statistics.mean(rtts[group]))
        errors.append(statistics.stdev(per_run[group])
                      if len(per_run[group]) > 1 else 0.0)
        labels.append(f"{label}\n{len(users[group])} user(s), "
                      f"{len(rtts[group])} msgs")
        print(f"{label}: {len(users[group])} users, "
              f"{len(rtts[group])} messages, "
              f"average RTT {values[-1]:.3f} ms")

    n_priority = len(users["priority"])
    n_normal = len(users["normal"])
    msgs_per_user = len(rtts["normal"]) // max(n_normal * len(files), 1)

    fig, ax = plt.subplots(figsize=(7.0, 5.0))
    bars = ax.bar(
        labels, values,
        color=[COLORS[g] for g in GROUPS],
        yerr=errors if any(errors) else None,
        capsize=5 if any(errors) else 0)
    ax.bar_label(bars, fmt="%.2f ms", padding=6)
    ax.set_ylim(bottom=0)
    ax.set_ylabel("Average RTT (ms)")
    ax.set_title(
        f"RTT under load: {n_priority} priority vs. {n_normal} normal "
        f"user{'s' if n_normal != 1 else ''}")

    fig.text(
        0.5, 0.01,
        f"{msgs_per_user} messages/user/run over {len(files)} run(s), "
        "~1000-byte messages. The priority user joins the priority room "
        "(vip); the normal users share room1 and provide the competing "
        "traffic when both batches run concurrently. Error bars show the "
        "spread of the per-run averages.",
        ha="center", va="bottom", fontsize=7, color="#444444", wrap=True)
    fig.subplots_adjust(bottom=0.24)

    out = RESULTS / "priority_vs_normal_rtt.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
