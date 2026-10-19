
import socket
import threading

# Chat server configuration
HOST = "0.0.0.0"
PORT = 5000

# SDN controller configuration
CONTROLLER_HOST = "127.0.0.1"
CONTROLLER_PORT = 6000

# Shared server data
users = {}          # username: password
online_users = {}   # username: client socket
rooms = {}          # room name: set of usernames
client_user = {}    # client socket: username

lock = threading.Lock()


def send_message(client, message):
    """Send one newline-terminated message to a client."""
    try:
        client.sendall((message + "\n").encode("utf-8"))
    except OSError:
        pass


def notify_controller(event, user_ip, room):
    """Send a room event to the SDN controller over TCP."""
    message = f"{event} {user_ip} {room}\n"

    try:
        with socket.create_connection(
            (CONTROLLER_HOST, CONTROLLER_PORT),
            timeout=1
        ) as controller_socket:
            controller_socket.sendall(message.encode("utf-8"))

        print(f"[SDN NOTIFICATION] {message.strip()}")

    except OSError:
        print(
            f"[SDN] Controller unavailable; "
            f"notification not delivered: {message.strip()}"
        )


def handle_client(client, address):
    username = None
    buffer = ""

    print(f"[CONNECTED] {address}")

    try:
        while True:
            data = client.recv(4096)

            if not data:
                break

            buffer += data.decode("utf-8", errors="replace")

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.rstrip("\r")

                if not line:
                    continue

                parts = line.split(" ", 2)
                command = parts[0].upper()

                # REGISTER
                if command == "REGISTER":
                    fields = line.split()

                    if len(fields) != 3:
                        send_message(client, "ERR BAD_COMMAND")
                        continue

                    _, user, password = fields

                    with lock:
                        if user in users:
                            response = "ERR USER_EXISTS"
                        else:
                            users[user] = password
                            response = "OK registered"

                    send_message(client, response)

                # LOGIN
                elif command == "LOGIN":
                    fields = line.split()

                    if len(fields) != 3:
                        send_message(client, "ERR BAD_COMMAND")
                        continue

                    _, user, password = fields

                    with lock:
                        if username is not None:
                            response = "ERR ALREADY_LOGGED_IN"
                        elif user not in users or users[user] != password:
                            response = "ERR BAD_CREDENTIALS"
                        elif user in online_users:
                            response = "ERR ALREADY_LOGGED_IN"
                        else:
                            username = user
                            online_users[user] = client
                            client_user[client] = user
                            response = "OK logged_in"

                    send_message(client, response)

                # All other commands require login
                elif username is None:
                    send_message(client, "ERR NOT_LOGGED_IN")

                # CREATE ROOM
                elif command == "CREATE":
                    fields = line.split()

                    if len(fields) != 2:
                        send_message(client, "ERR BAD_COMMAND")
                        continue

                    room = fields[1]

                    with lock:
                        if room in rooms:
                            response = "ERR ROOM_EXISTS"
                        else:
                            rooms[room] = set()
                            response = "OK created"

                    send_message(client, response)

                # JOIN ROOM
                elif command == "JOIN":
                    fields = line.split()

                    if len(fields) != 2:
                        send_message(client, "ERR BAD_COMMAND")
                        continue

                    room = fields[1]

                    with lock:
                        if room not in rooms:
                            response = "ERR NO_SUCH_ROOM"
                            members = []
                        else:
                            rooms[room].add(username)
                            response = "OK joined"

                            members = [
                                online_users[u]
                                for u in rooms[room]
                                if u != username and u in online_users
                            ]

                    send_message(client, response)

                    if response == "OK joined":
                        notify_controller(
                            "ROOM_JOIN", address[0], room
                        )

                        for member in members:
                            send_message(
                                member,
                                f"INFO {username} joined {room}"
                            )

                # LEAVE ROOM
                elif command == "LEAVE":
                    fields = line.split()

                    if len(fields) != 2:
                        send_message(client, "ERR BAD_COMMAND")
                        continue

                    room = fields[1]

                    with lock:
                        if room not in rooms:
                            response = "ERR NO_SUCH_ROOM"
                        elif username not in rooms[room]:
                            response = "ERR NOT_IN_ROOM"
                        else:
                            rooms[room].remove(username)
                            response = "OK left"

                    send_message(client, response)

                    if response == "OK left":
                        notify_controller(
                            "ROOM_LEAVE", address[0], room
                        )

                # ROOM MESSAGE
                elif command == "MSG":
                    if len(parts) < 3 or not parts[1] or not parts[2]:
                        send_message(client, "ERR BAD_COMMAND")
                        continue

                    room, text = parts[1], parts[2]

                    with lock:
                        if room not in rooms:
                            response = "ERR NO_SUCH_ROOM"
                            recipients = []
                        elif username not in rooms[room]:
                            response = "ERR NOT_IN_ROOM"
                            recipients = []
                        else:
                            response = "OK sent"
                            recipients = [
                                online_users[u]
                                for u in rooms[room]
                                if u != username and u in online_users
                            ]

                    send_message(client, response)

                    if response == "OK sent":
                        for recipient in recipients:
                            send_message(
                                recipient,
                                f"ROOMMSG {room} {username} {text}"
                            )

                # PRIVATE MESSAGE
                elif command == "PM":
                    if len(parts) < 3 or not parts[1] or not parts[2]:
                        send_message(client, "ERR BAD_COMMAND")
                        continue

                    target, text = parts[1], parts[2]

                    with lock:
                        recipient = online_users.get(target)

                    if recipient is None:
                        send_message(client, "ERR NO_SUCH_USER")
                    else:
                        send_message(
                            recipient,
                            f"PMSG {username} {text}"
                        )
                        send_message(client, "OK sent")

                # LIST ONLINE USERS
                elif command == "USERS":
                    with lock:
                        names = ",".join(sorted(online_users))

                    send_message(client, f"USERS {names}")

                # LIST ROOMS
                elif command == "ROOMS":
                    with lock:
                        names = ",".join(sorted(rooms))

                    send_message(client, f"ROOMS {names}")

                # DISCONNECT
                elif command == "QUIT":
                    send_message(client, "OK bye")
                    return

                else:
                    send_message(client, "ERR BAD_COMMAND")

    except (OSError, ConnectionError) as error:
        print(f"[CONNECTION ERROR] {address}: {error}")

    finally:
        # Remove the disconnected user from online state and rooms.
        departed_rooms = []

        with lock:
            if username is not None:
                online_users.pop(username, None)
                client_user.pop(client, None)

                for room, members in rooms.items():
                    if username in members:
                        members.remove(username)
                        departed_rooms.append(room)

        # Notify the controller about room departures.
        for room in departed_rooms:
            notify_controller("ROOM_LEAVE", address[0], room)

        try:
            client.close()
        except OSError:
            pass

        print(f"[DISCONNECTED] {address}")


def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen()

    print(f"Chat server listening on {HOST}:{PORT}")

    try:
        while True:
            client, address = server.accept()

            thread = threading.Thread(
                target=handle_client,
                args=(client, address),
                daemon=True
            )
            thread.start()

    except KeyboardInterrupt:
        print("\nShutting down server.")

    finally:
        server.close()


if __name__ == "__main__":
    main()
