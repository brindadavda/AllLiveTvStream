import asyncio
import sys
import os

# Add backend directory to PYTHONPATH
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from app.database import mongo_client

async def main():
    await mongo_client.init_db()
    db = mongo_client.db
    
    # 1. Get distinct language from channels
    distinct_langs = await db.channels.distinct("language", {"active": True, "stream_url": {"$exists": True}})
    print("NEW PLAYABLE DISTINCT LANGUAGES IN DB:", len(distinct_langs), distinct_langs)
    
    # 2. Get samples from channels for languages other than English or US
    cursor = db.channels.find({"language": {"$ne": "English"}}).limit(5)
    channels = await cursor.to_list(length=5)
    print("\nSAMPLE NON-ENGLISH CHANNELS:")
    for c in channels:
        print(f"Name: {c.get('name')} | Language: {c.get('language')} | Country: {c.get('country')}")

if __name__ == "__main__":
    asyncio.run(main())
