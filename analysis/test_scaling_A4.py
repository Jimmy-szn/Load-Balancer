import asyncio, aiohttp, requests
from collections import Counter
import matplotlib.pyplot as plt

BASE = "http://localhost:5000"
N_VALUES = [2, 3, 4, 5, 6]

async def send_request(session, url):
    async with session.get(url) as r:
        data = await r.json()
        return data["message"]

async def fire_requests(n_requests=10000):
    async with aiohttp.ClientSession() as session:
        tasks = [send_request(session, f"{BASE}/home") for _ in range(n_requests)]
        results = await asyncio.gather(*tasks)
    return Counter(results)

def set_server_count(target_n):
    current = requests.get(f"{BASE}/rep").json()["message"]["N"]
    if target_n > current:
        requests.post(f"{BASE}/add", json={"n": target_n - current, "hostnames": []})
    elif target_n < current:
        requests.delete(f"{BASE}/rm", json={"n": current - target_n, "hostnames": []})

def main():
    avg_loads = []
    for n in N_VALUES:
        set_server_count(n)
        actual_n = requests.get(f"{BASE}/rep").json()["message"]["N"]
        counts = asyncio.run(fire_requests(10000))
        total = sum(counts.values())
        avg = total / actual_n if actual_n else 0
        avg_loads.append(avg)
        print(f"N={actual_n}: total_handled={total}, avg_load={avg:.1f}, counts={dict(counts)}")

    plt.figure()
    plt.plot(N_VALUES, avg_loads, marker="o")
    plt.xlabel("Number of servers (N)")
    plt.ylabel("Average requests handled per server")
    plt.title("Average load vs N (10000 requests per run)")
    plt.savefig("A4_line_chart.png")

if __name__ == "__main__":
    main()
