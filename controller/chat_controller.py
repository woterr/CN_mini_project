"""Ryu SDN controller for the chat network (OpenFlow 1.3).

Policies, configured in controller/policy.json:

- blocked hosts  : all IPv4 traffic is dropped at the switch.
- priority tier  : chat traffic goes to the higher-priority queue (queue 1)
                   on the bottleneck link.
- normal tier    : chat traffic goes to the limited queue (queue 0) on the
                   bottleneck link.
- priority rooms : the chat server notifies the controller with ROOM_JOIN /
                   ROOM_LEAVE messages on port 6000. While a user is in a
                   priority room, its chat traffic moves to the priority
                   queue; when it leaves the last priority room it falls
                   back to its tier queue. This happens while the system
                   is running, with no restart.

Queues 0 and 1 are created on the bottleneck link ports by
topology/topology.py. Table 0 classifies chat traffic by user in both
directions (client -> server uses source IP + TCP dst 5000; server ->
client uses destination IP + TCP src 5000); table 1 is a learning L2
switch.
"""

import json
import os

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import (CONFIG_DISPATCHER, MAIN_DISPATCHER,
                                    set_ev_cls)
from ryu.lib import hub
from ryu.lib.packet import ethernet, in_proto, packet
from ryu.ofproto import ether, ofproto_v1_3

POLICY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'policy.json')
ROOM_PORT = 6000
CHAT_PORT = 5000

TABLE_CLASSIFY = 0
TABLE_FORWARD = 1

QUEUE_NORMAL = 0     # limited queue on the bottleneck link
QUEUE_PRIORITY = 1   # higher-priority queue on the bottleneck link
QUEUE_NAME = {QUEUE_NORMAL: 'normal queue 0 (limited)',
              QUEUE_PRIORITY: 'priority queue 1'}

PRIORITY_BLOCKED = 300   # drop rule for blocked hosts
PRIORITY_ROOM = 260      # dynamic rule for priority-room members
TIER_PRIORITY = {'priority': 200, 'normal': 100}  # static tier rules
PRIORITY_DEFAULT = 50    # catch-all rule for unknown hosts (default tier)
PRIORITY_L2 = 10         # learned L2 forwarding rules


