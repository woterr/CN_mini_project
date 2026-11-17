#!/usr/bin/env bash
# The two 100-client comparison runs (both setups), then regenerate plots.
set -e

cd /mnt/shared/Academic/CN/CN_MINI/repo

sudo python3 experiments/run_mininet.py --setup ours --count 100 \
    --messages 20 --size 1000 --runs 3 --priority --timeout 1200 \
    --output experiments/results/compare_ours_100clients.csv

sudo python3 experiments/run_mininet.py --setup baseline --count 100 \
    --messages 20 --size 1000 --runs 3 --priority --timeout 1200 \
    --output experiments/results/compare_baseline_100clients.csv

python3 experiments/plot_comparison.py --counts 10 25 50 100
python3 experiments/plot_baseline.py
python3 experiments/plot_priority.py \
    experiments/results/priority_load_run1.csv \
    experiments/results/priority_load_run2.csv \
    experiments/results/priority_load_run3.csv \
    --baseline experiments/results/priority_load_baseline.csv

echo "100-client runs and plots finished."
