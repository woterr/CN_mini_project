#!/usr/bin/env python3
"""Run the chat load experiments inside Mininet.

Must be run as root on the Mininet VM, e.g.:

    sudo python3 experiments/run_mininet.py --setup ours --count 25 \
        --messages 20 --size 1000 --runs 2 \
        --output experiments/results/compare_ours_25clients.csv

The script builds the topology (ours with queues, or the plain-learning
baseline), starts the Ryu controller and the chat server, then launches
automated clients inside the Mininet hosts, one client per host. Hosts
c1 (priority tier) and c4 (blocked) are excluded from load batches so
every measured user is a normal-tier user; run with --priority to also
launch a priority user on c1.

With --priority the script runs two batches concurrently:

- one client on c1 joining the priority room (--priority-room, vip),
  with usernames <priority-prefix>1 (pri1);
- the normal batch on the remaining hosts joining --room, with
  usernames <prefix>N (norm1, norm2, ...).

Every run writes its own CSV (<output stem>_run<k>.csv) plus a combined
CSV at --output, matching experiments/run_clients.py behaviour.
"""

import argparse
import csv
import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

# Mininet's Node.popen(shell=True) needs $SHELL in the environment.
os.environ.setdefault("SHELL", "/bin/bash")

REPO = Path(__file__).resolve().parent.parent
RESULTS = REPO / "experiments" / "results"
CONTROLLER_PORT = 6653
SERVER_IP = "10.0.0.10"
CONTROLLER_IP = "10.0.0.254"
CLIENT_TIMEOUT_MARGIN = 60


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_network(setup, count):
    if setup == "ours":
        topo = load_module("cn_topology", REPO / "topology" / "topology.py")
        net = topo.build_network(count)
    else:
        topo = load_module("cn_baseline_topology",
                           REPO / "topology" / "baseline_topology.py")
        net = topo.build_network(count)

    net.start()
    ensure_switches_started(net)

    if setup == "ours":
        topo.configure_queues(net)

    return net


def ensure_switches_started(net):
    """Work around an OVS/Mininet failure at large topologies.

    Mininet starts each OVS bridge with ONE big ovs-vsctl transaction
    (add-br + all add-ports). If anything in that transaction fails, the
    whole bridge is rolled back, so at 100 clients bridge s1 (100 ports)
    silently disappears while s2 (3 ports) is fine. Re-running the exact
    same command outside Mininet's shell works, so: detect a missing
    bridge and replay its startup command via a direct subprocess.
    """
    bridges = subprocess.run(["ovs-vsctl", "list-br"], capture_output=True,
                             text=True).stdout.split()

    for sw in net.switches:
        if sw.name in bridges:
            continue

        print(f"WARNING: {sw.name} bridge was not created by net.start();"
              " replaying its startup command")
        captured = {}
        orig_cmd = sw.cmd

        def recorder(*args, _orig=orig_cmd, _cap=captured, **kwargs):
            text = " ".join(str(a) for a in args)
            if text.startswith("ovs-vsctl"):
                _cap["cmd"] = text
                return ""
            return _orig(*args, **kwargs)

        sw.cmd = recorder
        try:
            sw.start(net.controllers)
        finally:
            sw.cmd = orig_cmd

        cmd = captured.get("cmd")
        if not cmd:
            raise RuntimeError(f"could not capture startup command for {sw}")
        result = subprocess.run(cmd, shell=True, capture_output=True,
                                text=True)
        if result.returncode != 0:
            raise RuntimeError(f"{sw.name} restart failed: "
                               f"{result.stderr.strip()[:300]}")
        print(f"Replayed {sw.name} startup")

    # Give reconnected switches a moment to talk to the controller.
    deadline = time.time() + 10
    while time.time() < deadline:
        out = subprocess.run(
            ["ovs-vsctl", "get", "Bridge", "s1", "is_connected"],
            capture_output=True, text=True).stdout
        if "true" in out:
            break
        time.sleep(1)


def start_controller(setup):
    app = ("controller/chat_controller.py" if setup == "ours"
           else "controller/baseline_controller.py")
    log = open("/tmp/mn_controller.log", "w")
    proc = subprocess.Popen(
        [str(REPO / "ryu-env" / "bin" / "ryu-manager"), str(REPO / app)],
        stdout=log, stderr=subprocess.STDOUT, cwd=REPO)

    for _ in range(30):
        if proc.poll() is not None:
            raise RuntimeError(f"controller exited; see /tmp/mn_controller.log")
        try:
            socket.create_connection(("127.0.0.1", CONTROLLER_PORT),
                                     timeout=1).close()
            print(f"Controller running: {app}")
            return proc
        except OSError:
            time.sleep(1)

    raise RuntimeError("controller did not start; see /tmp/mn_controller.log")


