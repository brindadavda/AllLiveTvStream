import asyncio
import os
import sys

# Add the 'backend' directory to the Python path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from app.database.mongo_client import init_db, db

async def check():
    await init_db()
    total = await db.channels.count_documents({})
    active = await db.channels.count_documents({"active": True})
    stream_url_exists = await db.channels.count_documents({"stream_url": {"$exists": True}})
    active_stream = await db.channels.count_documents({"active": True, "stream_url": {"$exists": True}})
    working = await db.channels.count_documents({"status": "working"})
    active_working = await db.channels.count_documents({"active": True, "status": "working"})
    checking = await db.channels.count_documents({"status": "checking"})
    down = await db.channels.count_documents({"status": "down"})
    
    print("\nDATABASE STATUS REPORT:")
    print(f"Total documents in channels: {total}")
    print(f"Active channels: {active}")
    print(f"Channels with stream_url: {stream_url_exists}")
    print(f"Active with stream_url: {active_stream}")
    print(f"Status == 'working': {working}")
    print(f"Active and status == 'working': {active_working}")
    print(f"Status == 'checking': {checking}")
    print(f"Status == 'down': {down}")

if __name__ == "__main__":
    asyncio.run(check())
