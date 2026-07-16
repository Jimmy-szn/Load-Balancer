import os
import random
import string
import subprocess
import threading
import time
import requests
from flask import Flask, jsonify, request
from consistent_hash import ConsistentHashMap

app = Flask(__name__)
chmap = ConsistentHashMap()
# In-memory control plane state: container name -> stable server_id in the hash ring.
servers = {}
server_id_counter = [1]
lock = threading.Lock()

NETWORK = "net1"
SERVER_IMAGE = "my_server:latest"


def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output


def parse_scale_payload(data, action):
    # Shared validator for /add and /rm payloads.
    if not isinstance(data, dict):
        return None, None, "<Error> Invalid JSON payload"

    n = data.get("n")
    hostnames = data.get("hostnames", [])

    if not isinstance(n, int) or n < 0:
        return None, None, "<Error> 'n' must be a non-negative integer"
    if not isinstance(hostnames, list):
        return None, None, "<Error> 'hostnames' must be a list"
    if any((not isinstance(h, str)) or (not h.strip()) for h in hostnames):
        return None, None, "<Error> Hostnames must be non-empty strings"

    if len(set(hostnames)) != len(hostnames):
        return None, None, "<Error> Hostname list contains duplicates"

    if len(hostnames) > n:
        if action == "add":
            return None, None, "<Error> Length of hostname list is more than newly added instances"
        return None, None, "<Error> Length of hostname list is more than removable instances"

    return n, hostnames, None

def random_name():
    return "Server_" + "".join(random.choices(string.ascii_uppercase + string.digits, k=5))

def spawn_server(name=None):
    # Starts one backend container, then registers it in local state + hash ring.
    with lock:
        sid = server_id_counter[0]
        if name is None:
            for _ in range(20):
                candidate = random_name()
                if candidate not in servers:
                    name = candidate
                    break
            if name is None:
                return None, "<Error> Unable to generate unique hostname"
        elif name in servers:
            return None, f"<Error> Hostname '{name}' already exists"

        ok, output = run_cmd(
            f"sudo docker run --name {name} --network {NETWORK} "
            f"--network-alias {name} -e SERVER_ID={sid} -d {SERVER_IMAGE}"
        )
        if not ok:
            detail = output if output else "docker run failed"
            return None, f"<Error> Failed to spawn server '{name}': {detail}"

        server_id_counter[0] += 1
        servers[name] = sid
        chmap.add_server(sid)  # FIX: new API takes only server_id
        return name, None

def remove_server(name, allow_missing_container=False):
    # Removes backend container and unregisters it from the hash ring.
    with lock:
        if name not in servers:
            return False, f"<Error> Hostname '{name}' does not exist"

        ok, output = run_cmd(f"sudo docker stop {name} && sudo docker rm {name}")
        if not ok and ("No such container" not in output or not allow_missing_container):
            detail = output if output else "docker stop/rm failed"
            return False, f"<Error> Failed to remove server '{name}': {detail}"

        sid = servers.get(name)  # FIX: look up server_id before removing from ring
        if sid is not None:
            chmap.remove_server(sid)
        servers.pop(name, None)
        return True, None

# Background health checker: replace dead replicas automatically.
def heartbeat_monitor():
    while True:
        time.sleep(3)
        dead = []
        with lock:
            current = list(servers.keys())
        for name in current:
            try:
                r = requests.get(f"http://{name}:5000/heartbeat", timeout=2)
                if r.status_code != 200:
                    dead.append(name)
            except requests.RequestException:
                dead.append(name)
        for name in dead:
            print(f"[heartbeat] {name} is down, respawning...")
            removed, err = remove_server(name, allow_missing_container=True)
            if not removed:
                print(f"[heartbeat] remove failed: {err}")
                continue
            _, err = spawn_server()
            if err:
                print(f"[heartbeat] respawn failed: {err}")

@app.route("/rep", methods=["GET"])
def rep():
    # Returns the current replica set known to the load balancer.
    with lock:
        return jsonify({"message": {"N": len(servers), "replicas": list(servers.keys())},
                        "status": "successful"}), 200

@app.route("/add", methods=["POST"])
def add():
    # Adds n replicas; optional hostnames can pin exact container names.
    data = request.get_json()
    n, hostnames, err = parse_scale_payload(data, "add")
    if err:
        return jsonify({"message": err, "status": "failure"}), 400

    with lock:
        existing = set(servers.keys())
    duplicate_with_existing = [h for h in hostnames if h in existing]
    if duplicate_with_existing:
        return jsonify({"message": f"<Error> Hostname '{duplicate_with_existing[0]}' already exists",
                        "status": "failure"}), 400

    added = []
    for i in range(n):
        name = hostnames[i] if i < len(hostnames) else None
        created, err = spawn_server(name)
        if err:
            for created_name in added:
                remove_server(created_name)
            return jsonify({"message": err, "status": "failure"}), 500
        added.append(created)

    with lock:
        return jsonify({"message": {"N": len(servers), "replicas": list(servers.keys())},
                        "status": "successful"}), 200

@app.route("/rm", methods=["DELETE"])
def rm():
    # Removes requested replicas; if fewer names are provided than n, picks random extras.
    data = request.get_json()
    n, hostnames, err = parse_scale_payload(data, "rm")
    if err:
        return jsonify({"message": err, "status": "failure"}), 400

    to_remove = list(hostnames)
    with lock:
        all_servers = list(servers.keys())

    if n > len(all_servers):
        return jsonify({"message": "<Error> Number of removable instances is more than current replicas",
                        "status": "failure"}), 400

    missing = [h for h in hostnames if h not in all_servers]
    if missing:
        return jsonify({"message": f"<Error> Hostname '{missing[0]}' does not exist",
                        "status": "failure"}), 400

    remaining = [s for s in all_servers if s not in to_remove]
    while len(to_remove) < n and remaining:
        pick = random.choice(remaining)
        remaining.remove(pick)
        to_remove.append(pick)

    for name in to_remove:
        removed, err = remove_server(name)
        if not removed:
            return jsonify({"message": err, "status": "failure"}), 500

    with lock:
        return jsonify({"message": {"N": len(servers), "replicas": list(servers.keys())},
                        "status": "successful"}), 200

@app.route("/<path:path>", methods=["GET"])
def route_request(path):
    # Proxies any GET path to one backend selected via consistent hashing.
    rid = random.randint(100000, 999999)
    with lock:
        sid = chmap.get_server(rid)  # FIX: this now returns a server_id, not a hostname
        name = next((n for n, s in servers.items() if s == sid), None)
    if name is None:
        return jsonify({"message": "<Error> No servers available", "status": "failure"}), 400

    try:
        r = requests.get(f"http://{name}:5000/{path}", timeout=3)
        if r.status_code == 404:
            return jsonify({"message": f"<Error> '/{path}' endpoint does not exist in server replicas",
                            "status": "failure"}), 400

        try:
            payload = r.json()
        except ValueError:
            status = "successful" if r.ok else "failure"
            payload = {"message": r.text, "status": status}

        return jsonify(payload), r.status_code
    except requests.RequestException:
        return jsonify({"message": f"<Error> '/{path}' endpoint does not exist in server replicas",
                        "status": "failure"}), 400

if __name__ == "__main__":
    # Spawn initial 3 servers
    for i in range(3):
        _, err = spawn_server()
        if err:
            print(f"[startup] {err}")
    # Start heartbeat thread
    t = threading.Thread(target=heartbeat_monitor, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=5000)

