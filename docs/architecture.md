# Multi-Client Chat Network — Architecture and Evaluation

Final documentation for the CN mini project: architecture, SDN design, how to
run everything, and results/discussion. The wire protocol is specified in
[`docs/protocol.md`](protocol.md).

## 1. Architecture

```text
                 Ryu controller (ryu-manager)
        OpenFlow 1.3 : 6653          room events : 6000
        |                                   |
        | (management intf 10.0.0.254)      |
        v                                   v
  c1..cN                                +------+
    |        +----+   bottleneck   +----+|server|
    +-------| s1  |--5 Mbps------| s2 |-+------+
            +----+  queues 0/1   +----+
   clients on s1                chat server on s2
```

| Component | File | Responsibility |
|---|---|---|
| Chat server | `server/chat_server.py` | Threaded TCP server on port 5000; registration, login, rooms, PM, listings; background worker that sends ROOM_JOIN/ROOM_LEAVE events to the controller |
| Chat client | `client/chat_client.py` | One thread for receiving, one for sending; `--auto` mode sends N messages, measures RTT and connection setup time, writes CSV |
| SDN controller | `controller/chat_controller.py` | L2 learning switch + classification and policy enforcement (tiers, queues, blocking, dynamic priority rooms) |
| Policy config | `controller/policy.json` | Host tiers, default tier, priority rooms |
| Baseline controller | `controller/baseline_controller.py` | Plain L2 learning switch (no policies, no queues) |
| Topology (tiered queues) | `topology/topology.py` | s1–s2 topology, bottleneck link, OpenFlow queues, optional client count |
| Topology (baseline) | `topology/baseline_topology.py` | Same bottleneck link, no queues, scalable client count |
| Experiments | `experiments/run_clients.py` | Launches N auto clients, repeats runs, saves CSVs |
| Plots | `experiments/plot_*.py` | RTT / connection-setup graphs, comparison and priority plots |

### Chat server

- A single TCP listener on port 5000; every client connection gets its own
  thread.
- Shared state (`users`, `rooms`, `online_users`) is guarded by one lock.
- SDN notifications are pushed onto a queue and delivered by a background
  worker thread, so chat handling never blocks on controller I/O.

### SDN controller pipeline

Two OpenFlow 1.3 tables on every switch:

- **Table 0 — classification** (matches source IP and TCP destination port
  5000):

  | Priority | Match | Action | Why |
  |---:|---|---|---|
  | 300 | blocked host IP (any IPv4) | drop | user policy: blocked users cannot connect |
  | 260 | priority-room member IP, port 5000 | `set_queue:1` | dynamic room policy |
  | 200 / 100 | tier host IP, port 5000 | `set_queue:1` / `set_queue:0` | static user tier |
  | 50 | any host, port 5000 | `set_queue:0` | `default_tier` for hosts not listed in `policy.json` |
  | 0 | everything else | goto table 1 | L2 traffic (ARP, pings, server replies) |

- **Table 1 — forwarding**: MAC-learning L2 switch (flows with 60 s idle
  timeout, flood for unknown/broadcast destinations).

### Queues on the bottleneck link

`topology/topology.py` creates two `linux-htb` queues on both ports of the
5 Mbps bottleneck link (via `ovs-vsctl`):

| Queue | Tier | Min rate | Max rate |
|---:|---|---:|---:|
| 0 | normal (limited queue) | 0.5 Mbps | 5 Mbps (link rate) |
| 1 | priority (higher-priority queue) | 3 Mbps | 5 Mbps (link rate) |

No tier is hard-capped below the link rate: a queue may borrow spare
capacity, so a tier is only slowed when the other tier actually competes
for the link. The "limited" nature of the normal tier is its much
smaller guaranteed share (0.5 vs 3 Mbps), which HTB honours under
contention. OVS installs its own HTB root qdisc on the bottleneck ports
(replacing the netem delay qdisc TCLink configured), so `configure_queues`
re-attaches the 10 ms link delay as a netem child qdisc under each HTB
class — both experiment setups then share the same 5 Mbps / 10 ms
bottleneck. The controller only assigns traffic to queues
(`OFPActionSetQueue`); the topology owns queue creation.

### Dynamic behaviour

The server cannot see room names inside the TCP stream, so it tells the
controller: `ROOM_JOIN <user_ip> <room>` / `ROOM_LEAVE <user_ip> <room>` on
port 6000. When the room is a priority room:

- **ROOM_JOIN** installs a `priority=260` flow sending that user's chat
  traffic to the priority queue *while the system is running* — no restart,
  no reconnection.
- **ROOM_LEAVE** (last priority room) deletes the flow, so traffic falls
  back to the user's tier queue.
- Blocked users are never moved: their traffic stays dropped, and the
  controller logs why.

Every decision is printed to the controller log:

```text
Policy: 10.0.0.2 tier=normal (static queue 0)
[POLICY] switch 0000000000000001: 10.0.0.4 tier=blocked -> all IPv4 traffic dropped at the switch
[EVENT ] ROOM_JOIN 10.0.0.2 vip
[POLICY] 10.0.0.2 joined priority room 'vip' (tier=normal) -> chat traffic moved to priority queue 1 while running
[POLICY] 10.0.0.2 left last priority room (was in 'vip') -> chat traffic returned to normal queue 0 (limited) (tier=normal)
```

