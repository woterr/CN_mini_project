
# Multi-Client Chat Network

## Overview
A multi-client chat application built using Python TCP sockets and threading.
It supports registration, login, chat rooms, room messaging, private messaging,
and basic error handling. The server also attempts to notify an SDN controller
when users join or leave rooms.

## Requirements
- Python 3
- No third-party Python packages required for the chat server or client
- Ryu (OpenFlow 1.3) for the SDN controller

## Project Structure
- server/chat_server.py — TCP chat server
- client/chat_client.py — Command-line chat client
- controller/chat_controller.py — Ryu controller (L2 forwarding + policies)
- controller/policy.json — Host tiers and priority rooms
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

The controller in controller/chat_controller.py listens for these messages.

## Run the SDN Controller
Start the chat server first, then run the controller from the project root:

    ryu-manager controller/chat_controller.py

The controller reads controller/policy.json and listens on 0.0.0.0:6000 for
room events. See controller/README.md for the policy format.

## Limitations
- Accounts and rooms are stored in memory and reset when the server restarts.
- Local Windows clients share the loopback IP address.
- Queue-based priority on the Mininet bottleneck link is left for the next
  milestone.
- Automated load testing is reserved for a later milestone.


## Screenshots

Chat server

<img width="830" height="131" alt="image" src="https://github.com/user-attachments/assets/5b7dc790-6e89-4aeb-b650-fc48d0fdd1bf" />



Chat client

<img width="948" height="436" alt="image" src="https://github.com/user-attachments/assets/8263b009-7761-4c28-91a9-527c65f8eac0" />

