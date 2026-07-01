import asyncio, aiohttp, random, matplotlib.pyplot as plt
from collections import Counter

async def send_request(session, url):
    async with session.get(url) as r:
        data = await r.json()
        return data["message"]

async def run(n_requests=10000):
    async with aiohttp.ClientSession() as session:
        tasks = [send_request(session, "http://localhost:5000/home")
                 for _ in range(n_requests)]
        results = await asyncio.gather(*tasks)
    counts = Counter(results)
    plt.bar(counts.keys(), counts.values())
    plt.title("Request distribution across servers (N=3)")
    plt.savefig("A1_bar_chart.png")
    print(counts)

asyncio.run(run())
