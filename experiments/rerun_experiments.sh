#!/usr/bin/env bash
# Reduced sweep: matched comparison up to 50 clients (the trend is fully
# visible by 50), plus the priority-load runs for the third chart.
set -e

cd "$(dirname "$0")/.."   # repo root

# ours 10/25/50 already completed in this session and are kept.

# baseline (plain learning switch), 10/25/50 clients
sudo python3 experiments/run_mininet.py --setup baseline --count 10 \
    --messages 20 --size 1000 --runs 3 --priority \
    --output experiments/results/compare_baseline_10clients.csv

sudo python3 experiments/run_mininet.py --setup baseline --count 25 \
    --messages 20 --size 1000 --runs 3 --priority \
    --output experiments/results/compare_baseline_25clients.csv

sudo python3 experiments/run_mininet.py --setup baseline --count 50 \
    --messages 20 --size 1000 --runs 3 --priority \
    --output experiments/results/compare_baseline_50clients.csv

# priority vs normal under load (ours): pri1 on queue 1, norm1..13 on queue 0
sudo python3 experiments/run_mininet.py --setup ours --count 15 \
    --messages 20 --size 1000 --runs 3 --priority --prefix norm \
    --output experiments/results/priority_load.csv

# same workload against the baseline (no tiers): the pri1 user there
# behaves like a normal user, giving the "same user, baseline" bar
sudo python3 experiments/run_mininet.py --setup baseline --count 15 \
    --messages 20 --size 1000 --runs 3 --priority --prefix norm \
    --output experiments/results/priority_load_baseline.csv

# plots (only counts with matched data on both sides: 10/25/50)
python3 experiments/plot_comparison.py --counts 10 25 50
python3 experiments/plot_priority.py \
    experiments/results/priority_load_run1.csv \
    experiments/results/priority_load_run2.csv \
    experiments/results/priority_load_run3.csv \
    --baseline experiments/results/priority_load_baseline.csv

echo "Reduced sweep finished."
