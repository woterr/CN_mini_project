import socket
import threading
import argparse
import csv
import time
import os

HOST = "10.0.0.254"
PORT = 5000


def receive_messages(sock):
    buffer = ""

    try:
        while True:
            data = sock.recv(4096)

            if not data:
                print("\nDisconnected from server.")
                break

            buffer += data.decode("utf-8", errors="replace")

            while "\n" in buffer:
                message, buffer = buffer.split("\n", 1)
                print(f"\n{message}")
                print("> ", end="", flush=True)

    except OSError:
        pass


def main():
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        client.connect((HOST, PORT))
        print(f"Connected to chat server at {HOST}:{PORT}")
    except OSError as error:
        print(f"Could not connect: {error}")
        return

    receiver = threading.Thread(
        target=receive_messages,
        args=(client,),
        daemon=True
    )
    receiver.start()

    try:
        while True:
            command = input("> ")

            if not command.strip():
                continue

            client.sendall((command + "\n").encode("utf-8"))

            if command.strip().upper() == "QUIT":
                break

    except (KeyboardInterrupt, EOFError):
        pass
    except OSError as error:
        print(f"Connection error: {error}")
    finally:
        client.close()
        print("Client closed.")


def auto_mode(username, password, room, message_count, csv_file):
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.settimeout(10)

    connection_start = time.perf_counter()

    try:
        client.connect((HOST, PORT))

        reader = client.makefile("r", encoding="utf-8")

        def send_command(command):
            client.sendall((command + "\n").encode("utf-8"))
            while True:
                response = reader.readline()

                if not response:
                    raise ConnectionError("Server disconnected")

                response = response.strip()

                # Ignore messages received from other clients
                if response.startswith(("ROOMMSG ", "PMSG ", "INFO ")):
                    continue

                return response
        # Register account
        response = send_command(f"REGISTER {username} {password}")

        if response == "ERR USER_EXISTS":
            pass
        elif not response.startswith("OK"):
            raise RuntimeError(f"Registration failed: {response}")

        # Login
        response = send_command(f"LOGIN {username} {password}")

        if not response.startswith("OK"):
            raise RuntimeError(f"Login failed: {response}")

        # Join room
        response = send_command(f"JOIN {room}")

        if not response.startswith("OK"):
            raise RuntimeError(f"Room join failed: {response}")
        connect_time = (time.perf_counter() - connection_start) * 1000
        
        print(f"[{username}] Connected and joined {room}")

        results = []

        for i in range(1, message_count + 1):
            message = f"Automated message {i} from {username}"

            start = time.perf_counter()

            response = send_command(f"MSG {room} {message}")

            end = time.perf_counter()

            rtt = (end - start) * 1000

            if response == "OK sent":
                status = "SUCCESS"
            else:
                status = response

            results.append({
                "username": username,
                "message_number": i,
                "rtt_ms": round(rtt, 3),
                "status": status
            })

            print(f"[{username}] Message {i}: {rtt:.3f} ms")

        # Append results to CSV
        file_exists = os.path.exists(csv_file)

        with open(csv_file, "a", newline="") as file:
            fieldnames = [
                "username",
                "connection_setup_ms",
                "message_number",
                "rtt_ms",
                "status"
            ]

            writer = csv.DictWriter(file, fieldnames=fieldnames)

            if not file_exists or os.path.getsize(csv_file) == 0:
                writer.writeheader()

            for result in results:
                result["connection_setup_ms"] = round(connect_time, 3)

            writer.writerows(results)

        send_command("LEAVE " + room)
        send_command("QUIT")

        print(f"[{username}] Completed {message_count} messages")
        print(f"[{username}] Connection setup time: {connect_time:.3f} ms")

    except (OSError, RuntimeError) as error:
        print(f"[{username}] Error: {error}")
        raise SystemExit(1)

    finally:
        client.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--auto", action="store_true")
    parser.add_argument("--username", default="auto1")
    parser.add_argument("--password", default="pass123")
    parser.add_argument("--room", default="room1")
    parser.add_argument("--messages", type=int, default=10)
    parser.add_argument("--csv", default="performance_results.csv")

    args = parser.parse_args()

    if args.auto:
        auto_mode(
            args.username,
            args.password,
            args.room,
            args.messages,
            args.csv
        )
    else:
        main()