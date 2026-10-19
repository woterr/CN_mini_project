
# Multi-Client Chat Network

## Overview
A multi-client chat application built using Python TCP sockets and threading.
It supports registration, login, chat rooms, room messaging, private messaging,
and basic error handling. The server also attempts to notify an SDN controller
when users join or leave rooms.

## Requirements
- Python 3
- No third-party Python packages required for the chat server or client

## Project Structure
- server/chat_server.py — TCP chat server
- client/chat_client.py — Command-line chat client
- controller/ — SDN controller integration
- topology/ — Network topology
- experiments/ — Testing and performance experiments
- docs/protocol.md — Protocol specification

## Run Locally
Open a terminal in the project root.

Start the server:
    python server/chat_server.py

Open a second terminal:
    python client/chat_client.py

Open a third terminal for another client:
    python client/chat_client.py

## Commands
- REGISTER <user> <pass>
- LOGIN <user> <pass>
- CREATE <room>
- JOIN <room>
- LEAVE <room>
- MSG <room> <text>
- PM <user> <text>
- USERS
- ROOMS
- QUIT

## SDN Notifications
The chat server attempts to send newline-terminated messages over a separate
TCP connection to 127.0.0.1:6000:
- ROOM_JOIN <user_ip> <room>
- ROOM_LEAVE <user_ip> <room>

Delivery to the actual Ryu controller has not yet been verified.

## Limitations
- Accounts and rooms are stored in memory and reset when the server restarts.
- Local Windows clients share the loopback IP address.
- Integration with the Ryu controller and Mininet remains to be tested.
- Automated load testing is reserved for a later milestone.
