#!/usr/bin/env python3

import sys
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel, info


def build_network(client_count):
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

    for i in range(1, client_count + 1):
        # 10.0.0.10 is the chat server, so hosts c10 and above shift up
        # by one (c10 -> 10.0.0.11, c11 -> 10.0.0.12, ...).
        ip = f"10.0.0.{i}/24" if i < 10 else f"10.0.0.{i + 1}/24"
        net.addHost(f"c{i}", ip=ip)
        net.addLink(net.get(f"c{i}"), s1)

    server = net.addHost("server", ip="10.0.0.10/24")
    net.addLink(server, s2)

    net.addLink(s1, s2, bw=5, delay="10ms")

    net.build()
    return net


def run_topology(client_count):
    info(f"*** Starting topology with {client_count} clients\n")
    net = build_network(client_count)
    net.start()

    info("*** Run pingall to test connectivity\n")
    CLI(net)

    net.stop()


if __name__ == "__main__":
    setLogLevel("info")

    count = int(sys.argv[1]) if len(sys.argv) > 1 else 10

    if count not in [10, 25, 50, 100]:
        sys.exit("Choose 10, 25, 50, or 100 clients")

    run_topology(count)
