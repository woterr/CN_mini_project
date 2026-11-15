"""Plot RTT and connection setup time vs. number of clients,
baseline (plain learning switch) vs. the controller with tiered queues.

Expects CSV files named like:

    experiments/results/compare_baseline_10clients.csv
    experiments/results/compare_ours_10clients.csv

for each client count in CLIENT_COUNTS (produced by
experiments/run_mininet.py with --setup baseline / --setup ours).
Client counts with no file (for either setup) are skipped. Output:

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
SERIES = {"baseline": ("Baseline (no tiers)", "compare_baseline"),
          "ours": ("Priority policy (tiered queues)", "compare_ours")}


def avg(filename, column):
    with open(filename, newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["status"] == "SUCCESS"]
    return statistics.mean(float(r[column]) for r in rows) if rows else None


def series_avg(setup, count, column):
    _, prefix = SERIES[setup]
    path = RESULTS / f"{prefix}_{count}clients.csv"
    if not path.exists():
        return None
    return avg(path, column)


def plot(column, ylabel, outfile, log_scale=False):
    counts = {s: [] for s in SERIES}
    values = {s: [] for s in SERIES}

    for count in CLIENT_COUNTS:
        for setup in SERIES:
            value = series_avg(setup, count, column)
            if value is not None:
                counts[setup].append(count)
                values[setup].append(value)

    if not any(values.values()):
        sys.exit(f"No input CSVs found for {column!r}; nothing to plot.")

    plt.figure()
    colors = {"baseline": "#1f77b4", "ours": "#d62728"}

    for setup in SERIES:
        if values[setup]:
            plt.plot(counts[setup], values[setup], marker="o",
                     color=colors[setup], label=SERIES[setup][0])

    all_counts = sorted({c for c_list in counts.values() for c in c_list})

    if log_scale:
        plt.xscale("log")
        plt.xticks(all_counts, [str(c) for c in all_counts])

    plt.xlabel("Concurrent clients")
    plt.ylabel(ylabel)
    plt.title(f"{ylabel} vs. number of clients")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.savefig(outfile, dpi=200)
    plt.close()

    for setup in SERIES:
        for c, v in zip(counts[setup], values[setup]):
            print(f"{SERIES[setup][0]:>36} {c:>4} clients: {v:.3f} {ylabel}")
    print(f"Saved {outfile}\n")


def main():
    # Connection setup grows by orders of magnitude; log scale keeps all
    # points readable.
    plot("rtt_ms", "Average RTT (ms)", RESULTS / "comparison_rtt.png")
    plot("connection_setup_ms", "Connection Setup Time (ms)",
         RESULTS / "comparison_connection_setup.png", log_scale=True)


if __name__ == "__main__":
    main()
