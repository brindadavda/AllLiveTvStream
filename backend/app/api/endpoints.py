import json
from fastapi import APIRouter, Query, HTTPException, Request
from typing import List, Optional
from app.config import settings
from app.utils.logger import logger
from app.database.mongo_client import db
from app.cache.redis_client import redis_client
from app.schemas.channel import (
    ChannelResponse, ChannelListResponse, CategoryCount, CountryCount
)

router = APIRouter(prefix="/api/v1")

@router.get("/channels", response_model=ChannelListResponse)
async def get_channels(
    request: Request,
    country: Optional[str] = Query(None, description="Filter by Country name"),
    category: Optional[str] = Query(None, description="Filter by Category"),
    language: Optional[str] = Query(None, description="Filter by Language"),
    working_only: bool = Query(True, description="Only return working streams"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page")
):
    """
    Get paginated channels with optional filters.
    Caches responses to Redis for sub-millisecond delivery.
    """
    # Create a unique cache key based on query filters
    cache_key = f"cache:channels:country={country}:category={category}:language={language}:working_only={working_only}:page={page}:limit={limit}"
    
    try:
        cached_val = await redis_client.get(cache_key)
        if cached_val:
            logger.info(f"Cache HIT for channels query: {cache_key}")
            # Decode bytes if returned by redis
            data_str = cached_val.decode("utf-8") if isinstance(cached_val, bytes) else cached_val
            return json.loads(data_str)
    except Exception as e:
        logger.warning(f"Error fetching from cache: {e}")

    logger.info(f"Cache MISS for channels query: {cache_key}. Fetching from MongoDB...")

    # Build DB filter query
    query = {"active": True, "stream_url": {"$exists": True}}
    if working_only:
        query["status"] = "working"
    if country:
        query["country"] = country
    if category:
        query["category"] = category
    if language:
        query["language"] = language

    # Pagination logic
    skip = (page - 1) * limit
    
    total = await db.channels.count_documents(query)
    
    cursor = db.channels.find(query)
    # Apply sorting (default working first, then alphabetical)
    cursor = cursor.sort([("status", 1), ("name", 1)]).skip(skip).limit(limit)
    
    channels = await cursor.to_list(length=limit)
    
    # Render response dictionary
    pages = (total + limit - 1) // limit if total > 0 else 0
    response_data = {
        "total": total,
        "page": page,
        "limit": limit,
        "pages": pages,
        "channels": channels
    }
    
    # Store response in Redis cache (TTL: 5 minutes)
    try:
        await redis_client.set(cache_key, json.dumps(response_data), ex=300)
    except Exception as e:
        logger.warning(f"Error saving to cache: {e}")
        
    return response_data

@router.get("/search", response_model=ChannelListResponse)
async def search_channels(
    q: str = Query(..., min_length=1, description="Search query"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100)
):
    """
    Search channels by query matching name, category, country, or language.
    Uses Mongo regex indexing for fast search.
    """
    query = {
        "active": True,
        "stream_url": {"$exists": True},
        "$or": [
            {"name": {"$regex": q, "$options": "i"}},
            {"category": {"$regex": q, "$options": "i"}},
            {"country": {"$regex": q, "$options": "i"}},
            {"language": {"$regex": q, "$options": "i"}}
        ]
    }
    
    skip = (page - 1) * limit
    total = await db.channels.count_documents(query)
    
    cursor = db.channels.find(query)
    cursor = cursor.sort([("status", 1), ("name", 1)]).skip(skip).limit(limit)
    
    channels = await cursor.to_list(length=limit)
    pages = (total + limit - 1) // limit if total > 0 else 0
    
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "pages": pages,
        "channels": channels
    }

@router.get("/channel/{id}", response_model=ChannelResponse)
async def get_channel_detail(id: str):
    """
    Fetches the details of a single channel.
    Tracks trending score by incrementing hits count in Redis.
    """
    channel = await db.channels.find_one({"_id": id})
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
        
    # Increment trending score in Redis
    try:
        await redis_client.zincrby("trending_channels", 1.0, id)
    except Exception as e:
        logger.warning(f"Failed to increment trending score in Redis: {e}")
        
    return channel

