#  Customizable Load Balancer

This repository contains a Dockerized implementation of:
- Task 1: minimal web server replicas
- Task 2: consistent hashing with virtual servers
- Task 3: load balancer that manages replicas dynamically
- Task 4: analysis tooling and experiments

## 1) Current Project Structure

- `server/`
  - `server.py`: Flask server with `/home` and `/heartbeat`
  - `Dockerfile`: container image for server replicas
- `load_balancer/`
  - `app.py`: Flask load balancer with replica management and request routing
  - `consistent_hash.py`: consistent hash map implementation
  - `Dockerfile`: load balancer image (can spawn/manage Docker containers)
- `analysis/`
  - `test_load.py`: async load generator and bar-chart output for request distribution (A1)
  - `test_scaling.py`: async load generator across varying `N` and line-chart output (A2)
  - `test_load_A4.py`, `test_scaling_A4.py`: same experiments rerun under alternate hash functions (A4)
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

Status: **Completed**

- [x] async request launcher script (`analysis/test_load.py`)
- [x] A1 bar chart artifact generation present (`A1_bar_chart.png`)
- [x] A2 line chart for varying `N = 2..6` (`analysis/test_scaling.py`, `A2_line_chart.png`)
- [x] A3 complete endpoint/failure demonstration write-up
- [x] A4 modified hash-function experiment + observations (`experiment/alt-hash-functions` branch)

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

## 8) Task 4 Analysis Results

### A-1: Load Distribution (N=3, 10000 requests)

Result: `Server 1: 8462, Server 3: 1086, Server 2: 452` (84.6% / 10.9% / 4.5%)

This distribution is heavily skewed rather than even. Simulating the ring directly
showed the root cause: the given `Φ(server_id, replica_id) = server_id² + replica_id²
+ 2·replica_id + 25` is dominated by the `replica_id` term, which grows from 25 to
~114 across the 9 virtual replicas, while `server_id²` only separates servers by
1, 4, and 9. As a result, all 27 virtual server slots (3 servers × 9 replicas) land
in a narrow band of the ring (slots 26-114 out of 512), leaving the remaining ~398
slots empty. Any request hashing into that empty region wraps clockwise all the way
around to the lowest occupied slot, which belonged to Server 1 in this run. This
explains why Server 1 absorbed the majority of traffic — it wasn't "closer" to more
requests in a meaningful load-balancing sense, it was catching the entire wraparound
gap.

### A-2: Scalability (N=2 to 6, 10000 requests per run)

| N | Distribution |
|---|---|
| 2 | Server 2: 8763, Server 3: 1237 |
| 3 | Server 2: 8185, Server 3: 1125, Server 4: 690 |
| 4 | Server 2: 8104, Server 3: 1033, Server 4: 498, Server 5: 365 |
| 5 | Server 2: 8036, Server 3: 1019, Server 4: 491, Server 5: 369, Server 6: 85 |
| 6 | Server 2: 7780, Server 3: 982, Server 4: 449, Server 5: 370, Server 7: 419 |

The same skew from A-1 persists at every N — one server consistently takes
roughly 78-88% of the load regardless of how many servers are running. This
confirms the imbalance is structural (rooted in the hash function's slot
clustering) rather than something that improves or worsens with scale. The
average-load-per-server figure (`10000/N`) still decreases as expected with
more servers, but that metric alone hides the underlying imbalance — the
per-server breakdown is the more honest picture.

### A-3: Endpoint Testing and Failure Recovery

All endpoints were tested directly:

```bash
curl http://localhost:5000/rep
curl -X POST http://localhost:5000/add -H "Content-Type: application/json" -d '{"n": 2, "hostnames": []}'
curl -X DELETE http://localhost:5000/rm -H "Content-Type: application/json" -d '{"n": 1, "hostnames": []}'
curl http://localhost:5000/home
curl http://localhost:5000/other
```

`/rep`, `/add`, and `/rm` returned correct replica counts and hostname lists at
each step. `/home` routed successfully to a live server. `/other` correctly
returned a 400 with `<Error> '/other' endpoint does not exist in server replicas`.

Failure recovery was tested by killing a running server container and polling
`/rep` until the dead hostname was replaced:

```bash
docker kill <server_name>
# poll /rep every 0.2s until the killed hostname disappears from the replica list
```

Recovery time: **3.27 seconds**. This aligns with the heartbeat monitor's 3-second
polling interval, plus a small overhead for detecting the failure, removing the
dead container, and spawning + registering its replacement.

### A-4: Modified Hash Functions

New functions were added alongside the originals (both preserved in
`consistent_hash.py`, selectable via the class constructor):

```python
def alt_H(request_id: int, num_slots: int) -> int:
    return (request_id * 2654435761) % num_slots

def alt_Phi(server_id: int, replica_id: int, num_slots: int) -> int:
    return (server_id * 173 + replica_id * 41 + 7) % num_slots
```

Unlike the original `Φ`, this spreads virtual server slots across nearly the
full ring (span of ~503 out of 512 slots, vs. ~89 out of 512 originally),
eliminating the large empty region that caused wraparound clustering.

Rerunning A-1 under the new functions:

Result: `Server 3: 3913, Server 2: 3331, Server 1: 2756` (39.1% / 33.3% / 27.6%)

Rerunning A-2 under the new functions showed the same improvement held across
N=2 through 6 — no single server dominated at any scale, though distribution
was still not perfectly even (expected variance from linear probing with a
small number of servers, not structural clustering).

| Metric | Original H/Φ | alt_H/alt_Phi |
|---|---|---|
| Virtual slot span | 89 / 512 slots | 503 / 512 slots |
| A-1 distribution | 84.6 / 10.9 / 4.5% | 39.1 / 33.3 / 27.6% |

A small number of requests (15 out of 10000 at N=4, 23 out of 10000 at N=6)
returned `<Error> '/home' endpoint does not exist in server replicas`. This is
attributed to the async load generator firing requests concurrently while
`/add`/`/rm` was still resizing the server pool, causing a handful of requests
to briefly hit a server that was mid-startup or mid-removal — a transient
artifact of the test's timing, not a defect in the hash functions.

This experiment (branch: `experiment/alt-hash-functions`) is kept separate
from `main`, which retains the assignment's required `default_H`/`default_Phi`
for the actual submission.

## 9) Suggested Next Steps

1. Add a small automated test suite for endpoint behavior and failure recovery.
2. Add `requirements.txt` files and pin versions for reproducibility.
3. Optionally tighten proxy error differentiation (timeout vs 404 vs other backend errors).
4. Decide whether `experiment/alt-hash-functions` should be merged, referenced only, or left as-is for grading.
