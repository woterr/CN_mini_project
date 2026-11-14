import csv
import statistics
import matplotlib.pyplot as plt

with open("experiments/results/baseline_50clients.csv") as f:
    rows = list(csv.DictReader(f))

successful = [r for r in rows if r["status"] == "SUCCESS"]
rtt = [float(r["rtt_ms"]) for r in successful]
connections = {
    r["username"]: float(r["connection_setup_ms"])
    for r in rows
}

avg_rtt = statistics.mean(rtt)
avg_connection = statistics.mean(connections.values())

plt.figure()
plt.bar(["50 clients"], [avg_rtt])
plt.ylabel("Average RTT (ms)")
plt.title("Baseline: Average RTT - 25 Clients")
plt.savefig("experiments/results/baseline_50clients_rtt.png", dpi=200)
plt.close()

plt.figure()
plt.bar(["50 clients"], [avg_connection])
plt.ylabel("Connection Setup Time (ms)")
plt.title("Baseline: Connection Setup - 25 Clients")
plt.savefig("experiments/results/baseline_50clients_connection_setup.png", dpi=200)
plt.close()

print(f"Average RTT: {avg_rtt:.3f} ms")
print(f"Average connection setup: {avg_connection:.3f} ms")
print("50-client graphs saved successfully.")
