import argparse
import subprocess
import time
import psutil
import statistics
import sys
import logging
import matplotlib.pyplot as plt
import select
import os
import fcntl
import numpy as np

IFACE = "enp0s3"
IFB = "ifb0"
bandwidth_limits = [10, 20, 30, 40, 50]  # in Mbit/s

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("monitor_perf")

def run_cmd(cmd, check=True, **kwargs):
    logger.debug(f"Running command: {' '.join(cmd)}")
    subprocess.run(cmd, check=check, **kwargs)

def set_inbound_limit(bw_mbit, server_ip):
    logger.info(f"Setting inbound bandwidth limit to {bw_mbit} Mbit/s on {IFACE} for traffic from {server_ip}")
    subprocess.run(["sudo", "modprobe", "ifb"], stderr=subprocess.DEVNULL)
    subprocess.run(["sudo", "ip", "link", "del", IFB], stderr=subprocess.DEVNULL)
    run_cmd(["sudo", "ip", "link", "add", IFB, "type", "ifb"])
    run_cmd(["sudo", "ip", "link", "set", IFB, "up"])
    run_cmd(["sudo", "tc", "qdisc", "del", "dev", IFACE, "ingress"], check=False)
    run_cmd(["sudo", "tc", "qdisc", "del", "dev", IFB, "root"], check=False)
    run_cmd(["sudo", "tc", "qdisc", "add", "dev", IFACE, "handle", "ffff:", "ingress"])
    run_cmd([
        "sudo", "tc", "filter", "add", "dev", IFACE, "parent", "ffff:", "protocol", "ip", "u32",
        "match", "ip", "src", f"{server_ip}/32",
        "action", "mirred", "egress", "redirect", "dev", IFB
    ])
    run_cmd([
        "sudo", "tc", "qdisc", "add", "dev", IFB, "root", "tbf",
        "rate", f"{bw_mbit}mbit", "burst", "10k", "latency", "1000ms"
    ])

def clear_inbound_limit():
    logger.info("Clearing inbound bandwidth limit")
    subprocess.run(["sudo", "tc", "qdisc", "del", "dev", IFACE, "ingress"], stderr=subprocess.DEVNULL)
    subprocess.run(["sudo", "tc", "qdisc", "del", "dev", IFB, "root"], stderr=subprocess.DEVNULL)
    subprocess.run(["sudo", "ip", "link", "del", IFB], stderr=subprocess.DEVNULL)

def make_non_blocking(fd):
    # Make a file descriptor non-blocking
    fl = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

def monitor_cpu_and_wait(proc):
    """
    Continuously measure CPU usage and read output lines until the process is done or
    the completion message is found. Uses non-blocking I/O and select.
    """
    logger.debug("Starting CPU monitoring for client process.")
    cpu_measurements = []
    start_time = time.time()

    try:
        p = psutil.Process(proc.pid)
        # Warm-up psutil's internal counters
        _ = p.cpu_percent(interval=None)
    except psutil.NoSuchProcess:
        logger.debug("Process ended before monitoring started.")
        return 0.0, 0.0

    # Make stdout non-blocking
    make_non_blocking(proc.stdout.fileno())

    completion_detected = False

    while proc.poll() is None:
        # Check if there's any output available within 1 second
        rlist, _, _ = select.select([proc.stdout], [], [], 1.0)

        if rlist:
            try:
                line = proc.stdout.readline()
                if line:
                    line = line.strip()
                    logger.debug(f"Client output: {line}")
                    if "INFO:quic.client:Video transfer completed, closing connection..." in line:
                        logger.info("Detected completion message. Terminating client.")
                        proc.terminate()
                        completion_detected = True
                        break
            except Exception as e:
                # If reading failed for some reason, just ignore and continue
                logger.debug(f"Error reading line: {e}")

        # Measure CPU usage after waiting for output
        try:
            cpu_usage = p.cpu_percent(interval=None)  # snapshot since last call
            # Wait 1 second between CPU measurements
            time.sleep(1)
            cpu_measurements.append(cpu_usage)
            logger.debug(f"CPU usage: {cpu_usage}%")
        except psutil.NoSuchProcess:
            logger.debug("Process ended.")
            break

    end_time = time.time()
    duration = end_time - start_time
    avg_cpu = statistics.mean(cpu_measurements) if cpu_measurements else 0.0
    logger.debug(f"CPU monitoring ended. avg_cpu={avg_cpu:.2f}, duration={duration:.2f}s")
    return avg_cpu, duration

def run_client(host, port, output, extra_args):
    cmd = ["python3", "new_opt_client.py", "--host", host, "--port", str(port), "--output", output] + extra_args
    logger.info(f"Running client: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return proc

def plot_results(bandwidth_limits, avg_cpus, durations):
    plt.figure(figsize=(10, 6))

    # Plot CPU Usage
    plt.subplot(2, 1, 1)
    plt.plot(bandwidth_limits, avg_cpus, marker="o", label="Avg CPU Usage (%)")
    plt.title("Performance Metrics for Bandwidth Limits")
    plt.xlabel("Bandwidth Limit (Mbit/s)")
    plt.ylabel("Avg CPU Usage (%)")
    plt.legend(loc="upper left")
    plt.grid()

    # Plot Duration
    plt.subplot(2, 1, 2)
    plt.plot(bandwidth_limits, durations, marker="o", color="orange", label="Duration (s)")
    plt.xlabel("Bandwidth Limit (Mbit/s)")
    plt.ylabel("Duration (s)")
    plt.legend(loc="upper right")
    plt.grid()

    plt.tight_layout()
    plt.savefig("graph.png")
    cpu_arr = np.array(avg_cpus)
    dur_arr = np.array(durations)
    np.save('cpu_opt.npy',cpu_arr)
    np.save('dur_opt.npy',dur_arr)

def main():
    parser = argparse.ArgumentParser(description="Monitor CPU load while downloading video at various inbound bandwidth limits using IFB.")
    parser.add_argument("--host", required=True, help="Server IP/hostname")
    parser.add_argument("--port", type=int, default=4433, help="Server port (default: 4433)")
    parser.add_argument("--cert", type=str, default="client_cert.pem", help="Path to the server certificate file (default: client_cert.pem)")
    parser.add_argument("--key", type=str, default="client_key.pem", help="Path to the server private key file (default: client_key.pem)")
    parser.add_argument("--output", default="downloaded_video.mp4", help="Output file name for the received video")
    args = parser.parse_args()

    client_extra_args = []
    if args.no_verify:
        client_extra_args.append("--no-verify")

    avg_cpus = []
    durations = []

    for bw in bandwidth_limits:
        print(f"Testing with inbound bandwidth limit: {bw} Mbit/s")
        set_inbound_limit(bw, args.host)
        proc = run_client(args.host, args.port, args.output, client_extra_args)
        avg_cpu, duration = monitor_cpu_and_wait(proc)
        avg_cpus.append(avg_cpu)
        durations.append(duration)
        print(f"Inbound Bandwidth: {bw} Mbit/s | Avg CPU: {avg_cpu:.2f}% | Duration: {duration:.2f}s")
        clear_inbound_limit()

    print("\nSummary of Results:")
    for (bw, cpu, dur) in zip(bandwidth_limits, avg_cpus, durations):
        print(f"{bw} Mbit/s: Avg CPU: {cpu:.2f}%, Duration: {dur:.2f}s")

    plot_results(bandwidth_limits, avg_cpus, durations)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        clear_inbound_limit()
        sys.exit(1)
    except Exception as e:
        logger.exception("An error occurred:")
        clear_inbound_limit()
        sys.exit(1)
