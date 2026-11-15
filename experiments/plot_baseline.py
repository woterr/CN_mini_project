"""Plot baseline (plain learning switch) RTT and connection setup time
vs. the number of clients.

Reads every  experiments/results/baseline_<n>clients.csv  file found
(e.g. baseline_10clients.csv, baseline_25clients.csv, ...) and plots the
average over successful messages for each client count.

Output:

    experiments/results/baseline_rtt.png
    experiments/results/baseline_connection_setup.png
"""

import csv
import re
import statistics
import sys
from pathlib import Path

import matplotlib.pyplot as plt

RESULTS = Path(__file__).resolve().parent / "results"


def load_column(column):
    """Return ([client counts], [column averages]) over all baseline CSVs."""
    points = []

    for path in RESULTS.glob("baseline_*clients.csv"):
        match = re.fullmatch(r"baseline_(\d+)clients", path.stem)

        if not match:
            continue

        with open(path, newline="") as f:
            rows = [r for r in csv.DictReader(f) if r["status"] == "SUCCESS"]

        if rows:
            points.append(
                (int(match.group(1)),
                 statistics.mean(float(r[column]) for r in rows)))

    points.sort()
    return [c for c, _ in points], [v for _, v in points]


def plot(column, ylabel, outfile, log_scale=False):
    counts, values = load_column(column)

    if not counts:
        sys.exit(f"No baseline_*clients.csv data found for {column!r}.")

    plt.figure()
    plt.plot(counts, values, marker="o", color="#1f77b4",
             label="Baseline (learning switch)")

    for count, value in zip(counts, values):
        plt.annotate(f"{value:.2f}", (count, value),
                     textcoords="offset points", xytext=(0, 8),
                     ha="center", fontsize=8)

    if log_scale:
        plt.yscale("log")

    plt.margins(y=0.15)
    plt.xticks(counts)
    plt.xlabel("Concurrent clients")
    plt.ylabel(ylabel)
    plt.title(f"Baseline: {ylabel} vs. number of clients")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.savefig(outfile, dpi=200)
    plt.close()

    for count, value in zip(counts, values):
        print(f"  {count:>4} clients: {value:.3f} {ylabel}")
    print(f"Saved {outfile}\n")


def main():
    print("Average RTT:")
    plot("rtt_ms", "Average RTT (ms)", RESULTS / "baseline_rtt.png")

    print("Connection setup time:")
    # Spans ~120 ms to ~2400 ms; log scale keeps all points readable.
    plot("connection_setup_ms", "Connection Setup Time (ms)",
         RESULTS / "baseline_connection_setup.png", log_scale=True)


if __name__ == "__main__":
    main()
