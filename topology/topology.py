#!/usr/bin/env python3

import sys

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel, info


def build_network(client_count=4):
    net = Mininet(
        controller=None,
        switch=OVSSwitch,
        link=TCLink,
        build=False
    )

    net.addController(
        "c0",
        controller=RemoteController,
        ip="127.0.0.1",
        port=6653
    )

    s1 = net.addSwitch("s1", protocols="OpenFlow13")
    s2 = net.addSwitch("s2", protocols="OpenFlow13")

    clients = []
    for i in range(1, client_count + 1):
        # 10.0.0.10 is the chat server, so hosts c10 and above shift up
        # by one (c10 -> 10.0.0.11, c11 -> 10.0.0.12, ...).
        ip = f"10.0.0.{i}/24" if i < 10 else f"10.0.0.{i + 1}/24"
        clients.append(net.addHost(f"c{i}", ip=ip))

    server = net.addHost("server", ip="10.0.0.10/24")
    ctrl = net.addHost("ctrl", ip="10.0.0.254/24", inNamespace=False)

    for client in clients:
        net.addLink(client, s1)

    net.addLink(server, s2)
    net.addLink(ctrl, s2)
    net.addLink(s1, s2, bw=5, delay="10ms")

    net.build()
    return net


def configure_queues(net):
    """Create OpenFlow queues on both ports of the bottleneck link.

    Queue 0 (normal tier): guaranteed 0.5 Mbps, borrows spare capacity up
    to the full 5 Mbps link rate when the priority tier is idle.
    Queue 1 (priority tier): guaranteed 3 Mbps, allowed to use the full
    5 Mbps link rate.

    Neither queue is hard-capped below the link rate, so a tier is only
    slowed down when the other tier actually competes for the link; the
    "limited" nature of the normal tier is its much smaller guaranteed
    share (0.5 vs 3 Mbps), which HTB honours under contention.

    The controller assigns chat traffic to these queues with
    OFPActionSetQueue; see controller/chat_controller.py.

    OVS installs its own HTB root qdisc on these ports, which replaces
    the netem delay qdisc that TCLink put there. To keep both experiment
    setups on the same bottleneck, the 10 ms link delay is re-attached
    as a netem child qdisc under each HTB leaf class.
    """
    s1, s2 = net.get('s1'), net.get('s2')
    netem_handle = 100

    for src, dst in ((s1, s2), (s2, s1)):
        for intf, _peer in src.connectionsTo(dst):
            src.cmd(
                f'ovs-vsctl -- set Port {intf.name} qos=@newqos '
                '-- --id=@newqos create QoS type=linux-htb '
                'other-config:max-rate=5000000 queues:0=@q0 queues:1=@q1 '
                '-- --id=@q0 create Queue other-config:min-rate=500000 '
                'other-config:max-rate=5000000 '
                '-- --id=@q1 create Queue other-config:min-rate=3000000 '
                'other-config:max-rate=5000000'
            )

            # Re-attach the 10 ms link delay under every HTB leaf class
            # (the root class cannot take a child qdisc).
            classes = src.cmd(f'tc -d class show dev {intf.name}')
            for line in classes.splitlines():
                if 'class htb' not in line or 'parent 1:' not in line:
                    continue
                parent = line.split()[2]
                src.cmd(
                    f'tc qdisc add dev {intf.name} parent {parent} '
                    f'handle {netem_handle}: netem delay 10ms limit 2000'
                )
                netem_handle += 1

            info('*** Queues on %s: 0 = normal (0.5 Mbps guaranteed, '
                 'borrows to 5 Mbps), 1 = priority (3 Mbps guaranteed, '
                 '5 Mbps max); 10 ms netem delay under HTB classes\n'
                 % intf.name)


def run_topology(client_count=4):
    net = build_network(client_count)

    info("*** Starting Mininet topology (%d clients)\n" % client_count)
    net.start()
    configure_queues(net)

    info("*** Controller management address: 10.0.0.254\n")
    info("*** Run pingall to test host connectivity\n")
    CLI(net)

    net.stop()


if __name__ == "__main__":
    setLogLevel("info")

    count = int(sys.argv[1]) if len(sys.argv) > 1 else 4

    if count not in (4, 10, 25, 50, 100):
        sys.exit("Choose 4 (default), 10, 25, 50, or 100 clients")

    run_topology(count)
