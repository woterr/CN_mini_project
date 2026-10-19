
import socket
import threading

HOST = "127.0.0.1"
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


if __name__ == "__main__":
    main()