## 2. How to run

All commands run from the project root. The SDN parts need the bundled
Ryu environment (`source ryu-env/bin/activate`) and a Linux VM with
Mininet (root for `sudo python3 topology/...`).

### 2.1 Local (no Mininet)

```bash
python3 server/chat_server.py                     # terminal 1
CHAT_HOST=127.0.0.1 python3 client/chat_client.py # terminal 2+
```

### 2.2 Policy setup: controller + queues + topology

```bash
source ryu-env/bin/activate
ryu-manager controller/chat_controller.py         # terminal 1
sudo python3 topology/topology.py                 # terminal 2 (4 clients, policy demo)
sudo python3 topology/topology.py 25              # scaled topology for load tests
```

The topology configures the queues and prints `Controller management
address: 10.0.0.254`. Start the server inside Mininet so its events reach
the controller:

```text
mininet> server bash -c 'CONTROLLER_HOST=10.0.0.254 python3 -u server/chat_server.py > /tmp/chat_server.log 2>&1 &'
```

Then run `python3 client/chat_client.py` inside client hosts (`xterm`).
`c4` (10.0.0.4) is blocked and cannot connect — that is the policy working.

### 2.3 Baseline: plain learning switch

```bash
source ryu-env/bin/activate
ryu-manager controller/baseline_controller.py     # terminal 1
sudo python3 topology/baseline_topology.py 25     # terminal 2 (same bottleneck, no queues)
```

The baseline server uses the same IP as the main server (10.0.0.10), so the client
default works unchanged. The baseline controller has no room listener, so
the server logs `[SDN] Controller unavailable ...` for room events —
expected and harmless.

### 2.4 Comparison experiments (baseline vs. priority policy)

Both setups are run by the orchestrator `experiments/run_mininet.py`
(root), which builds the topology, starts the matching controller and the
chat server, and launches one auto client per host (`c1` priority tier and
`c4` blocked are excluded from the load batch):

```bash
sudo python3 experiments/run_mininet.py --setup ours --count 25 \
    --messages 20 --size 1000 --runs 3 --priority \
    --output experiments/results/compare_ours_25clients.csv
sudo python3 experiments/run_mininet.py --setup baseline --count 25 \
    --messages 20 --size 1000 --runs 3 --priority \
    --output experiments/results/compare_baseline_25clients.csv
```

Each run writes `compare_<setup>_<n>clients_run<k>.csv` plus a combined
`compare_<setup>_<n>clients.csv`. The standardized parameters for the
comparison are 20 messages of ~1000 bytes per client, 3 runs, counts
10/25/50/100, and `--priority` (a priority user on `c1` joins `vip` in
*both* setups, so RTT can be split by tier: `pri*` vs `norm*`). The
normal batch uses the remaining hosts (`c1` priority tier and `c4`
blocked are excluded from it). Historical one-off runs (5 short messages
per client) are kept under `baseline_<n>clients.csv` and are not
overwritten.

> The room must exist before the auto clients join: create it once from an
> interactive client (`CREATE room1`).

### 2.5 Priority vs. normal experiment (our controller running)

The orchestrator runs the whole experiment in one command — it starts a
priority-tier user on `c1` (joining `vip`) and the normal batch on the
remaining hosts (joining `room1`) concurrently:

```bash
sudo python3 experiments/run_mininet.py --setup ours --count 15 \
    --messages 50 --size 1000 --runs 3 --priority --prefix norm \
    --output experiments/results/priority_load.csv
```

This produces `priority_load_run1..3.csv` and a combined
`priority_load.csv`, with usernames `pri1` (priority tier) and
`norm1..13` (normal tier). Manually, the same experiment is:

1. Start our controller + topology + server (2.2), with enough normal
   clients to congest the bottleneck.
2. From an interactive client: `CREATE vip` and `CREATE room1`.
3. Start the priority-tier user (`c1`, tier `priority` or any user who
   joins `vip`) with the priority prefix, and normal users with the normal
   prefix, concurrently:

   ```bash
   # on c1 (priority tier):
   python3 client/chat_client.py --auto --username pri1 --room vip \
       --messages 30 --csv experiments/results/priority_load_run1.csv
   # on c2, c3, ... (normal tier):
   python3 client/chat_client.py --auto --username norm1 --room room1 \
       --messages 30 --csv experiments/results/priority_load_run1.csv
   ```

   To launch several users at once with the right prefix, use
   `experiments/run_clients.py --prefix pri --room vip` and
   `--prefix norm --room room1` (append to the same CSV per run with
   `--runs` for repetitions).
4. Plot:

   ```bash
   python3 experiments/plot_priority.py experiments/results/priority_load_run*.csv
   ```

### 2.6 Plots

