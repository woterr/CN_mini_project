# SDN controller

Ryu app for the chat network. It uses OpenFlow 1.3 and two tables:

- Table 0 classifies traffic by source IP and TCP destination port 5000.
- Table 1 is a learning L2 switch.

Host tiers and priority rooms are read from `policy.json`:

```json
{
  "priority_rooms": ["vip"],
  "hosts": {
    "10.0.0.1": "priority",
    "10.0.0.2": "normal",
    "10.0.0.4": "blocked"
  }
}
```

Blocked hosts get a drop flow for their IPv4 traffic. Traffic from priority and
normal hosts is sent to the forwarding table with different flow priorities.
Joining a priority room installs an extra priority flow; leaving the last
priority room removes it.

Run from the project root:

```sh
ryu-manager controller/chat_controller.py
```

The controller reads `controller/policy.json` and listens on `0.0.0.0:6000`
for room events. The listener accepts one-line TCP messages from the chat
server:

```text
ROOM_JOIN <user_ip> <room>
ROOM_LEAVE <user_ip> <room>
```

Queues for priority and normal traffic are not part of this milestone.

## Setup

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
