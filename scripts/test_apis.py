import asyncio
import time
import httpx

GREEN = "\033[0;32m"
RED = "\033[0;31m"
BLUE = "\033[0;34m"
NC = "\033[0m"

BASE_URL = "http://127.0.0.1:8000"

async def test_endpoint(client: httpx.AsyncClient, name: str, path: str):
    start = time.time()
    try:
        resp = await client.get(f"{BASE_URL}{path}", timeout=10)
        latency = (time.time() - start) * 1000
        
        status = GREEN if resp.status_code == 200 else RED
        latency_color = GREEN if latency < 200 else RED
        
        print(f"[{status}{resp.status_code}{NC}] Test {BLUE}{name:25}{NC} | Path: {path:30} | Latency: {latency_color}{latency:7.2f} ms{NC}")
        
        # Print a tiny summary
        data = resp.json()
        if isinstance(data, dict):
            if "total" in data:
                print(f"      -> Total Items: {data['total']} | Returned: {len(data.get('channels', []))}")
            elif "status" in data:
                print(f"      -> Health: {data['status']} | App: {data['app']}")
        elif isinstance(data, list):
            print(f"      -> Returned Count: {len(data)}")
            if len(data) > 0:
                print(f"      -> Sample Item: {data[0]}")
    except Exception as e:
        print(f"[{RED}FAIL{NC}] Test {BLUE}{name}{NC} failed: {e}")

async def main():
    print(f"\n{BLUE}=== Starting HydraStream API Verification ==={NC}\n")
    async with httpx.AsyncClient() as client:
        # 1. Root index check
        await test_endpoint(client, "Health / Info Check", "/")
        
        # 2. Get categories
        await test_endpoint(client, "Get Categories list", "/api/v1/categories")
        
        # 3. Get countries
        await test_endpoint(client, "Get Countries list", "/api/v1/countries")
        
        # 4. Get working channels list
        await test_endpoint(client, "Get All Channels (Page 1)", "/api/v1/channels?page=1&limit=5")
        
        # 5. Search channels
        await test_endpoint(client, "Search Channels for 'News'", "/api/v1/search?q=News&limit=5")
        
        # 6. Fastest channels list
        await test_endpoint(client, "Fastest Channels", "/api/v1/channels/fastest?limit=5")
        
        # 7. Trending channels
        await test_endpoint(client, "Trending Channels", "/api/v1/trending?limit=5")
        
    print(f"\n{BLUE}=== API Verification Complete ==={NC}\n")

if __name__ == "__main__":
    asyncio.run(main())
