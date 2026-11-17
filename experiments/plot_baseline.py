"""Plot baseline (plain learning switch) RTT and connection setup time
vs. the number of clients.

Reads ``experiments/results/baseline_<n>clients.csv`` (and
``compare_baseline_<n>clients.csv`` when present).  Matched 20-message
measurements exist for 10, 25, 50 and 100 clients.  Older 5-short-message
runs are only plotted as a separate series for counts without matched
data.

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
MATCHED_COUNTS = {100}


def load_column(prefix, column):
    """Return ({client count: average}) over successful messages."""
    points = {}

    for path in RESULTS.glob(f"{prefix}_*clients.csv"):
        match = re.fullmatch(rf"{re.escape(prefix)}_(\d+)clients", path.stem)
        if not match:
            continue

        with open(path, newline="") as f:
            rows = [r for r in csv.DictReader(f)
                    if r["status"] == "SUCCESS"
                    and not r["username"].startswith("pri")]
        if rows:
            points[int(match.group(1))] = statistics.mean(
                float(r[column]) for r in rows)

    return points


def split_points(column):
    """Return (matched, historical) as sorted (counts, values) pairs."""
    matched = load_column("compare_baseline", column)
    historical = {}

    for count, value in load_column("baseline", column).items():
        if count in matched:
            continue
        if count in MATCHED_COUNTS:
            # The matched 100-client baseline was saved under the old name.
            matched[count] = value
        else:
            historical[count] = value

    def pairs(points):
        ordered = sorted(points.items())
        return [c for c, _ in ordered], [v for _, v in ordered]

    return pairs(matched), pairs(historical)


def plot(column, ylabel, outfile, log_scale=False):
    (m_counts, m_values), (h_counts, h_values) = split_points(column)

    if not m_counts and not h_counts:
        sys.exit(f"No baseline CSV data found for {column!r}.")

    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    handles = []

    if h_counts:
        h_line, = ax.plot(
            h_counts, h_values, marker="s", linestyle="--", color="#7f7f7f",
            markerfacecolor="white", markeredgecolor="#7f7f7f",
            label="Baseline (historical: 5 short msgs/client)")
        handles.append(h_line)
        for count, value in zip(h_counts, h_values):
            ax.annotate(f"{value:.0f}", (count, value),
                        textcoords="offset points", xytext=(0, 8),
                        ha="center", fontsize=8, color="#666666")

    if m_counts:
        m_line, = ax.plot(
            m_counts, m_values, marker="o", linestyle="-", color="#1f77b4",
            label="Baseline (matched: 20 msgs/client, 3 runs)")
        handles.append(m_line)
        for count, value in zip(m_counts, m_values):
            ax.annotate(f"{value:.0f}", (count, value),
                        textcoords="offset points", xytext=(0, 9),
                        ha="center", fontsize=8, color="#1f77b4")

    if log_scale:
        ax.set_yscale("log")

    all_values = m_values + h_values
    ax.set_xlim(left=0, right=max(m_counts + h_counts) * 1.08)
    if log_scale:
        ax.set_ylim(min(all_values) * 0.8, max(all_values) * 1.25)
    else:
        ax.set_ylim(0, max(all_values) * 1.12)
    ax.set_xticks(sorted(set(m_counts + h_counts)))
    ax.set_xlabel("Concurrent clients")
    ax.set_ylabel(ylabel)
    ax.set_title(f"Baseline: {ylabel} vs. number of clients")
    ax.grid(True, alpha=0.3)
    ax.legend(handles=handles, fontsize=8)

    if h_counts:
        fig.text(
            0.5, 0.01,
            f"The {'/'.join(map(str, h_counts))}-client historical runs used "
            "5 short messages per client; only the matched point(s) use the "
            "20-message workload.",
            ha="center", va="bottom", fontsize=7, color="#444444")
        fig.subplots_adjust(bottom=0.20)

    fig.savefig(outfile, dpi=200, bbox_inches="tight")
    plt.close(fig)

    for label, counts, values in (
            ("historical", h_counts, h_values),
            ("matched", m_counts, m_values)):
        for count, value in zip(counts, values):
            print(f"  {label:>10} {count:>4} clients: {value:.3f} {ylabel}")
    print(f"Saved {outfile}\n")


def main():
    print("Average RTT:")
    plot("rtt_ms", "Average RTT (ms)", RESULTS / "baseline_rtt.png")

    print("Connection setup time:")
    # Spans ~120 ms to ~7900 ms; log scale keeps all points readable.
    plot("connection_setup_ms", "Connection Setup Time (ms)",
         RESULTS / "baseline_connection_setup.png", log_scale=True)


if __name__ == "__main__":
    main()
