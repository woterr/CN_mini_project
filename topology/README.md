# Part C: Topology and Testing

## IP Plan

| Device | IP Address | Connected To |
|---|---|---|
| c1 | 10.0.0.1/24 | s1 |
| c2 | 10.0.0.2/24 | s1 |
| c3 | 10.0.0.3/24 | s1 |
| c4 (blocked) | 10.0.0.4/24 | s1 |
| Server | 10.0.0.10/24 | s2 |

## Topology

- Two OpenFlow 1.3 switches: s1 and s2
- Four clients connected to s1
- Chat server connected to s2
- Inter-switch link bandwidth: 5 Mbps
- Inter-switch link delay: 10 ms
- SDN controller: Ryu at 127.0.0.1:6653

## Run

From the project root, start the Ryu controller in one terminal:

    source ryu-env/bin/activate
    ryu-manager controller/chat_controller.py

In another terminal, start the topology:

    sudo python3 topology/topology.py

## Initial Test Cases

1. Run `pingall` in the Mininet CLI to check connectivity.
2. Test c1, c2 and c3 connectivity to the server.
3. Test c4 connectivity; the policy should block c4.
4. Run `sh ovs-ofctl -O OpenFlow13 dump-flows s1` to inspect flow rules.
5. Join and leave a chat room and verify that the controller receives the room event and updates the relevant flow rule.

## Evidence

Capture terminal screenshots of the topology, connectivity tests, and OpenFlow flow-table output. Record room-join integration results after verifying them.
