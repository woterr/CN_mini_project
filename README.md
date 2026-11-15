# Multi-Client Chat Network

A multi-user chat application (Python TCP sockets + threading) running on a
Mininet network with an SDN controller that classifies users into tiers,
blocks unwanted hosts, and gives priority users a faster queue on the
bottleneck link — while the system is running.

## What it does

- **Chat**: registration, login, chat rooms, room messages, private messages,
  online-user tracking. One thread per client; see `docs/protocol.md`.
- **SDN policies** (`controller/chat_controller.py`, config in
  `controller/policy.json`):
  - **Queues on the bottleneck link** — priority tier → higher-priority queue,
    normal tier → limited queue (see the table below).
  - **Dynamic priority rooms** — when a `ROOM_JOIN` / `ROOM_LEAVE` arrives
    from the chat server for a priority room (`vip`), that user's traffic
    moves to or from the priority queue **while the system is running**.
  - **Blocked users** — blocked hosts are dropped at the switch; they cannot
    even connect to the server.
  - **Readable controller log** — every policy decision is logged with the
    host, tier, queue and reason (`[POLICY] ...` lines).
- **Comparison** — the same topology runs against a plain learning-switch
  controller (`controller/baseline_controller.py`) so the policies' effect
  is measurable.

## Requirements

- Python 3 (chat server/client: standard library only)
- Ryu with OpenFlow 1.3 (bundled in `ryu-env/`)
- Mininet and Open vSwitch (for the network experiments)

## Quick start (local, no Mininet)

Terminal 1 — start the server:

```bash
python3 server/chat_server.py
```

Terminal 2 (and more for extra users) — connect a client:

```bash
CHAT_HOST=127.0.0.1 python3 client/chat_client.py
```

Ports: chat `5000`, room events `6000`, OpenFlow controller `6653`.

### Chat commands

| Command | Description |
|---|---|
| `REGISTER <user> <pass>` / `LOGIN <user> <pass>` | Account management |
| `CREATE <room>` / `JOIN <room>` / `LEAVE <room>` | Rooms |
| `MSG <room> <text>` | Send to a room |
| `PM <user> <text>` | Private message |
| `USERS` / `ROOMS` | Who's online / which rooms exist |
| `QUIT` | Disconnect |

## The SDN network

`topology/topology.py` builds:
(to be changed and replaced using cisco packet tracer ss)
```
c1..cN ──┐
         ├── s1 ══ 5 Mbps, 10 ms ══ s2 ── server (10.0.0.10)
ctrl ────┘
```

The `s1↔s2` link is the bottleneck. Two HTB queues live on both of its
ports:

| Queue | Tier | Guaranteed | May use up to |
|---:|---|---:|---:|
| 0 | normal | 0.5 Mbps | full 5 Mbps (borrows when priority is idle) |
| 1 | priority | 3 Mbps | full 5 Mbps |

So nobody is throttled when the link is idle — but under congestion the
priority tier keeps its 3 Mbps share and the normal tier yields.

The controller classifies chat traffic (source IP + TCP port 5000) into
these queues. Tiers are configured in `controller/policy.json`:

```json
{
  "priority_rooms": ["vip"],
  "default_tier": "normal",
  "hosts": {
    "10.0.0.1": "priority",
    "10.0.0.2": "normal",
    "10.0.0.3": "normal",
    "10.0.0.4": "blocked"
  }
}
```

Hosts not listed get the `default_tier`. The chat server tells the
controller about room joins/leaves on port 6000; while a user is in a
priority room, their traffic rides the priority queue — live, no restart.

## Run on Mininet

Start the controller, then the topology:

```bash
ryu-env/bin/ryu-manager controller/chat_controller.py   # terminal 1
sudo python3 topology/topology.py 25                    # terminal 2 (10/25/50/100)
```

In the Mininet CLI, start the server (it needs the controller address so its
room events reach it):

```
mininet> server bash -c 'CONTROLLER_HOST=10.0.0.254 python3 -u server/chat_server.py > /tmp/chat_server.log 2>&1 &'
mininet> xterm c1 c2 c3
```

Then chat from the client terminals with `python3 client/chat_client.py`.
Watch the controller terminal: every room join/leave is logged together with
the policy applied and the queue chosen.

## Experiments

The orchestrator automates everything — topology, controller, chat server,
one automated client per host, CSV output:

```bash
# comparison (same workload on both controllers)
sudo python3 experiments/run_mininet.py --setup ours --count 25 \
    --messages 20 --size 1000 --runs 3 --priority \
    --output experiments/results/compare_ours_25clients.csv
sudo python3 experiments/run_mininet.py --setup baseline --count 25 \
    --messages 20 --size 1000 --runs 3 --priority \
    --output experiments/results/compare_baseline_25clients.csv

# priority vs normal under load (1 priority user vs 13 normal users)
sudo python3 experiments/run_mininet.py --setup ours --count 15 \
    --messages 50 --size 1000 --runs 3 --priority --prefix norm \
    --output experiments/results/priority_load.csv
```

Notes:

- `--priority` adds one priority-tier user on `c1` (joining `vip`) in both
  setups, so results can be split by tier (`pri*` vs `norm*` usernames).
- `c1` (priority tier) and `c4` (blocked — it intentionally cannot connect)
  are excluded from the load batches.
- 100-client runs work but are slow: the 5 Mbps bottleneck serializes
  ~2 MB of offered load per sweep, and a lost message in a few clients
  under peak congestion is normal.
- Plots: `python3 experiments/plot_comparison.py` (baseline vs policy)
  and `python3 experiments/plot_priority.py
  experiments/results/priority_load_run*.csv` (priority vs normal RTT).

Full procedures, result tables and discussion: [docs/architecture.md](docs/architecture.md).

## Results so far

Baseline (plain learning switch, Mininet, 5 messages per client — details
in `docs/architecture.md` §3.1):

| Concurrent clients | Successful | Average RTT (ms) | Avg connection setup (ms) |
|---:|---:|---:|---:|
| 10 | 50/50 | 72.174 | 122.560 |
| 25 | 125/125 | 83.452 | 291.304 |
| 50 | 250/250 | 82.845 | 2368.849 |

RTT stayed flat but connection setup exploded with load — the learning
switch has no way to protect anyone from the congestion.
The priority-policy comparison and priority-vs-normal results are being
produced with the commands above (placeholder tables in
`docs/architecture.md` §3.2/§3.3).

## Screenshots

### Chat Server

![Chat Server](https://github.com/user-attachments/assets/5b7dc790-6e89-4aeb-b650-fc48d0fdd1bf)

### Chat Client

![Chat Client](https://github.com/user-attachments/assets/8263b009-7761-4c28-91a9-527c65f8eac0)

## Limitations

- Accounts and rooms are in memory; they reset when the server restarts.
- Queues and policies are only enforced on the Mininet bottleneck link —
  local testing has no SDN path.
- Room notifications require the controller to be running when the server
  reports them.
