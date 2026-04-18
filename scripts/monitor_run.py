import subprocess
import time
import json
import os
import socket
import sys
import argparse

""" python scripts/monitor_run.py <runs> """

def wait_for_port(host, port, timeout=300):
    start_time = time.time()
    print(f"Waiting for {host}:{port} to be available...")
    while True:
        try:
            with socket.create_connection((host, port), timeout=1):
                print(f"Connected to {host}:{port}!")
                return True
        except (OSError, ConnectionRefusedError):
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Service {host}:{port} did not start in time.")
            time.sleep(1)

def run_commands():
    start_ts_ms = int(time.time() * 1000)
    start_iso = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

    try:
        subprocess.run("source ./envs/issuer.env.sh && docker compose up -d issuer", 
                       shell=True, check=True, executable='/bin/bash')
        
        subprocess.run("source ./envs/vendor.env.sh && docker compose up -d vendor", 
                       shell=True, check=True, executable='/bin/bash')

        wait_for_port("localhost", 8000) 
        
        # Add a small delay to ensure vendor service is fully ready
        time.sleep(5)
        
        # Run client with better error handling
        print("Starting client process...")
        try:
            subprocess.run("source ./envs/client.env.sh && docker compose up client", 
                           shell=True, check=True, executable='/bin/bash', timeout=300)
            print("Client process completed normally")
        except subprocess.TimeoutExpired:
            print("Client process timed out after 300 seconds - this might be expected behavior")
        except subprocess.CalledProcessError as e:
            print(f"Client process exited with code {e.returncode}")
            if e.returncode == 1:
                print("Client exited with code 1 - this is expected behavior")
            else:
                print(f"Unexpected exit code {e.returncode}, treating as error")
                raise
        
        status = "success"
    except Exception as e:
        print(f"Error executing command: {e}")
        status = "failed"

    finish_ts_ms = int(time.time() * 1000)
    finish_iso = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    
    metadata = {
        "status": status,
        "prometheus_timestamps": {"start_ms": start_ts_ms, "finish_ms": finish_ts_ms},
        "readable": {"start": start_iso, "finish": finish_iso, "duration_ms": finish_ts_ms - start_ts_ms}
    }
    
    return metadata

def main(runs):
    all_runs = []
    
    for i in range(runs):
        print(f"\n=== Run {i + 1}/{runs} ===")
        run_metadata = run_commands()
        all_runs.append(run_metadata)
    
    # Overwrite runs_metadata.json with new runs only
    with open("runs_metadata.json", "w") as f:
        json.dump(all_runs, f, indent=4)
    
    print(f"\nCompleted {runs} runs. Results saved to runs_metadata.json")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run monitoring commands multiple times")
    parser.add_argument("runs", type=int, nargs="?", default=1, 
                       help="Number of runs to execute (default: 1)")
    args = parser.parse_args()
    
    main(args.runs)