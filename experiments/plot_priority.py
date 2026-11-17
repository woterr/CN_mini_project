"""Plot priority-tier user RTT vs. normal-tier user RTT under load.

Input: one or more CSVs produced by run_clients.py with the --prefix
option, e.g. users named pri1... (priority tier) and norm1... (normal
tier). Users named auto... (no tier info) are treated as normal.

Optionally pass --baseline <csv> with the same workload run against the
plain learning switch; there the pri* user has no priority treatment,
so it is drawn as a third bar ("same user, baseline") and should sit
with the normal users.

Usage:

    python experiments/plot_priority.py \
        experiments/results/priority_load_run1.csv \
        [more CSVs ...] \
        [--baseline experiments/results/priority_load_baseline.csv]

Output:

    experiments/results/priority_vs_normal_rtt.png
"""

import argparse
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
BASELINE_COLOR = "#7f7f7f"


def group_of(username):
    for prefix, group in PREFIXES.items():
        if username.startswith(prefix):
            return group
    return None


def load_baseline(path):
    """Return (rtts, per-run averages, users) for pri* rows in the
    baseline CSVs (the same user, without tier treatment)."""
    rtts = []
    users = set()
    per_run = []

    for name in path:
        run_rtts = []
        with open(name, newline="") as f:
            for row in csv.DictReader(f):
                if row["status"] != "SUCCESS":
                    continue
                if not row["username"].startswith("pri"):
                    continue
                rtt = float(row["rtt_ms"])
                rtts.append(rtt)
                users.add(row["username"])
                run_rtts.append(rtt)
        if run_rtts:
            per_run.append(statistics.mean(run_rtts))

    return rtts, per_run, users


def main():
    parser = argparse.ArgumentParser(
        description="Plot priority-tier vs. normal-tier RTT under load")
    parser.add_argument("files", nargs="+",
                        help="CSVs from the policy run (pri*/norm*/auto* "
                             "users)")
    parser.add_argument("--baseline", nargs="+", metavar="CSV", default=[],
                        help="Optional CSVs from the same workload run "
                             "against the plain learning switch; the pri* "
                             "user there is drawn as an extra bar")
    args = parser.parse_args()
    files = args.files

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

    baseline_rtts, baseline_per_run, baseline_users = (
        load_baseline(args.baseline) if args.baseline else ([], [], set()))

    missing = [g for g in GROUPS if not rtts[g]]
    if missing:
        sys.exit(f"No RTT data for: {', '.join(missing)}. "
                 "Run run_clients.py with --prefix pri / --prefix norm.")

    labels = []
    values = []
    errors = []
    colors = []

    for group, label in GROUPS.items():
        values.append(statistics.mean(rtts[group]))
        errors.append(statistics.stdev(per_run[group])
                      if len(per_run[group]) > 1 else 0.0)
        labels.append(f"{label}\n{len(users[group])} user(s), "
                      f"{len(rtts[group])} msgs")
        colors.append(COLORS[group])
        print(f"{label}: {len(users[group])} users, "
              f"{len(rtts[group])} messages, "
              f"average RTT {values[-1]:.3f} ms")

    if baseline_rtts:
        label = ("Baseline (same user, no tiers)\n"
                 f"{len(baseline_users)} user(s), {len(baseline_rtts)} msgs")
        values.append(statistics.mean(baseline_rtts))
        errors.append(statistics.stdev(baseline_per_run)
                      if len(baseline_per_run) > 1 else 0.0)
        labels.append(label)
        colors.append(BASELINE_COLOR)
        print(f"Baseline (same user, no tiers): {len(baseline_users)} user, "
              f"{len(baseline_rtts)} messages, average RTT "
              f"{values[-1]:.3f} ms")

    n_priority = len(users["priority"])
    n_normal = len(users["normal"])
    msgs_per_user = len(rtts["normal"]) // max(n_normal * len(files), 1)

    title = (f"RTT under load: {n_priority} priority vs. {n_normal} "
             f"normal user{'s' if n_normal != 1 else ''}")
    if baseline_rtts:
        title += " + baseline run"

    fig, ax = plt.subplots(figsize=(7.0, 5.0))
    bars = ax.bar(
        labels, values,
        color=colors,
        yerr=errors if any(errors) else None,
        capsize=5 if any(errors) else 0)
    ax.bar_label(bars, fmt="%.2f ms", padding=6)
    ax.set_ylim(bottom=0)
    ax.set_ylabel("Average RTT (ms)")
    ax.set_title(title)

    fig.text(
        0.5, 0.01,
        f"{msgs_per_user} messages/user/run over {len(files)} run(s), "
        "~1000-byte messages. The priority user joins the priority room "
        "(vip); the normal users share room1 and provide the competing "
        "traffic when both batches run concurrently. Error bars show the "
        "spread of the per-run averages. "
        + ("The baseline bar is the same priority user workload run "
           "against the plain learning switch, where no tier treatment "
           "exists."
           if baseline_rtts else ""),
        ha="center", va="bottom", fontsize=7, color="#444444", wrap=True)
    fig.subplots_adjust(bottom=0.24)

    out = RESULTS / "priority_vs_normal_rtt.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
