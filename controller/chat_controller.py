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

DROP = 300
ROOM = 250
TIER = {'priority': 200, 'normal': 100}
TABLE_MISS = 0
L2 = 10


class ChatController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(ChatController, self).__init__(*args, **kwargs)
        with open(POLICY_FILE) as policy_file:
            policy = json.load(policy_file)

        self.hosts = policy['hosts']
        self.priority_rooms = set(policy['priority_rooms'])
        self.datapaths = {}
        self.mac_to_port = {}
        self.room_members = {}
        hub.spawn(self._room_listener)

    def _chat_match(self, dp, ip):
        return dp.ofproto_parser.OFPMatch(
            eth_type=ether.ETH_TYPE_IP,
            ip_proto=in_proto.IPPROTO_TCP,
            ipv4_src=ip,
            tcp_dst=CHAT_PORT,
        )

    def _forward_instruction(self, dp):
        return [dp.ofproto_parser.OFPInstructionGotoTable(TABLE_FORWARD)]

    def _add_flow(self, dp, table, priority, match, instructions,
                  idle_timeout=0):
        dp.send_msg(dp.ofproto_parser.OFPFlowMod(
            datapath=dp,
            table_id=table,
            priority=priority,
            idle_timeout=idle_timeout,
            match=match,
            instructions=instructions,
        ))

    def _delete_flow(self, dp, table, priority, match):
        dp.send_msg(dp.ofproto_parser.OFPFlowMod(
            datapath=dp,
            table_id=table,
            command=dp.ofproto.OFPFC_DELETE_STRICT,
            priority=priority,
            out_port=dp.ofproto.OFPP_ANY,
            out_group=dp.ofproto.OFPG_ANY,
            match=match,
        ))

    def _add_room_flow(self, dp, ip):
        self._add_flow(dp, TABLE_CLASSIFY, ROOM, self._chat_match(dp, ip), self._forward_instruction(dp))

    def _remove_room_flow(self, dp, ip):
        self._delete_flow(dp, TABLE_CLASSIFY, ROOM, self._chat_match(dp, ip))

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features(self, ev):
        dp = ev.msg.datapath
        parser = dp.ofproto_parser
        self.datapaths[dp.id] = dp
        self.mac_to_port.setdefault(dp.id, {})

        self._add_flow(dp, TABLE_CLASSIFY, TABLE_MISS, parser.OFPMatch(), self._forward_instruction(dp))
        self._add_flow(
            dp, TABLE_FORWARD, TABLE_MISS, parser.OFPMatch(),
            [parser.OFPInstructionActions(
                dp.ofproto.OFPIT_APPLY_ACTIONS,
                [parser.OFPActionOutput(dp.ofproto.OFPP_CONTROLLER, dp.ofproto.OFPCML_NO_BUFFER)],
            )],
        )

        for ip, tier in self.hosts.items():
            if tier == 'blocked':
                match = parser.OFPMatch(eth_type=ether.ETH_TYPE_IP, ipv4_src=ip)
                self._add_flow(dp, TABLE_CLASSIFY, DROP, match, [])
            else:
                self._add_flow(dp, TABLE_CLASSIFY, TIER[tier], self._chat_match(dp, ip), self._forward_instruction(dp))

        for ip in self.room_members:
            self._add_room_flow(dp, ip)

        self.logger.info('Switch %016x connected', dp.id)

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

        if int(eth.dst[:2], 16) & 1:
            out_port = dp.ofproto.OFPP_FLOOD
        elif eth.dst in macs:
            out_port = macs[eth.dst]
            self._add_flow(
                dp, TABLE_FORWARD, L2,
                parser.OFPMatch(in_port=in_port, eth_dst=eth.dst),
                [parser.OFPInstructionActions(
                    dp.ofproto.OFPIT_APPLY_ACTIONS,
                    [parser.OFPActionOutput(out_port, 0)],
                )],
                idle_timeout=60,
            )
        else:
            out_port = dp.ofproto.OFPP_FLOOD

        dp.send_msg(parser.OFPPacketOut(
            datapath=dp,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=[parser.OFPActionOutput(out_port, 0)],
            data=msg.data,
        ))

    def _room_listener(self):
        server = hub.listen(('0.0.0.0', ROOM_PORT))
        self.logger.info('Room policy listener on port %d', ROOM_PORT)
        while True:
            conn, _ = server.accept()
            hub.spawn(self._read_room_events, conn)

    def _read_room_events(self, conn):
        with conn:
            for line in conn.makefile('r'):
                self._handle_room_event(line.strip())

    def _handle_room_event(self, line):
        parts = line.split()
        if len(parts) != 3:
            return

        event, ip, room = parts
        if room not in self.priority_rooms or self.hosts.get(ip) == 'blocked':
            return

        if event == 'ROOM_JOIN':
            rooms = self.room_members.setdefault(ip, set())
            if room not in rooms:
                rooms.add(room)
                if len(rooms) == 1:
                    for dp in self.datapaths.values():
                        self._add_room_flow(dp, ip)
                    self.logger.info('%s joined priority room %s', ip, room)

        elif event == 'ROOM_LEAVE':
            rooms = self.room_members.get(ip)
            if rooms and room in rooms:
                rooms.remove(room)
                if not rooms:
                    del self.room_members[ip]
                    for dp in self.datapaths.values():
                        self._remove_room_flow(dp, ip)
                    self.logger.info('%s left priority rooms', ip)
