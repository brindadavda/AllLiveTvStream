import time
import json
import asyncio
import aiohttp
from typing import Dict, Any, Tuple
from app.config import settings
from app.utils.logger import logger

# Semaphore pools for concurrency throttling
http_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_VALIDATORS)
ffprobe_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_FFPROBE)

class StreamValidator:
    @staticmethod
    async def validate_level1(url: str) -> Tuple[str, float]:
        """
        Level 1: Quick Validation using aiohttp.
        Checks HTTP 200, measures latency, and confirms it's a valid manifest/stream.
        Returns (status, latency). Status can be 'working', 'dead', or 'unsupported'.
        """
        async with http_semaphore:
            start_time = time.time()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            
            try:
                # Use GET with a 10 second timeout and read only the first 1KB of content
                timeout = aiohttp.ClientTimeout(total=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers=headers, allow_redirects=True) as response:
                        if response.status != 200:
                            logger.debug(f"Level 1 failed for {url}: HTTP {response.status}")
                            return "dead", 0.0
                        
                        latency = (time.time() - start_time) * 1000.0  # in ms
                        
                        # Read first chunk of bytes to check manifest
                        try:
                            chunk = await response.content.read(1024)
                            chunk_str = chunk.decode("utf-8", errors="ignore").strip()
                        except Exception as e:
                            logger.debug(f"Level 1 failed to read body for {url}: {e}")
                            return "dead", latency
                        
                        # M3U8 manifest validation
                        if not chunk_str:
                            logger.debug(f"Level 1 empty body for {url}")
                            return "dead", latency
                            
                        # Standard manifest validation headers
                        if "#EXTM3U" in chunk_str or "#EXT-X-STREAM-INF" in chunk_str or "#EXTINF" in chunk_str:
                            return "working", latency
                        
                        # Check content type if manifest header is missing but HTTP 200 ok
                        content_type = response.headers.get("Content-Type", "").lower()
                        if "mpegurl" in content_type or "application/x-mpegurl" in content_type or "video/" in content_type:
                            return "working", latency
                            
                        # If it doesn't match standard HLS headers or content-type, we call it unsupported
                        logger.debug(f"Level 1 unsupported content type/headers for {url}: {content_type}")
                        return "unsupported", latency
                        
            except asyncio.TimeoutError:
                logger.debug(f"Level 1 timeout for {url}")
                return "dead", 0.0
            except Exception as e:
                logger.debug(f"Level 1 error for {url}: {e}")
                return "dead", 0.0

    @staticmethod
    async def validate_level2(url: str) -> Tuple[str, str]:
        """
        Level 2: Advanced Validation using ffprobe.
        Checks for actual video stream presence, codec, and resolution.
        Returns (status, resolution). Status can be 'working', 'dead', or 'unsupported'.
        """
        async with ffprobe_semaphore:
            # We construct ffprobe args to check for video stream details
            cmd = [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,codec_name",
                "-of", "json",
                "-timeout", "5000000",  # ffprobe timeout in microseconds (5 seconds)
                url
            ]
            
            try:
                # Launch ffprobe asynchronously
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                # Wait for process to complete with a hard timeout (6 seconds)
                try:
                    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=6.0)
                except asyncio.TimeoutError:
                    try:
                        process.kill()
                    except:
                        pass
                    logger.debug(f"Level 2 ffprobe timeout for {url}")
                    return "dead", "Unknown"
                
                if process.returncode != 0:
                    err_msg = stderr.decode().strip()
                    logger.debug(f"Level 2 ffprobe exit code {process.returncode} for {url}. Error: {err_msg}")
                    return "dead", "Unknown"
                
                # Parse JSON output
                out_str = stdout.decode().strip()
                if not out_str:
                    logger.debug(f"Level 2 ffprobe empty output for {url}")
                    return "unsupported", "Unknown" # No video stream
                    
                data = json.loads(out_str)
                streams = data.get("streams", [])
                
                if not streams:
                    logger.debug(f"Level 2 no video streams detected for {url}")
                    return "unsupported", "Unknown"
                
                video_stream = streams[0]
                width = video_stream.get("width")
                height = video_stream.get("height")
                codec = video_stream.get("codec_name")
                
                if not width or not height:
                    return "working", "Unknown"
                
                # Determine resolution standard tag
                if height >= 1080:
                    resolution = "1080p"
                elif height >= 720:
                    resolution = "720p"
                elif height >= 480:
                    resolution = "480p"
                elif height >= 360:
                    resolution = "360p"
                else:
                    resolution = f"{height}p"
                
                logger.debug(f"Level 2 verified stream: {url} | {codec} | {resolution}")
                return "working", resolution
                
            except Exception as e:
                logger.debug(f"Level 2 ffprobe error for {url}: {e}")
                return "dead", "Unknown"

    @classmethod
    async def validate_stream(cls, url: str) -> Dict[str, Any]:
        """
        Runs both validations sequentially to assign a status and resolution.
        """
        # Run Level 1 validation
        status, latency = await cls.validate_level1(url)
        
        # If dead or unsupported in Level 1, we return immediately
        if status in ("dead", "unsupported"):
            return {
                "status": status,
                "latency": latency,
                "resolution": "Unknown"
            }
            
        # Run Level 2 validation
        status2, resolution = await cls.validate_level2(url)
        
        # If Level 2 detects it's dead, we mark it dead
        if status2 == "dead":
            return {
                "status": "dead",
                "latency": latency,
                "resolution": "Unknown"
            }
            
        return {
            "status": "working" if status2 == "working" else "unsupported",
            "latency": latency,
            "resolution": resolution
        }
