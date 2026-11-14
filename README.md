# Multi-Client Chat Network

## Overview

A multi-client chat application built using Python TCP sockets and threading.

It supports user registration, login, chat rooms, room messaging, private messaging, online-user tracking, disconnect handling and error handling.

The chat server also communicates with an SDN controller through asynchronous room-join and room-leave notifications.

## Requirements

- Python 3
- No third-party Python packages required for the chat server or client
- Ryu (OpenFlow 1.3) for the SDN controller

## Project Structure

- `server/chat_server.py` — TCP chat server
- `client/chat_client.py` — Command-line chat client with interactive and automated modes
- `controller/chat_controller.py` — Ryu controller (L2 forwarding and policies)
- `controller/policy.json` — Host tiers and priority rooms
- `topology/` — Network topology
- `experiments/run_clients.py` — Automated multi-client performance testing
- `experiments/results/` — CSV performance results
- `docs/protocol.md` — Protocol specification

## Run Locally

Open a terminal in the project root.

Start the chat server:

```bash
python server/chat_server.py
```

Open a second terminal:

```bash
python client/chat_client.py
```

Open additional terminals to connect multiple clients:

```bash
python client/chat_client.py
```

## Chat Commands

| Command | Description |
|---|---|
| `REGISTER <user> <pass>` | Register a new user |
| `LOGIN <user> <pass>` | Log in |
| `CREATE <room>` | Create a chat room |
| `JOIN <room>` | Join a room |
| `LEAVE <room>` | Leave a room |
| `MSG <room> <text>` | Send a room message |
| `PM <user> <text>` | Send a private message |
| `USERS` | List online users |
| `ROOMS` | List available rooms |
| `QUIT` | Disconnect from the server |

## Server Features

- Multiple simultaneous TCP clients using threading.
- User registration and authentication.
- Duplicate registration and invalid credential handling.
- Room creation, joining and leaving.
- Room messaging and message broadcasting.
- Private messaging between online users.
- Handling of nonexistent and offline message recipients.
- Online-user tracking.
- Graceful client disconnection and room-membership cleanup.
- Background queue for asynchronous SDN notifications.

## SDN Notifications

The chat server sends newline-terminated messages over a separate TCP connection to `127.0.0.1:6000`.

Supported events:

- `ROOM_JOIN <user_ip> <room>`
- `ROOM_LEAVE <user_ip> <room>`

The server uses a background worker to process these notifications so controller communication does not block normal chat operations.

The controller in `controller/chat_controller.py` listens for these messages.

## Run the SDN Controller

Start the chat server first, then run the controller from the project root:

```bash
ryu-manager controller/chat_controller.py
```

The controller reads `controller/policy.json` and listens on port `6000` for room events.

See `controller/README.md` for the policy format.

## Automated Performance Testing

The project includes an automated client launcher that supports 10, 25, 50 and 100 simultaneous clients.

Before running an experiment:

1. Start the chat server.
2. Ensure the test room exists (default: `room1`).
3. Run the launcher from the project root.

Example:

```bash
python experiments/run_clients.py --count 10 --messages 5 --room room1 --output experiments/results/load_10.csv
```

Other supported client counts:

```bash
python experiments/run_clients.py --count 25 --messages 5 --room room1 --output experiments/results/load_25.csv

python experiments/run_clients.py --count 50 --messages 5 --room room1 --output experiments/results/load_50.csv

python experiments/run_clients.py --count 100 --messages 5 --room room1 --output experiments/results/load_100.csv
```

The automated clients:

- Register and log in automatically.
- Join the specified room.
- Send a fixed number of messages.
- Measure message round-trip time (RTT).
- Measure connection setup time.
- Record message status and timing information in CSV files.

The launcher checks client completion, successful message counts and execution timeouts.

## Performance Test Results

The following results were obtained from Windows localhost testing using 5 messages per client.

| Concurrent clients | Total messages | Successful messages | Failed messages | Execution time |
|---:|---:|---:|---:|---:|
| 10 | 50 | 50 | 0 | 217.811 ms |
| 25 | 125 | 125 | 0 | 514.343 ms |
| 50 | 250 | 250 | 0 | 1122.431 ms |
| 100 | 500 | 500 | 0 | 2339.235 ms |

All four experiments completed successfully, with 925 successful messages and zero failed messages.

### CSV Results

The final experiment results are stored in `experiments/results/`:

- `final_10_test.csv`
- `final_25_test.csv`
- `final_50_test.csv`
- `final_100_test.csv`

Each CSV contains:

- Username
- Connection setup time (ms)
- Message number
- Message RTT (ms)
- Message status

**Note:** These measurements were obtained using local Windows TCP connections. They are not Mininet network performance measurements.

## Limitations

- User accounts and rooms are stored in memory and reset when the server restarts.
- Local Windows clients share the loopback IP address.
- SDN controller notifications require the controller to be running to be delivered.
- Queue-based priority on the Mininet bottleneck link is handled in the separate network/SDN milestone.

## Screenshots

### Chat Server

![Chat Server](https://github.com/user-attachments/assets/5b7dc790-6e89-4aeb-b650-fc48d0fdd1bf)

### Chat Client

![Chat Client](https://github.com/user-attachments/assets/8263b009-7761-4c28-91a9-527c65f8eac0)

## Mininet Baseline Performance Results

Baseline performance testing was conducted using Mininet with a 5 Mbps bottleneck link and 10 ms configured link delay.

Each client sent 5 messages to the chat server. Message RTT and connection setup time were recorded.

| Concurrent clients | Total messages | Successful messages | Failed messages | Average RTT (ms) | Average connection setup (ms) |
|---:|---:|---:|---:|---:|---:|
| 10 | 50 | 50 | 0 | 72.174 | 122.560 |
| 25 | 125 | 125 | 0 | 83.452 | 291.304 |

Both experiments completed successfully, recording 175 successful messages with zero failures.

### Mininet CSV and Graph Results

The measurements and generated graphs are stored in `experiments/results/`:

- `baseline_10clients.csv`
- `baseline_25clients.csv`
- `baseline_rtt.png`
- `baseline_connection_setup.png`
- `baseline_25clients_rtt.png`
- `baseline_25clients_connection_setup.png`

### Performance Observation

As the number of concurrent clients increased from 10 to 25, average RTT increased from 72.174 ms to 83.452 ms. Average connection setup time increased from 122.560 ms to 291.304 ms.

These results indicate increased communication overhead with a higher number of concurrent clients.