```bash
python3 experiments/plot_baseline.py     # baseline RTT + connection setup vs. clients
python3 experiments/plot_comparison.py   # RTT + connection setup vs. clients (baseline vs. priority policy)
python3 experiments/plot_priority.py experiments/results/priority_load_run*.csv
```

Outputs land in `experiments/results/` (`comparison_rtt.png`,
`comparison_connection_setup.png`, `priority_vs_normal_rtt.png`).

## 3. Results

### 3.1 Baseline (plain learning switch), Mininet, 5 Mbps bottleneck

| Concurrent clients | Total messages | Successful | Average RTT (ms) | Avg connection setup (ms) |
|---:|---:|---:|---:|---:|
| 10 | 50 | 50 | 72.174 | 122.560 |
| 25 | 125 | 125 | 83.452 | 291.304 |
| 50 | 250 | 250 | 82.845 | 2368.849 |

### 3.2 Comparison at scale: baseline vs. priority policy (to be filled)

Run the standardized comparison of §2.4 for counts 10/25/50/100 (both
setups include the `pri1` priority user so RTT can be split by tier),
then fill in the table below from the combined CSVs:

| Concurrent clients | Setup | Successful / total | Average RTT (ms) | Avg connection setup (ms) |
|---:|---|---:|---:|---:|
| 10 | Baseline (no tiers) | — | — | — |
| 10 | Priority policy (tiered queues) | — | — | — |
| 25 | Baseline (no tiers) | — | — | — |
| 25 | Priority policy (tiered queues) | — | — | — |
| 50 | Baseline (no tiers) | — | — | — |
| 50 | Priority policy (tiered queues) | — | — | — |
| 100 | Baseline (no tiers) | — | — | — |
| 100 | Priority policy (tiered queues) | — | — | — |

Notes for whoever runs this:

- With the current queue configuration neither tier is hard-capped below
  the link rate, so normal users should be close to baseline while the
  priority user stays fast under load.
- Averages over successful messages only; `plots: python3
  experiments/plot_comparison.py`.
- The 100-client runs are slow (a saturated run takes minutes — the
  5 Mbps bottleneck serializes ~2 MB of offered load per sweep), so
  expect long wall-clock times, and a lost message in a few clients
  under peak congestion is normal.

### 3.3 Priority vs. normal RTT under load (to be filled)

Run the §2.5 experiment (our controller, 1 priority user on `c1` in
`vip` + 13 normal users flooding `room1`, 50 messages of ~1000 bytes
each, 3 runs), then fill in:

| Group | Messages | Average RTT (ms) |
|---|---:|---:|
| Priority tier (queue 1) | — | — |
| Normal tier (queue 0) | — | — |

Expected result: the priority user's traffic keeps flowing through the
guaranteed 3 Mbps queue while the 13 normal users saturate their
queue — a large RTT difference. Plot with
`python3 experiments/plot_priority.py experiments/results/priority_load_run*.csv`
(a log-scale y axis keeps the small priority bar visible). State the run
conditions next to the result: these runs use more messages than the
§3.2 comparison, so the numbers are not directly comparable.

## 4. Discussion

**Baseline (§3.1, historical 5-message runs).** Average RTT stayed around
83 ms from 25 to 50 clients, but connection setup time exploded from
291 ms (25 clients) to 2369 ms (50 clients): with one 5 Mbps bottleneck
and a learning switch, the TCP handshakes plus per-connection flow
installation compete with everyone else's traffic once enough clients
start at the same time.

**What the controller changes.**

- *Blocking*: `c4`'s traffic is dropped in table 0 of the switch — it never
  reaches the server, so a blocked user cannot connect at all, without the
  server spending resources on it.
- *Queues*: normal-tier chat traffic shares a queue with only a
  0.5 Mbps guarantee while priority traffic keeps a guaranteed
  3 Mbps share (both may borrow idle capacity up to the 5 Mbps link
  rate). So when the link is idle, nobody is throttled; when it is
  congested, the priority tier keeps most of the bandwidth and the
  normal tier yields.
- *Dynamic rooms*: joining `vip` moves a user's traffic into the priority
  queue immediately (one flow, priority 260, `set_queue:1`); leaving the
  last priority room moves it back. The upgrade path is per user and needs
  no topology or controller restart.
- *Classification is per user, not per flow*: matching source IP +
  TCP port 5000 means every message from a user is classified without
  per-message controller involvement — the RTT overhead of the policy is
  one flow install per join/leave, not per message.

**Threats to validity / notes.**

- Local (non-Mininet) numbers (§"Performance Test Results" in the README)
  measure only server-side threading, not the network; the Mininet tables
  are the meaningful ones.
- On the bottleneck ports, OVS installs its own HTB qdisc, which would
  replace the link's netem delay; `configure_queues` re-attaches the
  10 ms delay as a child qdisc under the HTB classes so both experiment
  setups share the same 5 Mbps / 10 ms bottleneck.
- Averages over successful messages only. Under peak congestion a
  single message can be lost occasionally (TCP buffer pressure);
  report and discuss any losses.
- With more than 4 clients, `c4` stays blocked by policy — exclude it from
  load runs (its client intentionally cannot connect).
