#  Customizable Load Balancer

This repository contains a Dockerized implementation of:
- Task 1: minimal web server replicas
- Task 2: consistent hashing with virtual servers
- Task 3: load balancer that manages replicas dynamically
- Task 4: partial analysis tooling

## 1) Current Project Structure

- `server/`
  - `server.py`: Flask server with `/home` and `/heartbeat`
  - `Dockerfile`: container image for server replicas
- `load_balancer/`
  - `app.py`: Flask load balancer with replica management and request routing
  - `consistent_hash.py`: consistent hash map implementation
  - `Dockerfile`: load balancer image (can spawn/manage Docker containers)
- `analysis/`
  - `test_load.py`: async load generator and bar-chart output for request distribution
- `docker-compose.yml`: runs the load balancer container on port 5000
- `Makefile`: helper commands to build/up/down the stack

## 2) How the System Works Right Now

1. `load_balancer` starts on host port `5000`.
2. On startup, it spawns 3 server containers (`my_server:latest`) on internal Docker network `net1`.
3. Requests to load balancer path endpoints are mapped to replicas via consistent hashing.
4. A heartbeat thread checks each replica (`/heartbeat`) every 3 seconds.
5. If a replica is unhealthy/missing, it is removed from internal state and a replacement is spawned.

## 3) Endpoints Implemented

### Server Endpoints (Task 1)

- `GET /home`
  - returns: `{"message": "Hello from Server: <ID>", "status": "successful"}`
- `GET /heartbeat`
  - returns: empty body with `200`

### Load Balancer Endpoints (Task 3)

- `GET /rep`
  - returns current replica count and hostnames
- `POST /add`
  - payload: `{"n": <int>, "hostnames": [..optional..]}`
  - supports validation for payload shape/types and hostname constraints
- `DELETE /rm`
  - payload: `{"n": <int>, "hostnames": [..optional..]}`
  - supports validation, including removable-count checks
- `GET /<path>`
  - forwards to selected backend replica
  - unknown backend route returns failure with 400

## 4) Running the Project

Prerequisites:
- Ubuntu + Docker + Docker Compose installed
- user allowed to run Docker commands (or use `sudo`)

Build images:

```bash
sudo make build
```

Start stack:

```bash
sudo make up
```

Stop stack and cleanup server containers:

```bash
sudo make down
```

Quick checks:

```bash
curl http://localhost:5000/rep
curl http://localhost:5000/home
curl -X POST http://localhost:5000/add -H "Content-Type: application/json" -d '{"n":1,"hostnames":["S5"]}'
curl -X DELETE http://localhost:5000/rm -H "Content-Type: application/json" -d '{"n":1,"hostnames":["S5"]}'
```

## 5) Progress Status

### Task 1 - Server

Status: **Completed**

- [x] `/home` implemented
- [x] `/heartbeat` implemented
- [x] server Dockerfile implemented

### Task 2 - Consistent Hashing

Status: **Completed (core implementation)**

- [x] ring size `M = 512`
- [x] virtual servers `K = 9`
- [x] request hashing + clockwise server lookup
- [x] server add/remove with probing on collisions

### Task 3 - Load Balancer

Status: **Completed (with robustness fixes)**

- [x] `/rep`, `/add`, `/rm`, `/<path>` endpoints implemented
- [x] heartbeat monitoring and auto-replacement on failure
- [x] docker command success checks before mutating in-memory state
- [x] payload validation and sanity checks for scaling APIs
- [x] startup with default replica count `N = 3`
- [x] docker-compose + Makefile for deployment

### Task 4 - Analysis

Status: **Partially Completed**

- [x] async request launcher script (`analysis/test_load.py`)
- [x] A1 bar chart artifact generation present (`A1_bar_chart.png`)
- [ ] A2 line chart for varying `N = 2..6`
- [ ] A3 complete endpoint/failure demonstration write-up
- [ ] A4 modified hash-function experiment + observations

## 6) Recent Improvements

Recent hardening done in `load_balancer/app.py`:
- strict payload parsing for `/add` and `/rm`
- prevents duplicate hostname additions
- rejects impossible removals (`n > current replicas`)
- only updates internal replica/hash state after successful Docker operations
- heartbeat cleanup can handle already-missing containers and recover cleanly

## 7) Known Notes

- The load balancer currently chooses a random request ID for hashing during route forwarding.
- Container management from inside the load balancer depends on Docker socket access and privileges.
- Some old leftover containers can exist if not cleaned; `sudo make down` is used to clean typical `Server*` containers.

## 8) Suggested Next Steps

1. Finish Task 4 experiments (A2, A3, A4) and add plots/results.
2. Add a small automated test suite for endpoint behavior and failure recovery.
3. Add `requirements.txt` files and pin versions for reproducibility.
4. Optionally tighten proxy error differentiation (timeout vs 404 vs other backend errors).
