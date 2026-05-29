import asyncio
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.config import settings
from app.utils.logger import logger
from app.database.mongo_client import db
from app.cache.redis_client import redis_client
from app.validators.stream_validator import StreamValidator
from app.services.playlist_service import PlaylistService

scheduler = AsyncIOScheduler()

async def revalidate_all_streams_job():
    """
    Periodic job that revalidates active streams in MongoDB.
    Runs every 30 minutes, measuring latency and updating working statuses.
    """
    logger.info("Starting background stream health validation job...")
    
    # Fetch active channels from DB
    cursor = db.channels.find({"active": True, "stream_url": {"$exists": True}})
    channels = await cursor.to_list(length=None)
    
    if not channels:
        logger.info("No active channels found in database to validate.")
        return
        
    logger.info(f"Validating {len(channels)} active streams...")
    
    # Helper validation task wrapper
    async def validate_and_update(chan: dict):
        url = chan["stream_url"]
        chan_id = chan["_id"]
        
        # Run validations
        result = await StreamValidator.validate_stream(url)
        
        # Build update fields
        update_fields = {
            "status": result["status"],
            "latency": result["latency"],
            "resolution": result["resolution"],
            "last_checked": datetime.utcnow().isoformat() + "Z"
        }
        
        # If dead, we mark it active: False (or keep it active, but requirements say "remove dead channels" or "status: dead" and filter working streams only)
        # We will keep active=True but change status='dead' so the API filter knows to exclude it
        await db.channels.update_one(
            {"_id": chan_id},
            {"$set": update_fields}
        )
        
        # Increment channel metrics in Redis
        # E.g. Set cache status for quick individual checks
        try:
            cache_key = f"channel_status:{chan_id}"
            await redis_client.set(cache_key, result["status"], ex=1800) # cache for 30 mins
        except Exception as e:
            logger.error(f"Failed to cache status in Redis for {chan_id}: {e}")

    # Launch revalidations concurrently (will be throttled by Semaphores internally!)
    start_time = asyncio.get_event_loop().time()
    tasks = [validate_and_update(chan) for chan in channels]
    await asyncio.gather(*tasks, return_exceptions=True)
    
    elapsed = asyncio.get_event_loop().time() - start_time
    logger.info(f"Background stream validation finished in {elapsed:.2f} seconds!")
    
    # Invalidate cached lists to force refresh on next request
    try:
        keys_to_delete = await redis_client.keys("cache:channels:*")
        if keys_to_delete:
            # Redis delete takes strings, but mock/real might return bytes. Let's normalize.
            decoded_keys = [k.decode("utf-8") if isinstance(k, bytes) else k for k in keys_to_delete]
            await redis_client.delete(*decoded_keys)
            logger.info(f"Invalidated {len(decoded_keys)} API response caches in Redis")
    except Exception as e:
        logger.error(f"Failed to clear Redis API caches: {e}")

async def refetch_playlists_job():
    """
    Periodic job that refetches lists and discovers new channels.
    Runs every 12 hours.
    """
    logger.info("Starting background playlist refresh job...")
    try:
        # Initial parse limit can be larger for background updates
        count = await PlaylistService.parse_m3u_playlist(limit=2000)
        logger.info(f"Background playlist ingestion complete! Discovered/Upserted {count} channels.")
        
        # Instantly run revalidation to verify status of newly ingested streams
        asyncio.create_task(revalidate_all_streams_job())
    except Exception as e:
        logger.error(f"Failed background playlist refresh: {e}")

def start_scheduler():
    """Starts APScheduler daemon."""
    if not scheduler.running:
        scheduler.add_job(
            revalidate_all_streams_job,
            "interval",
            minutes=settings.VALIDATION_INTERVAL_MINUTES,
            id="revalidate_streams",
            replace_existing=True
        )
        scheduler.add_job(
            refetch_playlists_job,
            "interval",
            hours=settings.PLAYLIST_REFETCH_HOURS,
            id="refetch_playlists",
            replace_existing=True
        )
        scheduler.start()
        logger.info("HydraStream Scheduler started successfully!")

def shutdown_scheduler():
    """Stops APScheduler daemon."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("HydraStream Scheduler stopped.")
