"""Plot priority-tier user RTT vs. normal-tier user RTT under load.

Input: one or more CSVs produced by run_clients.py with the --prefix
option, e.g. users named pri1... (priority tier) and norm1... (normal
tier). Users named auto... (no tier info) are ignored.

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
PREFIXES = {"pri": "priority", "norm": "normal"}


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

    for name in files:
        with open(name, newline="") as f:
            for row in csv.DictReader(f):
                if row["status"] != "SUCCESS":
                    continue
                group = group_of(row["username"])
                if group:
                    rtts[group].append(float(row["rtt_ms"]))

    missing = [g for g in GROUPS if not rtts[g]]
    if missing:
        sys.exit(f"No RTT data for: {', '.join(missing)}. "
                 "Run run_clients.py with --prefix pri / --prefix norm.")

    labels = []
    values = []

    for group, label in GROUPS.items():
        labels.append(label)
        values.append(statistics.mean(rtts[group]))
        print(f"{label}: {len(rtts[group])} messages, "
              f"average RTT {values[-1]:.3f} ms")

    plt.figure()
    bars = plt.bar(labels, values, color=["#2a7ab9", "#d62728"])
    plt.bar_label(bars, fmt="%.2f ms")
    plt.ylabel("Average RTT (ms)")
    plt.title("RTT under load: priority vs. normal tier")
    plt.savefig(RESULTS / "priority_vs_normal_rtt.png", dpi=200)
    plt.close()
    print(f"Saved {RESULTS / 'priority_vs_normal_rtt.png'}")


if __name__ == "__main__":
    main()
