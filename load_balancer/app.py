import os
import random
import string
import threading
import time
import requests
from flask import Flask, jsonify, request
from consistent_hash import ConsistentHashMap

app = Flask(__name__)
chmap = ConsistentHashMap()
servers = {}       # name -> server_id
server_id_counter = [1]
lock = threading.Lock()

NETWORK = "net1"
SERVER_IMAGE = "my_server:latest"

def random_name():
    return "Server_" + "".join(random.choices(string.ascii_uppercase + string.digits, k=5))

def spawn_server(name=None):
    with lock:
        sid = server_id_counter[0]
        server_id_counter[0] += 1
        if name is None:
            name = random_name()
        os.system(f"sudo docker run --name {name} --network {NETWORK} "
                  f"--network-alias {name} -e SERVER_ID={sid} -d {SERVER_IMAGE}")
        servers[name] = sid
        chmap.add_server(sid, name)
        return name

def remove_server(name):
    with lock:
        os.system(f"sudo docker stop {name} && sudo docker rm {name}")
        chmap.remove_server(name)
        servers.pop(name, None)

# Heartbeat monitor
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
            except:
                dead.append(name)
        for name in dead:
            print(f"[heartbeat] {name} is down, respawning...")
            remove_server(name)
            spawn_server()

@app.route("/rep", methods=["GET"])
def rep():
    with lock:
        return jsonify({"message": {"N": len(servers), "replicas": list(servers.keys())},
                        "status": "successful"}), 200

@app.route("/add", methods=["POST"])
def add():
    data = request.get_json()
    n = data.get("n", 0)
    hostnames = data.get("hostnames", [])
    if len(hostnames) > n:
        return jsonify({"message": "<Error> Length of hostname list is more than newly added instances",
                        "status": "failure"}), 400
    added = []
    for i in range(n):
        name = hostnames[i] if i < len(hostnames) else None
        added.append(spawn_server(name))
    with lock:
        return jsonify({"message": {"N": len(servers), "replicas": list(servers.keys())},
                        "status": "successful"}), 200

@app.route("/rm", methods=["DELETE"])
def rm():
    data = request.get_json()
    n = data.get("n", 0)
    hostnames = data.get("hostnames", [])
    if len(hostnames) > n:
        return jsonify({"message": "<Error> Length of hostname list is more than removable instances",
                        "status": "failure"}), 400
    to_remove = list(hostnames)
    with lock:
        remaining = [s for s in servers.keys() if s not in to_remove]
    while len(to_remove) < n and remaining:
        pick = random.choice(remaining)
        remaining.remove(pick)
        to_remove.append(pick)
    for name in to_remove:
        remove_server(name)
    with lock:
        return jsonify({"message": {"N": len(servers), "replicas": list(servers.keys())},
                        "status": "successful"}), 200

@app.route("/<path:path>", methods=["GET"])
def route_request(path):
    rid = random.randint(100000, 999999)
    with lock:
        name = chmap.get_server(rid)
    if name is None:
        return jsonify({"message": "<Error> No servers available", "status": "failure"}), 400
    try:
        r = requests.get(f"http://{name}:5000/{path}", timeout=3)
        return jsonify(r.json()), r.status_code
    except:
        return jsonify({"message": f"<Error> '/{path}' endpoint does not exist in server replicas",
                        "status": "failure"}), 400

if __name__ == "__main__":
    # Spawn initial 3 servers
    for i in range(3):
        spawn_server()
    # Start heartbeat thread
    t = threading.Thread(target=heartbeat_monitor, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=5000)
