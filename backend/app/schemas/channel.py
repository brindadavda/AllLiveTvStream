from pydantic import BaseModel, Field
from typing import List, Optional

class ChannelResponse(BaseModel):
    id: str = Field(alias="_id")
    name: str
    stream_url: str
    logo: Optional[str] = ""
    country: Optional[str] = "Unknown"
    language: Optional[str] = "Unknown"
    category: Optional[str] = "General"
    status: Optional[str] = "working"
    latency: Optional[float] = 0.0
    resolution: Optional[str] = "Unknown"
    last_checked: Optional[str] = ""
    active: Optional[bool] = True
    group_title: Optional[str] = "General"
    stream_format: Optional[str] = "hls"

    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "_id": "sony_max_in",
                "name": "Sony Max",
                "country": "IN",
                "language": "Hindi",
                "category": "Movies",
                "logo": "https://example.com/sony_max.png",
                "stream_url": "https://example.com/sony_max/index.m3u8",
                "status": "working",
                "latency": 210.5,
                "resolution": "720p",
                "last_checked": "2026-05-29T00:00:00Z",
                "active": True,
                "group_title": "Entertainment",
                "stream_format": "hls"
            }
        }

class ChannelListResponse(BaseModel):
    total: int
    page: int
    limit: int
    pages: int
    channels: List[ChannelResponse]

class CategoryCount(BaseModel):
    category: str
    count: int

class CountryCount(BaseModel):
    country: str
    count: int
