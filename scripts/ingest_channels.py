import asyncio
import sys
import os

# Add backend directory to PYTHONPATH
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from app.database import mongo_client
from app.cache import redis_client
from app.services.playlist_service import PlaylistService
from app.workers.scheduler import revalidate_all_streams_job

async def main():
    print("=== HydraStream Channel Ingest Tool ===")
    
    # 1. Initialize DB & Cache
    await mongo_client.init_db()
    await redis_client.init_cache()
    
    if mongo_client.is_mock_db:
        print("\n[WARNING] Running in Fallback Mode (Mock JSON DB).")
        print("To ingest directly into your Cloud MongoDB Atlas cluster, make sure your IP is whitelisted!")
    else:
        print("\n[SUCCESS] Connected to MongoDB Atlas Cloud Cluster!")
        
    limit = 250
    print(f"\n1. Fetching, parsing, and enriching the first {limit} channels from IPTV-org...")
    
    # Run the ingestion service
    count = await PlaylistService.parse_m3u_playlist(limit=limit)
    
    if count == 0:
        print("[ERROR] Ingestion failed. Check network connectivity or logs.")
        return
        
    print(f"[SUCCESS] Ingested {count} channels into database!")
    
    # 2. Revalidate stream health
    print("\n2. Launching health validation check on ingested streams...")
    await revalidate_all_streams_job()
    
    print("\n=== Ingestion Completed Successfully! ===")
    print("Your database is now populated with fully working streams.")

if __name__ == "__main__":
    asyncio.run(main())
