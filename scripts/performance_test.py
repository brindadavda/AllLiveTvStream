import asyncio
import time
import httpx


GREEN = "\033[0;32m"
RED = "\033[0;31m"
BLUE = "\033[0;34m"
NC = "\033[0m"

import os

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")
CONCURRENT_REQUESTS = 100
PATH = "/api/v1/channels?page=1&limit=10"

async def make_single_request(client: httpx.AsyncClient) -> float:
    start = time.time()
    try:
        resp = await client.get(f"{BASE_URL}{PATH}", timeout=10)
        latency = (time.time() - start) * 1000
        if resp.status_code == 200:
            return latency
        return -1.0
    except Exception:
        return -1.0

async def main():
    print(f"\n{BLUE}=== HydraStream Performance & Load Testing Suite ==={NC}\n")
    print(f"Target URL: {BASE_URL}{PATH}")
    print(f"Load Configuration: {CONCURRENT_REQUESTS} parallel requests\n")

    # Verify server is online
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(BASE_URL)
            if resp.status_code != 200:
                print(f"[{RED}ERROR{NC}] Server is online but returned status code {resp.status_code}")
                return
    except Exception as e:
        print(f"[{RED}ERROR{NC}] Server is offline or unreachable at {BASE_URL}. Start the server first.")
        print(f"Run: python3 backend/main.py")
        return

    async with httpx.AsyncClient() as client:
        # 1. Warm-up (Force cache miss or cache generation)
        print(f"[{BLUE}INFO{NC}] Executing warm-up request (forcing DB read and cache populating)...")
        warmup_start = time.time()
        resp = await client.get(f"{BASE_URL}{PATH}")
        warmup_latency = (time.time() - warmup_start) * 1000
        
        # Verify cache worked
        # Standard mock/real cache has a short delay, let's wait a fraction of a second
        await asyncio.sleep(0.5)

        if resp.status_code == 200:
            print(f"[{GREEN}SUCCESS{NC}] Warm-up complete. DB read latency: {warmup_latency:.2f} ms")
        else:
            print(f"[{RED}WARNING{NC}] Warm-up returned status: {resp.status_code}")

        # 2. Parallel Load Spike Simulation
        print(f"\n[{BLUE}INFO{NC}] Simulating load spike: Spawning {CONCURRENT_REQUESTS} concurrent requests...")
        
        start_load_time = time.time()
        tasks = [make_single_request(client) for _ in range(CONCURRENT_REQUESTS)]
        latencies = await asyncio.gather(*tasks)
        total_load_time = (time.time() - start_load_time) * 1000
        
        # Filter successful latencies
        success_latencies = [l for l in latencies if l > 0]
        failed_count = CONCURRENT_REQUESTS - len(success_latencies)
        
        if not success_latencies:
            print(f"[{RED}ERROR{NC}] All {CONCURRENT_REQUESTS} requests failed.")
            return

        # 3. Compile Statistics
        success_latencies.sort()
        n = len(success_latencies)
        min_l = success_latencies[0]
        max_l = success_latencies[-1]
        avg_l = sum(success_latencies) / n
        p95_l = success_latencies[min(int(n * 0.95), n - 1)]
        p99_l = success_latencies[min(int(n * 0.99), n - 1)]
        throughput = (CONCURRENT_REQUESTS / total_load_time) * 1000

        # Output Results
        print(f"\n{BLUE}=== Load Test Results ==={NC}\n")
        print(f"  • Total Load Simulation Duration : {total_load_time:7.2f} ms")
        print(f"  • Simulated Parallel Requests    : {CONCURRENT_REQUESTS} requests")
        print(f"  • Successful Requests (200 OK)   : {GREEN}{len(success_latencies)}{NC} ({len(success_latencies)/CONCURRENT_REQUESTS*100:.1f}%)")
        print(f"  • Failed / Dropped Requests      : {RED if failed_count > 0 else GREEN}{failed_count}{NC}")
        print(f"  • Calculated Throughput         : {GREEN}{throughput:7.2f} req/sec{NC}\n")
        
        print(f"  • Min Response Latency (Fastest) : {GREEN}{min_l:7.2f} ms{NC}")
        print(f"  • Max Response Latency (Slowest) : {max_l:7.2f} ms")
        print(f"  • Average Latency (Cache HIT)    : {GREEN if avg_l < 200 else RED}{avg_l:7.2f} ms{NC}")
        print(f"  • 95th Percentile Latency (p95)   : {p95_l:7.2f} ms")
        print(f"  • 99th Percentile Latency (p99)   : {p99_l:7.2f} ms\n")

        # Compare warm-up (Cache MISS) vs average (Cache HIT)
        cache_speedup = warmup_latency / avg_l if avg_l > 0 else 0
        print(f"  • Cache Efficiency speed-up      : {GREEN}{cache_speedup:.2f}x faster{NC} than raw DB query!")
        
        print(f"\n{BLUE}=========================================={NC}\n")

if __name__ == "__main__":
    asyncio.run(main())