def start_server(net):
    server = net.get("server")
    server.cmd(
        f"CONTROLLER_HOST={CONTROLLER_IP} "
        f"python3 -u {REPO}/server/chat_server.py "
        f"> /tmp/mn_chat_server.log 2>&1 &")

    probe = ("python3 -c \"import socket; "
             "socket.create_connection(('127.0.0.1', 5000), "
             "timeout=1).close(); print('READY')\"")

    for _ in range(30):
        if "READY" in server.cmd(probe):
            print("Chat server running inside Mininet (10.0.0.10:5000)")
            return
        time.sleep(1)

    raise RuntimeError("chat server did not start; see /tmp/mn_chat_server.log")


def seed_rooms(net, rooms):
    """Create the test rooms once per topology, from inside c2."""
    seed_path = Path("/tmp/mn_seed_rooms.py")

    seed_path.write_text(
        "import socket\n"
        f"s = socket.create_connection((\"{SERVER_IP}\", 5000), timeout=5)\n"
        "reader = s.makefile('r')\n"
        "def cmd(line):\n"
        "    s.sendall((line + '\\n').encode())\n"
        "    return reader.readline().strip()\n"
        "print('seed:', cmd('REGISTER seed pw'))\n"
        "print('seed:', cmd('LOGIN seed pw'))\n"
        + "".join(f"print('seed:', cmd('CREATE {room}'))\n" for room in rooms)
        + "print('seed:', cmd('QUIT'))\n")

    out = net.get("c2").cmd(f"python3 {seed_path}")
    print(out.strip())


def load_hosts(net, count):
    """All hosts usable for load batches: everything except c1
    (priority tier) and c4 (blocked)."""
    return [net.get(f"c{i}") for i in range(1, count + 1)
            if i not in (1, 4)]


BARRIER_TIMEOUT = 300  # seconds to wait for all clients to join before GO


def wait_for_barrier(barrier_dir, expected_users, timeout):
    """Wait until every expected client has joined, then release them all.

    Each client writes <user>.ready after connect+login+join; once all
    markers exist this writes the GO marker, and every waiting client
    starts sending at the same moment in both setups.  On timeout it
    releases anyway (clients proceed on their own timeout) so a failed
    client cannot stall the whole run.
    """
    barrier_dir = Path(barrier_dir)
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        missing = [u for u in expected_users
                   if not (barrier_dir / f"{u}.ready").exists()]
        if not missing:
            break
        time.sleep(0.1)
    else:
        print(f"WARNING: start barrier timed out after {timeout}s; "
              f"missing: {', '.join(missing)}")

    (barrier_dir / "GO").write_text("go\n")
    print(f"Start barrier released for {len(expected_users)} clients "
          f"({time.monotonic() - (deadline - timeout):.1f}s to reach it)")


def launch_batch(net, hosts, prefix, room, messages, size, timeout,
                 barrier_dir=None, expected_users=None):
    """Start one auto client per host, wait for all, return (rows, failed).

    With barrier_dir, clients only start sending once every expected user
    (across both batches) has joined — see wait_for_barrier."""
    tmpdir = Path("/tmp/mn_exp")
    tmpdir.mkdir(exist_ok=True)

    processes = []

    for i, host in enumerate(hosts, 1):
        user = f"{prefix}{i}"
        # Remove stale results from previous runs so rows cannot
        # accumulate (the client appends to its CSV).
        for stale in (tmpdir / f"{user}.csv", tmpdir / f"{user}.log"):
            if stale.exists():
                stale.unlink()
        cmd = (f"python3 {REPO}/client/chat_client.py --auto "
               f"--username {user} --password pass123 --room {room} "
               f"--messages {messages} --size {size} "
               f"--csv {tmpdir}/{user}.csv > {tmpdir}/{user}.log 2>&1")
        if barrier_dir:
            cmd += f" --barrier-dir {barrier_dir}"
        processes.append((user, host, host.popen(cmd, shell=True)))

    if barrier_dir:
        wait_for_barrier(barrier_dir, expected_users,
                         timeout=min(timeout, BARRIER_TIMEOUT))

    rows = []
    fieldnames = None
    failed = []

    for user, host, proc in processes:
        try:
            proc.wait(timeout=timeout)
            ok = proc.returncode == 0
        except subprocess.TimeoutExpired:
            host.cmd(f"pkill -f 'username {user}'")
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
            ok = False

        path = tmpdir / f"{user}.csv"
        user_rows = []

        if path.exists():
            with open(path, newline="") as f:
                user_rows = list(csv.DictReader(f))

        if user_rows:
            fieldnames = list(user_rows[0].keys())
            rows.extend(user_rows)

        sent = sum(1 for r in user_rows if r["status"] == "SUCCESS")
        print(f"  {user}: {sent}/{messages} messages "
              f"{'ok' if ok and sent == messages else 'FAILED'}")

        if not ok or sent != messages:
            failed.append(user)

    return rows, fieldnames, failed


