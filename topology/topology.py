#!/usr/bin/env python3

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel, info


def run_topology():
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

    c1 = net.addHost("c1", ip="10.0.0.1/24")
    c2 = net.addHost("c2", ip="10.0.0.2/24")
    c3 = net.addHost("c3", ip="10.0.0.3/24")
    c4 = net.addHost("c4", ip="10.0.0.4/24")
    server = net.addHost("server", ip="10.0.0.10/24")

    for client in (c1, c2, c3, c4):
        net.addLink(client, s1)

    net.addLink(server, s2)
    net.addLink(s1, s2, bw=5, delay="10ms")

    info("*** Starting Mininet topology\n")
    net.build()
    net.start()

    info("*** Run pingall to test host connectivity\n")
    CLI(net)

    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    run_topology()
