import re
import aiohttp
from typing import Dict, List, Any, Optional, Tuple
from app.config import settings
from app.utils.logger import logger
from app.models.channel import ChannelModel
from app.database.mongo_client import db

class PlaylistService:
    @staticmethod
    async def fetch_iptv_metadata() -> Tuple[Dict[str, Any], Dict[str, str], Dict[str, str]]:
        """
        Fetches metadata directories from IPTV-org in the background for precise enrichment.
        Returns: (channels_map, countries_map, languages_map)
        """
        channels_map = {}
        countries_map = {}
        languages_map = {}
        
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession(headers=headers) as session:
            # 1. Fetch Countries (to map ISO code to nice names)
            try:
                async with session.get("https://iptv-org.github.io/api/countries.json", timeout=10) as resp:
                    if resp.status == 200:
                        countries_list = await resp.json()
                        countries_map = {c["code"].upper(): c["name"] for c in countries_list if "code" in c and "name" in c}
                        logger.info(f"Loaded {len(countries_map)} countries from IPTV-org API")
            except Exception as e:
                logger.warning(f"Could not load countries metadata: {e}")

            # 2. Fetch Languages (to map code to nice names)
            try:
                async with session.get("https://iptv-org.github.io/api/languages.json", timeout=10) as resp:
                    if resp.status == 200:
                        languages_list = await resp.json()
                        languages_map = {l["code"].lower(): l["name"] for l in languages_list if "code" in l and "name" in l}
                        logger.info(f"Loaded {len(languages_map)} languages from IPTV-org API")
            except Exception as e:
                logger.warning(f"Could not load languages metadata: {e}")

            # 3. Fetch Channels Database (to map tvg-id to country, category, languages)
            try:
                async with session.get("https://iptv-org.github.io/api/channels.json", timeout=15) as resp:
                    if resp.status == 200:
                        channels_list = await resp.json()
                        for c in channels_list:
                            if "id" in c:
                                channels_map[c["id"]] = c
                        logger.info(f"Loaded {len(channels_map)} channels database items from IPTV-org API")
            except Exception as e:
                logger.warning(f"Could not load channels database metadata: {e}")
                
        return channels_map, countries_map, languages_map

    @classmethod
    async def parse_m3u_playlist(cls, limit: Optional[int] = 500) -> int:
        """
        Downloads and parses the index.m3u playlist.
        Enriches channel documents using official IPTV-org JSON records.
        Upserts the channels into the database.
        
        :param limit: Capping the number of parsed channels for initial performance (None for unlimited)
        """
        logger.info(f"Downloading IPTV playlist from: {settings.PLAYLIST_URL}...")
        
        m3u_content = ""
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(settings.PLAYLIST_URL, timeout=20) as resp:
                    if resp.status != 200:
                        logger.error(f"Failed to download M3U. HTTP Status: {resp.status}")
                        return 0
                    m3u_content = await resp.text()
                    logger.info("IPTV playlist downloaded successfully!")
        except Exception as e:
            logger.error(f"Error fetching playlist: {e}")
            return 0
            
        # Parse M3U
        lines = m3u_content.splitlines()
        if not lines or not lines[0].startswith("#EXTM3U"):
            logger.error("Invalid M3U playlist format: missing #EXTM3U header.")
            return 0
            
        # Fetch auxiliary metadata in the background
        channels_api_map, countries_api_map, languages_api_map = await cls.fetch_iptv_metadata()
        
        parsed_count = 0
        channels_to_save = []
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("#EXTINF"):
                # Parse attributes
                # Example: #EXTINF:-1 tvg-id="123tv.de@SD" tvg-logo="..." group-title="Shop",1-2-3 TV (270p)
                tvg_id_match = re.search(r'tvg-id="([^"]*)"', line)
                tvg_logo_match = re.search(r'tvg-logo="([^"]*)"', line)
                group_title_match = re.search(r'group-title="([^"]*)"', line)
                
                # Channel name is after the last comma
                name = "Unknown Channel"
                if "," in line:
                    name = line.split(",", 1)[1].strip()
                    
                tvg_id = tvg_id_match.group(1) if tvg_id_match else ""
                tvg_logo = tvg_logo_match.group(1) if tvg_logo_match else ""
                group_title = group_title_match.group(1) if group_title_match else ""
                
                # Fetch stream URL from subsequent lines (skip optional #EXTVLCOPT lines)
                stream_url = ""
                i += 1
                while i < len(lines):
                    sub_line = lines[i].strip()
                    if not sub_line:
                        i += 1
                        continue
                    if sub_line.startswith("#"):
                        # Skip extra config lines like #EXTVLCOPT
                        i += 1
                        continue
                    stream_url = sub_line
                    break
                    
                if stream_url:
                    # Resolve enriched details from IPTV-org API metadata
                    country_code = "US"
                    country_name = "United States"
                    languages_str = "English"
                    category = group_title or "General"
                    logo = tvg_logo
                    
                    # Try lookup by tvg_id
                    if tvg_id and tvg_id in channels_api_map:
                        api_chan = channels_api_map[tvg_id]
                        # Logo
                        if not logo and api_chan.get("logo"):
                            logo = api_chan["logo"]
                        # Country
                        if api_chan.get("country"):
                            country_code = api_chan["country"].upper()
                            country_name = countries_api_map.get(country_code, country_code)
                        # Languages
                        if api_chan.get("languages"):
                            lang_codes = api_chan["languages"]
                            lang_names = [languages_api_map.get(l.lower(), l) for l in lang_codes]
                            languages_str = ";".join(lang_names) if lang_names else "English"
                        # Categories
                        if api_chan.get("categories"):
                            category_list = [c.capitalize() for c in api_chan["categories"]]
                            category = ";".join(category_list)
                    else:
                        # Fallback parsing directly from tvg_id or group-title
                        # E.g., tvg-id="123tv.de@SD" -> country code: de
                        if tvg_id and "." in tvg_id:
                            parts = tvg_id.split(".")
                            inferred_code = parts[-1].split("@")[0].upper()
                            if len(inferred_code) == 2:
                                country_code = inferred_code
                                country_name = countries_api_map.get(country_code, country_code)
                                
                    # Normalize category representation
                    main_category = category.split(";")[0] if ";" in category else category
                    main_language = languages_str.split(";")[0] if ";" in languages_str else languages_str
                    
                    # Extract resolution hint from name if possible
                    resolution = "Unknown"
                    res_match = re.search(r'\((\d+p|HD|SD|FHD|UHD)\)', name)
                    if res_match:
                        res_val = res_match.group(1)
                        if res_val in ("HD", "FHD", "UHD"):
                            resolution = "1080p" if res_val == "FHD" else ("720p" if res_val == "HD" else "2160p")
                        else:
                            resolution = res_val
                            
                    # Construct Database document
                    channel_doc = ChannelModel.to_db(
                        name=name,
                        stream_url=stream_url,
                        logo=logo,
                        country=country_name,  # Store nice country name or code
                        language=main_language,
                        category=main_category,
                        status="working",
                        latency=0.0,
                        resolution=resolution,
                        tvg_id=tvg_id,
                        group_title=group_title,
                        stream_format="hls" if "m3u8" in stream_url.lower() else "mp4"
                    )
                    channels_to_save.append(channel_doc)
                    parsed_count += 1
                    
                    if limit is not None and parsed_count >= limit:
                        logger.info(f"Reached ingestion limit of {limit} channels.")
                        break
                        
            i += 1
            
        # Bulk save channels in database
        logger.info(f"Upserting {len(channels_to_save)} parsed channels into database...")
        success_count = 0
        for chan in channels_to_save:
            try:
                # Upsert by ID (stream_url or tvg_id)
                await db.channels.update_one(
                    {"_id": chan["_id"]},
                    {"$set": chan},
                    upsert=True
                )
                success_count += 1
            except Exception as e:
                logger.error(f"Error saving channel {chan['name']}: {e}")
                
        logger.info(f"Ingested {success_count} channels successfully!")
        return success_count
