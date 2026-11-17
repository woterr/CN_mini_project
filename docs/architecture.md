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
  | 0 | everything else | goto table 1 | L2 traffic (ARP, pings, non-chat packets) |

  Every port-5000 rule is installed twice: once for the client-to-server
  direction (`ipv4_src=<client>`, `tcp_dst=5000`) and once for the
  server-to-client direction (`ipv4_dst=<client>`, `tcp_src=5000`). Both
  halves of a chat round trip cross the bottleneck, so both must be
  assigned to the client's queue; classifying only requests lets the
  reply wait behind normal traffic.

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

- **ROOM_JOIN** installs a `priority=260` pair of flows sending that
  user's chat traffic (requests and replies) to the priority queue
  *while the system is running* — no restart, no reconnection.
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
    --messages 20 --size 1000 --runs 3 --priority --prefix norm \
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
       --messages 20 --size 1000 --csv experiments/results/priority_load_run1.csv
   # on c2, c3, ... (normal tier):
   python3 client/chat_client.py --auto --username norm1 --room room1 \
       --messages 20 --size 1000 --csv experiments/results/priority_load_run1.csv
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

### 3.2 Comparison at scale: baseline vs. priority policy

Matched baseline runs are available for all four client counts, using
`--count N --messages 20 --size 1000 --runs 3`. The table below covers
normal-batch users only (the `pri1` priority user is analysed in §3.3).

| Concurrent clients | Successful messages | Average RTT (ms) | Avg connection setup (ms) |
|---:|---:|---:|---:|
| 10 | 480 | 97.901 | 88.730 |
| 25 | 1380 | 866.233 | 134.671 |
| 50 | 2875 | 3478.923 | 711.358 |
| 100 | 5205 | 11188.134 | 2362.598 |

The matched 100-client comparison used both setups with
`--count 100 --messages 20 --size 1000 --runs 3`.

Averages below are calculated across successful message rows in each
combined CSV.

| Setup | Successful / total rows | Success rate | Average RTT (ms) | Avg connection setup (ms) |
|---|---:|---:|---:|---:|
| Baseline (no tiers) | 5265/5280 | 99.72% | 11188.134 | 2362.598 |
| Our controller (tiered queues) | 3558/3560 | 99.94% | 6522.144 | 9332.785 |

At 100 clients, the controller run had approximately 41.7% lower average
RTT, while connection setup time was approximately 4.0× higher
(295%).

The `--count` argument includes the separately configured `c1` priority
host and `c4` blocked host, so the topology has 98 normal automated
client hosts. At 100 clients some clients time out under saturation and
offer fewer messages; the CSVs contain 98 distinct baseline usernames and
87 distinct policy usernames. Averages are over the messages that
completed, so the comparison is per-message RTT rather than throughput.

The historical baseline results in §3.1 used 5 messages per client and
are retained for reference only. The matched runs above use 20 messages
per client and 3 runs, and are the source for the comparison plots.

The baseline topology still uses the same 5 Mbps / 10 ms Mininet
bottleneck; it simply has no OpenFlow queues. The flat 25/50 baseline
curve in §3.1 is caused by the 5-short-message workload, not by a missing
rate limit.

Averages are calculated over successful messages only. Generate the
comparison plots with `python3 experiments/plot_comparison.py`.

### 3.3 Priority vs. normal RTT under load

The priority-load experiment used our controller with one priority user
(`c1`) and 13 normal users. It used 20 messages of approximately 1000
bytes per user over 3 runs.

| Group | Successful messages | Average RTT (ms) |
|---|---:|---:|
| Priority tier (queue 1) | 60 | 20.373 |
| Normal tier (queue 0) | 780 | 270.915 |

In this concurrent run the priority tier was about 92.5% faster. The
controller classifies chat traffic in both directions: the request
(`ipv4_src=<client>, tcp_dst=5000`) and the server reply
(`ipv4_dst=<client>, tcp_src=5000`) both use the client's queue. This
matters because each normal message is broadcast to the other room
members, so the return path carries most of the load.

Generate the plot with:

`python3 experiments/plot_priority.py experiments/results/priority_load_run*.csv`

The plot is saved as `experiments/results/priority_vs_normal_rtt.png`.
These results describe a separate priority-load experiment and should
not be directly compared with the 100-client comparison in §3.2 because
the workload and traffic groups differ.

## 4. Discussion

**Baseline (historical 5-message runs in §3.1).** Average RTT stayed
around 83 ms from 25 to 50 clients, but connection setup time exploded
from 291 ms (25 clients) to 2369 ms (50 clients): with one 5 Mbps
bottleneck and a learning switch, the TCP handshakes plus per-connection
flow installation compete with everyone else's traffic once enough
clients start at the same time. With the matched 20-message workload the
baseline rises from 97.9 ms at 10 clients to 11.2 s at 100 clients as the
bottleneck saturates.

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
- *Classification is per user, not per flow*: matching the user's IP
  with TCP port 5000 in both directions means every message and reply is
  classified without per-message controller involvement — the RTT
  overhead of the policy is a small fixed flow set per user, not one
  flow per message.

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
- The 100-client connection setup times (2.4 s baseline, 9.3 s policy)
  include SYN retransmission backoff under saturation (1 s, 2 s, 4 s, ...).
  They are not caused by a small server backlog: Python/Linux uses a
  backlog of 4096 here. Staggering client starts would reduce the initial
  SYN burst but would also change the workload, so both setups launch all
  clients together.
- The priority-load CSVs in this repository were produced after the
  controller gained bidirectional classification, so the priority request
  and the server reply both use queue 1.
- With more than 4 clients, `c4` stays blocked by policy — exclude it from
  load runs (its client intentionally cannot connect).
