import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME: str = "HydraStream Backend"
    APP_ENV: str = "development"
    
    # MongoDB Config
    MONGO_URI: str = "mongodb+srv://davdabrinda_db_user:MGl9sD2Q93jCBybL@cluster0.uo1byzk.mongodb.net/hydra_stream?retryWrites=true&w=majority&appName=Cluster0&tlsAllowInvalidCertificates=true"
    MONGO_DB: str = "hydra_stream"
    
    # Redis Config
    REDIS_URI: str = "redis://localhost:6379"
    
    # Playlist & Sync
    PLAYLIST_URL: str = "https://iptv-org.github.io/iptv/index.m3u"
    PLAYLIST_REFETCH_HOURS: int = 12
    VALIDATION_INTERVAL_MINUTES: int = 30
    
    # Concurrency controls
    MAX_CONCURRENT_VALIDATORS: int = 50
    MAX_CONCURRENT_FFPROBE: int = 10
    
    # Fallback storage for DB when MongoDB is offline
    FALLBACK_DB_PATH: str = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "hydra_db.json")
    
    # Rate limit configurations
    RATE_LIMIT_DEFAULT: str = "100 per minute"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