def write_csv(path, fieldnames, rows):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows, label):
    ok = [r for r in rows if r["status"] == "SUCCESS"]
    if not ok:
        print(f"{label}: no successful messages")
        return
    rtt = sum(float(r["rtt_ms"]) for r in ok) / len(ok)
    setup = sum(float(r["connection_setup_ms"]) for r in ok) / len(ok)
    print(f"{label}: {len(ok)} successful messages, "
          f"avg RTT {rtt:.3f} ms, avg connection setup {setup:.3f} ms")


def main():
    parser = argparse.ArgumentParser(
        description="Run chat load experiments inside Mininet")
    parser.add_argument("--setup", choices=["ours", "baseline"],
                        default="ours")
    parser.add_argument("--count", type=int, default=10,
                        help="Number of Mininet client hosts (c1..cN)")
    parser.add_argument("--messages", type=int, default=20)
    parser.add_argument("--size", type=int, default=0,
                        help="Pad auto messages to ~SIZE bytes for load")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--room", default="room1")
    parser.add_argument("--prefix", default="auto",
                        help="Username prefix for the normal batch")
    parser.add_argument("--priority", action="store_true",
                        help="Also run a priority user on c1 joining "
                             "--priority-room")
    parser.add_argument("--priority-room", default="vip")
    parser.add_argument("--priority-prefix", default="pri")
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=int, default=600,
                        help="Per-client timeout in seconds")
    args = parser.parse_args()

    if os.geteuid() != 0:
        sys.exit("run as root: sudo python3 experiments/run_mininet.py")

    rooms = [args.room, args.priority_room] if args.priority else [args.room]
    timeout = args.timeout

    controller = start_controller(args.setup)
    net = build_network(args.setup, args.count)
    start_server(net)
    seed_rooms(net, rooms)

    hosts = load_hosts(net, args.count)
    print(f"Load batch hosts: {[h.name for h in hosts]} "
          f"(c1 priority tier, c4 blocked, excluded)")

    # Everyone in the run must wait at the same start barrier: the normal
    # batch plus (with --priority) the priority user on c1.
    expected_users = [f"{args.prefix}{i}" for i in range(1, len(hosts) + 1)]
    if args.priority:
        expected_users.append(f"{args.priority_prefix}1")

    combined_rows = []
    combined_fieldnames = None
    all_failed = {}

    try:
        for run in range(1, args.runs + 1):
            output = Path(args.output)
            run_path = (output.with_name(
                f"{output.stem}_run{run}.csv") if args.runs > 1 else output)

            print(f"\n=== run {run}/{args.runs} -> {run_path.name} ===")

            # Fresh barrier directory per run: remove stale ready/GO markers.
            barrier_dir = Path("/tmp/mn_exp") / f"barrier_run{run}"
            if barrier_dir.exists():
                shutil.rmtree(barrier_dir)
            barrier_dir.mkdir(parents=True)

            if args.priority:
                # The priority user must compete with the normal batch, so
                # launch both at the same time instead of running the
                # priority client after every normal client has finished.
                pri_result = {}

                def run_priority_batch():
                    try:
                        pri_result["value"] = launch_batch(
                            net, [net.get("c1")], args.priority_prefix,
                            args.priority_room, args.messages, args.size,
                            timeout, barrier_dir, expected_users)
                    except BaseException as exc:  # surfaced below
                        pri_result["error"] = exc

                pri_thread = threading.Thread(
                    target=run_priority_batch, daemon=True)
                pri_thread.start()

                rows, fieldnames, failed = launch_batch(
                    net, hosts, args.prefix, args.room,
                    args.messages, args.size, timeout,
                    barrier_dir, expected_users)

                pri_thread.join()
                if "error" in pri_result:
                    raise pri_result["error"]
                pri_rows, pri_fields, pri_failed = pri_result["value"]
                rows.extend(pri_rows)
                fieldnames = fieldnames or pri_fields
                failed.extend(pri_failed)
            else:
                rows, fieldnames, failed = launch_batch(
                    net, hosts, args.prefix, args.room,
                    args.messages, args.size, timeout,
                    barrier_dir, expected_users)

            if failed:
                all_failed.setdefault(run, []).extend(failed)

            if not fieldnames:
                print("no data produced this run")
                continue

            write_csv(run_path, fieldnames, rows)
            combined_rows.extend(rows)
            combined_fieldnames = fieldnames
            summarize(rows, f"run {run}")

            if run < args.runs:
                time.sleep(5)

        if args.runs > 1 and combined_fieldnames:
            write_csv(args.output, combined_fieldnames, combined_rows)
            print(f"\nCombined {args.runs} runs into {args.output}")
    finally:
        net.stop()
        controller.terminate()
        try:
            controller.wait(timeout=10)
        except subprocess.TimeoutExpired:
            controller.kill()

    if all_failed:
        print(f"FAILED clients: {all_failed}")
        sys.exit(1)

    print("All clients completed successfully.")


if __name__ == "__main__":
    main()
