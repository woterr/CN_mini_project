import argparse
import subprocess
import sys
import os
import csv
import time
import tempfile
from pathlib import Path

def run_experiment(client_count, message_count, room, password, output_file,
                   username_prefix="auto"):

    project_root = Path(__file__).resolve().parent.parent
    client_script = project_root / "client" / "chat_client.py"

    processes = []
    start_time = time.perf_counter()

    with tempfile.TemporaryDirectory() as temp_dir:

        print(f"\nStarting {client_count} clients...")
        print(f"Messages per client: {message_count}")
        print(f"Room: {room}\n")

        # Start all clients
        for i in range(1, client_count + 1):

            username = f"{username_prefix}{i}"
            client_csv = os.path.join(temp_dir, f"{username}.csv")

            command = [
                sys.executable,
                str(client_script),
                "--auto",
                "--username", username,
                "--password", password,
                "--room", room,
                "--messages", str(message_count),
                "--csv", client_csv
            ]

            # Local experiments talk over loopback; the client itself
            # defaults to the Mininet server address.
            child_env = os.environ.copy()
            child_env.setdefault("CHAT_HOST", "127.0.0.1")

            process = subprocess.Popen(command, env=child_env)
            processes.append((username, process, client_csv))

        # Wait for all clients to finish and verify results
        failed_clients = []

        for username, process, client_csv in processes:
            try:
                process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                print(f"{username} timed out.")
                process.kill()
                process.wait()
                failed_clients.append(username)
                continue

            successful_messages = 0

            if os.path.exists(client_csv):
                with open(client_csv, "r", newline="") as input_file:
                    reader = csv.DictReader(input_file)
                    successful_messages = sum(
                        1 for row in reader
                        if row["status"] == "SUCCESS"
                    )

            if (process.returncode == 0 and
                    successful_messages == message_count):
                print(f"{username} finished successfully.")
            else:
                print(
                    f"{username} failed: "
                    f"exit code={process.returncode}, "
                    f"successful messages={successful_messages}"
                )
                failed_clients.append(username)

        # Combine individual CSV files
        fieldnames = [
            "username",
            "connection_setup_ms",
            "message_number",
            "rtt_ms",
            "status"
        ]

        with open(output_file, "w", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()

            for username, process, client_csv in processes:
                if os.path.exists(client_csv):
                    with open(client_csv, "r", newline="") as input_file:
                        reader = csv.DictReader(input_file)
                        writer.writerows(reader)

    total_time = (time.perf_counter() - start_time) * 1000

    print("\nExperiment completed.")
    print(f"Total clients: {client_count}")
    print(f"Total execution time: {total_time:.3f} ms")
    print(f"Results saved to: {output_file}")
    if failed_clients:
        print(f"Experiment FAILED: {len(failed_clients)} client(s) failed.")
        print("Failed clients:", ", ".join(failed_clients))
        return False

    print("Experiment PASSED: All clients completed successfully.")
    return True
def main():

    parser = argparse.ArgumentParser(
        description="Multi-client chat performance testing"
    )

    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="Number of clients to launch (experiment counts: 10/25/50/100)"
    )

    parser.add_argument(
        "--messages",
        type=int,
        default=100,
        help="Number of messages per client"
    )

    parser.add_argument(
        "--room",
        default="room1",
        help="Chat room for testing"
    )

    parser.add_argument(
        "--password",
        default="pass123",
        help="Password for automated clients"
    )

    parser.add_argument(
        "--output",
        default="performance_results.csv",
        help="Output CSV filename"
    )

    parser.add_argument(
        "--prefix",
        default="auto",
        help="Username prefix for automated clients "
             "(use pri/norm for priority-vs-normal runs)"
    )

    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of repeated runs; each run is written to its own CSV "
             "suffixed _run<k>, and all runs are also combined into --output"
    )

    args = parser.parse_args()

    combined_rows = []
    combined_fieldnames = None
    all_ok = True

    for run in range(1, args.runs + 1):
        if args.runs > 1:
            stem = Path(args.output).with_suffix("")
            output = f"{stem}_run{run}.csv"
            print(f"\n=== Run {run}/{args.runs} -> {output} ===")
        else:
            output = args.output

        ok = run_experiment(
            args.count,
            args.messages,
            args.room,
            args.password,
            output,
            args.prefix
        )
        all_ok = all_ok and ok

        # Collect rows for the combined CSV
        with open(output, newline="") as f:
            rows = list(csv.DictReader(f))
            if rows:
                combined_fieldnames = list(rows[0].keys())
                combined_rows.extend(rows)

    if combined_fieldnames and args.runs > 1:
        with open(args.output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=combined_fieldnames)
            writer.writeheader()
            writer.writerows(combined_rows)
        print(f"\nCombined {args.runs} runs into {args.output}")

    if not all_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()