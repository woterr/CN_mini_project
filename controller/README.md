# SDN controller

Ryu app for the chat network. It uses OpenFlow 1.3 and two tables:

- Table 0 classifies chat traffic by user in both directions: client to
  server (`nw_src`, `tp_dst=5000`) and server to client (`nw_dst`,
  `tp_src=5000`).
- Table 1 is a learning L2 switch.

Host tiers and priority rooms are read from `policy.json`:

```json
{
  "priority_rooms": ["vip"],
  "default_tier": "normal",
  "hosts": {
    "10.0.0.1": "priority",
    "10.0.0.2": "normal",
    "10.0.0.4": "blocked"
  }
}
```

`default_tier` (optional) is the tier used for hosts that are not listed in
`hosts` — in a 25/50/100-client load test, clients `c5` and above get this
tier's queue automatically.

## Policies

- **Blocked users**: a `priority=300` flow drops all IPv4 traffic from the
  host at the switch (user policy).
- **Priority tier**: chat traffic in both directions (source IP + TCP
  port 5000, and destination IP + TCP source port 5000) is sent to the
  higher-priority **queue 1** on the bottleneck link with `priority=200`
  flows.
- **Normal tier**: chat traffic in both directions is sent to the limited
  **queue 0** with `priority=100` flows. Queue 0 has only a 0.5 Mbps
  guarantee (queue 1 is guaranteed 3 Mbps) but may borrow idle capacity
  up to the full 5 Mbps link rate — so nobody is throttled when the link
  is idle, and the priority tier wins under congestion.
- **Priority rooms**: joining a priority room installs dynamic
  `priority=260` flows that send the user's chat traffic (requests and
  replies) to the priority queue while the system is running; leaving the
  last priority room deletes them, so traffic falls back to the tier
  queue. Blocked users are never moved.

The controller log shows every policy decision and why:

```text
Policy: default tier for unknown hosts = normal (queue 0)
Policy: 10.0.0.1 tier=priority (static queue 1)
[POLICY] switch 0000000000000001: 10.0.0.2 tier=normal -> chat traffic (both directions) sent to normal queue 0 (limited)
[POLICY] switch 0000000000000001: 10.0.0.4 tier=blocked -> all IPv4 traffic dropped at the switch
[EVENT ] ROOM_JOIN 10.0.0.2 vip
[POLICY] 10.0.0.2 joined priority room 'vip' (tier=normal) -> chat traffic moved to priority queue 1 while running
[EVENT ] ROOM_LEAVE 10.0.0.2 vip
[POLICY] 10.0.0.2 left last priority room (was in 'vip') -> chat traffic returned to normal queue 0 (limited) (tier=normal)
[POLICY] ROOM_JOIN 10.0.0.4 ignored: user is blocked, traffic stays dropped
```

Run from the project root:

```sh
ryu-manager controller/chat_controller.py
```

The controller reads `controller/policy.json` and listens on `0.0.0.0:6000`
for room events. In the Mininet topology the listener is reachable at
`10.0.0.254:6000`. The listener accepts one-line TCP messages from the chat
server:

```text
ROOM_JOIN <user_ip> <room>
ROOM_LEAVE <user_ip> <room>
```

Queues 0 (normal, limited guarantee) and 1 (priority) are created on the
bottleneck link ports by `topology/topology.py` at startup. Verify the
queue assignment with:

```sh
ovs-ofctl -O OpenFlow13 dump-flows s1
```

```text
priority=300,ip,nw_src=10.0.0.4 actions=drop
priority=260,tcp,nw_src=10.0.0.2,tp_dst=5000 actions=set_queue:1,goto_table:1
priority=260,tcp,nw_dst=10.0.0.2,tp_src=5000 actions=set_queue:1,goto_table:1
priority=200,tcp,nw_src=10.0.0.1,tp_dst=5000 actions=set_queue:1,goto_table:1
priority=200,tcp,nw_dst=10.0.0.1,tp_src=5000 actions=set_queue:1,goto_table:1
priority=100,tcp,nw_src=10.0.0.2,tp_dst=5000 actions=set_queue:0,goto_table:1
priority=100,tcp,nw_dst=10.0.0.2,tp_src=5000 actions=set_queue:0,goto_table:1
priority=50,tcp,tp_dst=5000 actions=set_queue:0,goto_table:1
priority=50,tcp,tp_src=5000 actions=set_queue:0,goto_table:1
```

The `priority=50` catch-all only exists when `default_tier` is set, and
covers hosts that are not listed in `policy.json`. The `nw_dst`/`tp_src`
rules are the reply direction; without them the priority request is
queued but the server's reply still waits in the normal queue.

`set_queue:1` disappears when the user leaves the last priority room, and
the `priority=260` rules appear/disappear dynamically on ROOM_JOIN /
ROOM_LEAVE while the system is running.

## Setup

### Baseline controller

`controller/baseline_controller.py` is a plain L2 learning switch (no
policies, no queues). Use it for the comparison experiments together with
`topology/baseline_topology.py`:

```sh
ryu-manager controller/baseline_controller.py
```

### Ryu environment

Ryu 4.34 is old: its build fails with current setuptools, and its eventlet
dependency does not work on Python 3.14. Use Python 3.9 (tested) and
setuptools 58:

```sh
uv venv --python 3.9 --seed ryu-env
ryu-env/bin/pip install 'setuptools==58.3.0' wheel pbr
curl -LO https://files.pythonhosted.org/packages/25/30/1c1972b3f9bf52de32d2fdf7c5206ff7099e739bf69b6004f4a71bcbde18/ryu-4.34.tar.gz
ryu-env/bin/pip install --no-build-isolation --no-deps ./ryu-4.34.tar.gz
ryu-env/bin/pip install 'eventlet==0.30.2' 'msgpack>=0.3.0' netaddr \
    'oslo.config>=2.5.0' 'ovs>=2.6.0' routes 'six>=1.4.0' tinyrpc \
    'webob>=1.2' 'dnspython<2.2'
```

The `ryu-4.34.tar.gz` source archive is available from PyPI. The local
`ryu-env/` in the repository root is already set up this way.