class ChatController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(ChatController, self).__init__(*args, **kwargs)
        with open(POLICY_FILE) as policy_file:
            policy = json.load(policy_file)

        self.hosts = policy['hosts']
        self.priority_rooms = set(policy['priority_rooms'])
        self.default_tier = policy.get('default_tier')  # tier for unknown hosts
        self.datapaths = {}
        self.mac_to_port = {}
        self.room_members = {}  # user IP -> set of priority rooms joined

        hub.spawn(self._room_listener)

        self.logger.info('Policy loaded: priority rooms %s', sorted(self.priority_rooms))
        if self.default_tier:
            self.logger.info('Policy: default tier for unknown hosts = %s (queue %d)',
                             self.default_tier, self._tier_queue(self.default_tier))
        for ip, tier in sorted(self.hosts.items()):
            if tier == 'blocked':
                self.logger.info('Policy: %s tier=blocked (traffic will be dropped)', ip)
            else:
                self.logger.info('Policy: %s tier=%s (static queue %d)',
                                 ip, tier, self._tier_queue(tier))

    # ---------- flow helpers ----------

    def _tier_queue(self, tier):
        return QUEUE_PRIORITY if tier == 'priority' else QUEUE_NORMAL

    def _chat_match(self, dp, ip):
        return dp.ofproto_parser.OFPMatch(
            eth_type=ether.ETH_TYPE_IP,
            ip_proto=in_proto.IPPROTO_TCP,
            ipv4_src=ip,
            tcp_dst=CHAT_PORT,
        )

    def _chat_reply_match(self, dp, ip):
        """Match the server's replies to this client.

        A chat round trip crosses the bottleneck twice: the request
        (client -> server, tcp_dst=5000) and the reply (server -> client,
        tcp_src=5000).  Both directions must use the client's queue, or a
        priority request still waits behind normal traffic for its reply.
        """
        return dp.ofproto_parser.OFPMatch(
            eth_type=ether.ETH_TYPE_IP,
            ip_proto=in_proto.IPPROTO_TCP,
            ipv4_dst=ip,
            tcp_src=CHAT_PORT,
        )

    def _ip_match(self, dp, ip):
        return dp.ofproto_parser.OFPMatch(eth_type=ether.ETH_TYPE_IP, ipv4_src=ip)

    def _any_chat_match(self, dp):
        return dp.ofproto_parser.OFPMatch(
            eth_type=ether.ETH_TYPE_IP,
            ip_proto=in_proto.IPPROTO_TCP,
            tcp_dst=CHAT_PORT,
        )

    def _any_chat_reply_match(self, dp):
        return dp.ofproto_parser.OFPMatch(
            eth_type=ether.ETH_TYPE_IP,
            ip_proto=in_proto.IPPROTO_TCP,
            tcp_src=CHAT_PORT,
        )

    def _add_flow(self, dp, table, priority, match, actions=None,
                  goto_forward=False, idle_timeout=0):
        # NOTE: policy (tier/queue) rules and learned L2 rules must NOT
        # expire: the baseline learning switch installs its flows
        # permanently, and an expired L2 rule would make the switch flood
        # unicast packets to every access port until re-learned.  Keep
        # both setups apples-to-apples and free of expiry churn.
        parser = dp.ofproto_parser
        instructions = []

        if actions:
            instructions.append(parser.OFPInstructionActions(
                dp.ofproto.OFPIT_APPLY_ACTIONS, actions))

        if goto_forward:
            instructions.append(parser.OFPInstructionGotoTable(TABLE_FORWARD))

        dp.send_msg(parser.OFPFlowMod(
            datapath=dp,
            table_id=table,
            priority=priority,
            idle_timeout=idle_timeout,
            match=match,
            instructions=instructions,
        ))

    def _delete_flow(self, dp, priority, match):
        dp.send_msg(dp.ofproto_parser.OFPFlowMod(
            datapath=dp,
            table_id=TABLE_CLASSIFY,
            command=dp.ofproto.OFPFC_DELETE_STRICT,
            priority=priority,
            out_port=dp.ofproto.OFPP_ANY,
            out_group=dp.ofproto.OFPG_ANY,
            match=match,
        ))

    # ---------- per-switch policy installation ----------

    def _apply_policy(self, dp):
        """Install every policy rule for this switch and log what was applied."""
        parser = dp.ofproto_parser
        sid = format(dp.id, '016x')

        # Table-miss rules: unknown L2 traffic, and chat traffic from
        # hosts not listed in policy.json when a default tier is set.
        self._add_flow(dp, TABLE_CLASSIFY, 0, parser.OFPMatch(),
                       goto_forward=True)
        self._add_flow(
            dp, TABLE_FORWARD, 0, parser.OFPMatch(),
            actions=[parser.OFPActionOutput(
                dp.ofproto.OFPP_CONTROLLER, dp.ofproto.OFPCML_NO_BUFFER)])

        if self.default_tier:
            self._add_flow(dp, TABLE_CLASSIFY, PRIORITY_DEFAULT,
                           self._any_chat_match(dp),
                           actions=[parser.OFPActionSetQueue(
                               self._tier_queue(self.default_tier))],
                           goto_forward=True)
            self._add_flow(dp, TABLE_CLASSIFY, PRIORITY_DEFAULT,
                           self._any_chat_reply_match(dp),
                           actions=[parser.OFPActionSetQueue(
                               self._tier_queue(self.default_tier))],
                           goto_forward=True)
            self.logger.info(
                '[POLICY] switch %s: unknown hosts tier=%s -> chat traffic (both directions) sent to %s',
                sid, self.default_tier,
                QUEUE_NAME[self._tier_queue(self.default_tier)])

        for ip, tier in sorted(self.hosts.items()):
            if tier == 'blocked':
                self._add_flow(dp, TABLE_CLASSIFY, PRIORITY_BLOCKED,
                               self._ip_match(dp, ip))
                self.logger.info(
                    '[POLICY] switch %s: %s tier=blocked -> all IPv4 traffic dropped at the switch',
                    sid, ip)
            else:
                queue = self._tier_queue(tier)
                self._add_flow(dp, TABLE_CLASSIFY, TIER_PRIORITY[tier],
                               self._chat_match(dp, ip),
                               actions=[parser.OFPActionSetQueue(queue)],
                               goto_forward=True)
                self._add_flow(dp, TABLE_CLASSIFY, TIER_PRIORITY[tier],
                               self._chat_reply_match(dp, ip),
                               actions=[parser.OFPActionSetQueue(queue)],
                               goto_forward=True)
                self.logger.info(
                    '[POLICY] switch %s: %s tier=%s -> chat traffic (both directions) sent to %s',
                    sid, ip, tier, QUEUE_NAME[queue])

        # Re-apply dynamic priority-room rules (e.g. after a switch reconnect).
        for ip in self.room_members:
            self._add_room_flow(dp, ip)
            self.logger.info(
                '[POLICY] switch %s: %s in priority room(s) %s -> chat traffic (both directions) sent to %s',
                sid, ip, sorted(self.room_members[ip]), QUEUE_NAME[QUEUE_PRIORITY])

        self.logger.info('[INFO] switch %s connected and policies applied', sid)

    # ---------- dynamic priority-room policy ----------

    def _add_room_flow(self, dp, ip):
        parser = dp.ofproto_parser
        queue_action = [parser.OFPActionSetQueue(QUEUE_PRIORITY)]
        self._add_flow(dp, TABLE_CLASSIFY, PRIORITY_ROOM,
                       self._chat_match(dp, ip),
                       actions=queue_action,
                       goto_forward=True)
        self._add_flow(dp, TABLE_CLASSIFY, PRIORITY_ROOM,
                       self._chat_reply_match(dp, ip),
                       actions=queue_action,
                       goto_forward=True)

    def _remove_room_flow(self, dp, ip):
        self._delete_flow(dp, PRIORITY_ROOM, self._chat_match(dp, ip))
        self._delete_flow(dp, PRIORITY_ROOM, self._chat_reply_match(dp, ip))

    def _handle_room_event(self, line):
        parts = line.split()
        if len(parts) != 3:
            return

        event, ip, room = parts
        tier = self.hosts.get(ip, self.default_tier or 'unknown')
        self.logger.info('[EVENT ] %s %s %s', event, ip, room)

        if room not in self.priority_rooms:
            self.logger.info(
                '[POLICY] %s %s ignored: room %r is not a priority room', event, ip, room)
            return

        if tier == 'blocked':
            self.logger.info(
                '[POLICY] %s %s ignored: user is blocked, traffic stays dropped', event, ip)
            return

        if event == 'ROOM_JOIN':
            rooms = self.room_members.setdefault(ip, set())
            if room not in rooms:
                rooms.add(room)
                if len(rooms) == 1:
                    for dp in self.datapaths.values():
                        self._add_room_flow(dp, ip)
                self.logger.info(
                    '[POLICY] %s joined priority room %r (tier=%s) -> chat traffic moved to %s while running',
                    ip, room, tier, QUEUE_NAME[QUEUE_PRIORITY])

        elif event == 'ROOM_LEAVE':
            rooms = self.room_members.get(ip)
            if rooms and room in rooms:
                rooms.remove(room)
                if not rooms:
                    del self.room_members[ip]
                    for dp in self.datapaths.values():
                        self._remove_room_flow(dp, ip)
                    self.logger.info(
                        '[POLICY] %s left last priority room (was in %r) -> chat traffic returned to %s (tier=%s)',
                        ip, room, QUEUE_NAME[self._tier_queue(tier)], tier)
                else:
                    self.logger.info(
                        '[POLICY] %s left priority room %r, still in %s -> stays in %s',
                        ip, room, sorted(rooms), QUEUE_NAME[QUEUE_PRIORITY])

    # ---------- Ryu handlers ----------

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features(self, ev):
        dp = ev.msg.datapath
        self.datapaths[dp.id] = dp
        self.mac_to_port.setdefault(dp.id, {})
        self._apply_policy(dp)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in(self, ev):
        msg = ev.msg
        dp = msg.datapath
        parser = dp.ofproto_parser
        in_port = msg.match['in_port']

        eth = packet.Packet(msg.data).get_protocol(ethernet.ethernet)
        if eth is None:
            return

        macs = self.mac_to_port.setdefault(dp.id, {})
        macs[eth.src] = in_port

        if int(eth.dst[:2], 16) & 1:  # multicast/broadcast
            out_port = dp.ofproto.OFPP_FLOOD
        elif eth.dst in macs:
            out_port = macs[eth.dst]
            # Permanent, like the baseline learning switch (no idle
            # timeout): expiry would re-flood unicast traffic.
            self._add_flow(
                dp, TABLE_FORWARD, PRIORITY_L2,
                parser.OFPMatch(in_port=in_port, eth_dst=eth.dst),
                actions=[parser.OFPActionOutput(out_port, 0)])
        else:
            out_port = dp.ofproto.OFPP_FLOOD

        dp.send_msg(parser.OFPPacketOut(
            datapath=dp,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=[parser.OFPActionOutput(out_port, 0)],
            data=msg.data,
        ))

    # ---------- room event listener ----------

    def _room_listener(self):
        server = hub.listen(('0.0.0.0', ROOM_PORT))
        self.logger.info('[INFO] Room policy listener on port %d', ROOM_PORT)
        while True:
            conn, _ = server.accept()
            hub.spawn(self._read_room_events, conn)

    def _read_room_events(self, conn):
        with conn:
            for line in conn.makefile('r'):
                self._handle_room_event(line.strip())