@router.get("/channels/fastest", response_model=List[ChannelResponse])
async def get_fastest_channels(
    limit: int = Query(10, ge=1, le=50, description="Number of items to return")
):
    """
    Returns working channels sorted by latency ascending.
    """
    query = {"active": True, "status": "working", "latency": {"$ne": 0.0}, "stream_url": {"$exists": True}}
    cursor = db.channels.find(query)
    cursor = cursor.sort("latency", 1).limit(limit)
    return await cursor.to_list(length=limit)

@router.get("/categories", response_model=List[CategoryCount])
async def get_categories():
    """
    Return distinct categories and their aggregate channel counts.
    """
    cache_key = "cache:categories"
    try:
        cached_val = await redis_client.get(cache_key)
        if cached_val:
            logger.info("Cache HIT for categories query")
            data_str = cached_val.decode("utf-8") if isinstance(cached_val, bytes) else cached_val
            return json.loads(data_str)
    except Exception as e:
        logger.warning(f"Error fetching categories from cache: {e}")

    # Using dynamic MongoDB aggregations or fallback mock distinct queries
    categories = await db.channels.distinct("category", {"active": True, "stream_url": {"$exists": True}})
    
    results = []
    for cat in categories:
        count = await db.channels.count_documents({"active": True, "category": cat, "stream_url": {"$exists": True}})
        results.append({"category": cat, "count": count})
        
    # Sort categories by channel counts descending
    results.sort(key=lambda x: x["count"], reverse=True)

    try:
        await redis_client.set(cache_key, json.dumps(results), ex=300)
    except Exception as e:
        logger.warning(f"Error saving categories to cache: {e}")

    return results

@router.get("/countries", response_model=List[CountryCount])
async def get_countries():
    """
    Return distinct countries and their aggregate channel counts.
    """
    cache_key = "cache:countries"
    try:
        cached_val = await redis_client.get(cache_key)
        if cached_val:
            logger.info("Cache HIT for countries query")
            data_str = cached_val.decode("utf-8") if isinstance(cached_val, bytes) else cached_val
            return json.loads(data_str)
    except Exception as e:
        logger.warning(f"Error fetching countries from cache: {e}")

    countries = await db.channels.distinct("country", {"active": True, "stream_url": {"$exists": True}})
    
    results = []
    for c in countries:
        count = await db.channels.count_documents({"active": True, "country": c, "stream_url": {"$exists": True}})
        results.append({"country": c, "count": count})
        
    # Sort countries by count descending
    results.sort(key=lambda x: x["count"], reverse=True)

    try:
        await redis_client.set(cache_key, json.dumps(results), ex=300)
    except Exception as e:
        logger.warning(f"Error saving countries to cache: {e}")

    return results

@router.get("/trending", response_model=List[ChannelResponse])
async def get_trending_channels(
    limit: int = Query(10, ge=1, le=50)
):
    """
    Returns top N trending channels based on Redis zincrby hits.
    Falls back to fastest/working channels if no trending history exists.
    """
    trending_list = []
    try:
        # Get top trending channel IDs from Redis sorted set
        raw_items = await redis_client.zrevrange("trending_channels", 0, limit - 1)
        # Decode bytes if necessary
        trending_ids = [item.decode("utf-8") if isinstance(item, bytes) else item for item in raw_items]
        
        # Load details for trending ids
        for chan_id in trending_ids:
            chan = await db.channels.find_one({"_id": chan_id})
            if chan:
                trending_list.append(chan)
    except Exception as e:
        logger.warning(f"Error fetching trending data from Redis: {e}")
        
    # Fallback to working channels if no trending hits yet
    if not trending_list:
        cursor = db.channels.find({"active": True, "status": "working", "stream_url": {"$exists": True}})
        cursor = cursor.limit(limit)
        trending_list = await cursor.to_list(length=limit)
        
    return trending_list
