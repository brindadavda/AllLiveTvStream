from datetime import datetime
from typing import Any, Dict, Optional

class ChannelModel:
    @staticmethod
    def to_db(
        name: str,
        stream_url: str,
        logo: Optional[str] = "",
        country: Optional[str] = "US",
        language: Optional[str] = "English",
        category: Optional[str] = "General",
        status: Optional[str] = "working",
        latency: Optional[float] = 0.0,
        resolution: Optional[str] = "Unknown",
        tvg_id: Optional[str] = "",
        group_title: Optional[str] = "General",
        stream_format: Optional[str] = "hls",
        active: Optional[bool] = True
    ) -> Dict[str, Any]:
        """Formats the data to be written into MongoDB."""
        return {
            "_id": tvg_id if tvg_id else stream_url,  # Unique identifier
            "name": name,
            "stream_url": stream_url,
            "logo": logo or "",
            "country": country or "US",
            "language": language or "English",
            "category": category or "General",
            "status": status or "working",
            "latency": latency or 0.0,
            "resolution": resolution or "Unknown",
            "last_checked": datetime.utcnow().isoformat() + "Z",
            "active": active if active is not None else True,
            "group_title": group_title or "General",
            "stream_format": stream_format or "hls"
        }
