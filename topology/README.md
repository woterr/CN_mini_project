# Part C: Topology and Testing

## IP Plan

| Device | IP Address | Connected To |
|---|---|---|
| c1 | 10.0.0.1/24 | s1 |
| c2 | 10.0.0.2/24 | s1 |
| c3 | 10.0.0.3/24 | s1 |
| c4 (blocked) | 10.0.0.4/24 | s1 |
| server | 10.0.0.10/24 | s2 |
| ctrl (management) | 10.0.0.254/24 | s2 |

## Topology

- Two OpenFlow 1.3 switches: s1 and s2
- Four clients connected to s1
- Chat server connected to s2
- Inter-switch link bandwidth: 5 Mbps
- Inter-switch link delay: 10 ms
- Queues on both bottleneck-link ports, created by `topology.py` at startup:
  queue 0 = normal (0.5 Mbps guaranteed, borrows idle capacity up to the
  5 Mbps link rate), queue 1 = priority (3 Mbps guaranteed, 5 Mbps max)
- Ryu OpenFlow listener: 127.0.0.1:6653
- Ryu room listener: 0.0.0.0:6000, reachable from Mininet at 10.0.0.254:6000

## Run

From the project root, start the Ryu controller in one terminal:

```sh
source ryu-env/bin/activate
ryu-manager controller/chat_controller.py
```

In another terminal, start the topology:

```sh
sudo python3 topology/topology.py
```

The default topology has 4 clients (`c1`–`c4`). For load experiments a
larger client count can be passed:

```sh
sudo python3 topology/topology.py 25    # c1..c25
```

`c4` (10.0.0.4) stays blocked by policy in every case — exclude it from
load runs; its client intentionally cannot connect. The comparison
baseline uses `topology/baseline_topology.py <count>` with the same
5 Mbps bottleneck link but no queues.

The topology prints `Controller management address: 10.0.0.254`, then
configures the queues on the bottleneck ports:

```text
*** Queues on s1-eth5: 0 = normal (0.5 Mbps guaranteed, borrows to 5 Mbps), 1 = priority (3 Mbps guaranteed, 5 Mbps max); 10 ms netem delay under HTB classes
*** Queues on s2-eth4: 0 = normal (0.5 Mbps guaranteed, borrows to 5 Mbps), 1 = priority (3 Mbps guaranteed, 5 Mbps max); 10 ms netem delay under HTB classes
```

## Start the Chat Server Inside Mininet

The chat server must run in the `server` host so clients can reach
`10.0.0.10:5000`. It also needs to send room events to `10.0.0.254:6000`.

At the `mininet>` prompt:

```text
mininet> server bash -c 'cd /home/ubuntu/CN_mini_project && CONTROLLER_HOST=10.0.0.254 nohup python3 -u server/chat_server.py > /tmp/chat_server.log 2>&1 &'
mininet> server cat /tmp/chat_server.log
```

Expected:

```text
Chat server listening on 0.0.0.0:5000
```

Replace `/home/ubuntu/CN_mini_project` with the actual project path on the
Mininet VM.

## Run Chat Clients

The client defaults to `10.0.0.10:5000`, which is correct for Mininet. For a
GUI VM, open one terminal per client:

```text
mininet> xterm c1 c2 c3
```

In each terminal:

```sh
python3 /home/ubuntu/CN_mini_project/client/chat_client.py
```

For a headless VM, run the client command inside a host with `mininet>` or use
`mnexec`; do not run it from the Ubuntu host, because the host is not inside the
Mininet network namespace.

For the local, non-Mininet demo, use loopback instead:

```sh
CHAT_HOST=127.0.0.1 python3 client/chat_client.py
```

## Test Cases

1. Run `pingall`. With `c4` blocked and `ctrl` included, expect about
   `33% dropped (20/30 received)`. All failures should involve `c4`.
2. Test allowed and blocked hosts:

   ```text
   mininet> c1 ping -c 3 10.0.0.10
   mininet> c4 ping -c 3 10.0.0.10
   ```

   `c1` should have `0%` loss. `c4` should have `100%` loss.

3. Inspect the flow rules:

   ```text
   mininet> sh ovs-ofctl -O OpenFlow13 dump-flows s1
   ```

   Expected rules include:

   ```text
   priority=300,ip,nw_src=10.0.0.4 actions=drop
   priority=200,tcp,nw_src=10.0.0.1,tp_dst=5000 actions=set_queue:1,goto_table:1
   priority=100,tcp,nw_src=10.0.0.2,tp_dst=5000 actions=set_queue:0,goto_table:1
   ```

4. Run two clients, create `vip`, and join it. The server log should show:

   ```text
   [SDN NOTIFICATION] ROOM_JOIN 10.0.0.1 vip
   [SDN NOTIFICATION] ROOM_JOIN 10.0.0.2 vip
   ```

   The controller should show:

   ```text
   [EVENT ] ROOM_JOIN 10.0.0.1 vip
   [POLICY] 10.0.0.1 joined priority room 'vip' (tier=priority) -> chat traffic moved to priority queue 1 while running
   [EVENT ] ROOM_JOIN 10.0.0.2 vip
   [POLICY] 10.0.0.2 joined priority room 'vip' (tier=normal) -> chat traffic moved to priority queue 1 while running
   ```

   While both users are in `vip`, `dump-flows s1` should contain a
   `priority=260` rule for each source IP with `tp_dst=5000` and
   `actions=set_queue:1,goto_table:1`.

5. Leave the room or disconnect the clients. The controller should log the
   leave events and the tier each user fell back to, and the `priority=260`
   rules should disappear.

6. Try a TCP connection from `c4` to `10.0.0.10:5000`. It should time out
   because the switch drops its IPv4 traffic. Also try joining `vip` from
   `c4`: the controller logs `[POLICY] ROOM_JOIN 10.0.0.4 ignored: user is
   blocked, traffic stays dropped`.

7. Run `pingall` again after the clients disconnect. The result should return
   to the same blocked-host pattern.
