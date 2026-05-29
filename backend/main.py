import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.utils.logger import logger
from app.database.mongo_client import init_db, db
from app.cache.redis_client import init_cache
from app.api.endpoints import router as api_router
from app.workers.scheduler import start_scheduler, shutdown_scheduler, revalidate_all_streams_job
from app.services.playlist_service import PlaylistService

# Initialize Rate Limiter
limiter = Limiter(key_func=get_remote_address)

# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    description="HydraStream - Fast. Stable. Intelligent Streaming. IPTV Backend System.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Attach limiter properties
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production security
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API router
app.include_router(api_router)

@app.on_event("startup")
async def startup_event():
    logger.info("Initializing HydraStream Backend services...")
    
    # Initialize DB & Cache
    await init_db()
    await init_cache()
    
    # Check if database has channels; if empty, ingest initial subset asynchronously
    channel_count = await db.channels.count_documents({"stream_url": {"$exists": True}})
    if channel_count == 0:
        logger.info("No playable channels with stream URLs found. Triggering initial playlist ingestion in the background...")
        
        async def run_initial_ingest():
            # Ingest initial 250 channels for quick startup/testing
            count = await PlaylistService.parse_m3u_playlist(limit=250)
            if count > 0:
                logger.info("Initial ingestion complete! Running first-time stream revalidation...")
                await revalidate_all_streams_job()
                
        # Run asynchronously in the background so main server starts instantly
        asyncio.create_task(run_initial_ingest())
    else:
        logger.info(f"Database contains {channel_count} channels. Ready to stream.")
        
    # Start Scheduler
    start_scheduler()
    logger.info("HydraStream Backend successfully loaded!")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down HydraStream services...")
    shutdown_scheduler()
    logger.info("HydraStream Backend shut down successfully.")

@app.get("/")
async def root():
    return {
        "status": "online",
        "app": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "endpoints": {
            "api_v1_channels": "/api/v1/channels",
            "api_v1_categories": "/api/v1/categories",
            "api_v1_countries": "/api/v1/countries",
            "api_v1_trending": "/api/v1/trending",
            "api_v1_fastest": "/api/v1/channels/fastest",
            "api_v1_search": "/api/v1/search?q=sports",
            "documentation_swagger": "/docs"
        }
    }
