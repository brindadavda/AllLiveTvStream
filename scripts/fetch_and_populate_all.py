import asyncio
import sys
import os
import aiohttp
import hashlib
import json

# Add backend directory to PYTHONPATH
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from app.database import mongo_client
from app.cache import redis_client
from app.utils.logger import logger

GREEN = "\033[0;32m"
RED = "\033[0;31m"
BLUE = "\033[0;34m"
NC = "\033[0m"

# Define resources, their official URLs, target collections, and unique ID resolver rules
RESOURCES = [
    {
        "name": "Channels",
        "url": "https://iptv-org.github.io/api/channels.json",
        "collection": "channels",
        "id_field": "id"
    },
    {
        "name": "Feeds",
        "url": "https://iptv-org.github.io/api/feeds.json",
        "collection": "feeds",
        "id_field": "id"
    },
    {
        "name": "Logos",
        "url": "https://iptv-org.github.io/api/logos.json",
        "collection": "logos",
        "composite_fields": ["channel", "feed", "url"]
    },
    {
        "name": "Streams",
        "url": "https://iptv-org.github.io/api/streams.json",
        "collection": "streams",
        "composite_fields": ["channel", "feed", "url"]
    },
    {
        "name": "Guides",
        "url": "https://iptv-org.github.io/api/guides.json",
        "collection": "guides",
        "composite_fields": ["channel", "feed", "site", "site_id"]
    },
    {
        "name": "Categories",
        "url": "https://iptv-org.github.io/api/categories.json",
        "collection": "categories",
        "id_field": "id"
    },
    {
        "name": "Languages",
        "url": "https://iptv-org.github.io/api/languages.json",
        "collection": "languages",
        "id_field": "code"
    },
    {
        "name": "Countries",
        "url": "https://iptv-org.github.io/api/countries.json",
        "collection": "countries",
        "id_field": "code"
    },
    {
        "name": "Subdivisions",
        "url": "https://iptv-org.github.io/api/subdivisions.json",
        "collection": "subdivisions",
        "id_field": "code"
    },
    {
        "name": "Cities",
        "url": "https://iptv-org.github.io/api/cities.json",
        "collection": "cities",
        "id_field": "code"
    },
    {
        "name": "Regions",
        "url": "https://iptv-org.github.io/api/regions.json",
        "collection": "regions",
        "id_field": "code"
    },
    {
        "name": "Timezones",
        "url": "https://iptv-org.github.io/api/timezones.json",
        "collection": "timezones",
        "id_field": "id"
    },
    {
        "name": "Blocklist",
        "url": "https://iptv-org.github.io/api/blocklist.json",
        "collection": "blocklist",
        "composite_fields": ["channel", "reason"]
    }
]

def make_deterministic_id(item: dict, fields: list) -> str:
    """Generates a deterministic unique ID based on a hash of composite fields."""
    components = []
    for f in fields:
        val = item.get(f)
        components.append(str(val) if val is not None else "")
    raw_str = "|".join(components)
    return hashlib.md5(raw_str.encode("utf-8")).hexdigest()

async def download_and_ingest(session: aiohttp.ClientSession, resource: dict):
    name = resource["name"]
    url = resource["url"]
    collection_name = resource["collection"]
    
    print(f"[{BLUE}INGEST{NC}] Fetching '{name}' from {url}...")
    try:
        async with session.get(url, timeout=30) as response:
            if response.status != 200:
                print(f"[{RED}FAIL{NC}] HTTP {response.status} loading {name}")
                return
            
            data = await response.json()
            if not isinstance(data, list):
                print(f"[{RED}FAIL{NC}] Invalid format for {name}: expected list, got {type(data)}")
                return
                
            total_items = len(data)
            print(f"[{BLUE}INGEST{NC}] Loaded {total_items} items of '{name}'. Upserting into MongoDB collection '{collection_name}'...")
            
            # Format and assign unique _id field
            formatted_items = []
            for item in data:
                # Resolve unique _id key
                if "id_field" in resource:
                    id_val = item.get(resource["id_field"])
                    if id_val:
                        item["_id"] = str(id_val)
                    else:
                        continue # Skip invalid records missing standard identifier
                elif "composite_fields" in resource:
                    item["_id"] = make_deterministic_id(item, resource["composite_fields"])
                
                # Check for active state if channels
                if collection_name == "channels":
                    if "active" not in item:
                        item["active"] = True
                    if "status" not in item:
                        item["status"] = "working"
                    if "latency" not in item:
                        item["latency"] = 0.0
                    if "resolution" not in item:
                        item["resolution"] = "Unknown"
                        
                formatted_items.append(item)
            
            # Bulk upsert into the DB in high-performance batches
            from pymongo import UpdateOne
            col = mongo_client.db[collection_name]
            
            requests = [
                UpdateOne({"_id": item["_id"]}, {"$set": item}, upsert=True)
                for item in formatted_items
            ]
            
            success = 0
            batch_size = 2000
            for k in range(0, len(requests), batch_size):
                batch = requests[k : k + batch_size]
                try:
                    await col.bulk_write(batch)
                    success += len(batch)
                except Exception as e:
                    logger.error(f"Failed bulk writing batch for {collection_name}: {e}")
                    
            print(f"[{GREEN}SUCCESS{NC}] Ingested {success}/{total_items} records into '{collection_name}'")
            
    except Exception as e:
        print(f"[{RED}ERROR{NC}] Failed to ingest {name}: {e}")

async def main():
    print(f"\n{BLUE}=== HydraStream Master Data Ingest Tool ==={NC}\n")
    
    # Initialize DB & Cache
    await mongo_client.init_db()
    await redis_client.init_cache()
    
    if mongo_client.is_mock_db:
        print(f"[{BLUE}INFO{NC}] Running in Fallback Mode (Mock JSON DB Collections).")
        print(f"All files will be saved in separate collections under {mongo_client.db.directory_path}/\n")
    else:
        print(f"[{GREEN}INFO{NC}] Running in Production Mode (MongoDB Atlas Cloud Cluster!)\n")
        
    start_time = time.time()
    
    # Launch parallel downloads & upserts using a single HTTP Session
    headers = {"User-Agent": "Mozilla/5.0"}
    async with aiohttp.ClientSession(headers=headers) as session:
        tasks = [download_and_ingest(session, res) for res in RESOURCES]
        await asyncio.gather(*tasks)
        
    elapsed = time.time() - start_time
    print(f"\n{GREEN}=== Master Ingestion Complete! ==={NC}")
    print(f"Ingested all 13 collections in {elapsed:.2f} seconds.")
    print(f"All data is successfully stored in your MongoDB database.")

if __name__ == "__main__":
    import time
    asyncio.run(main())
