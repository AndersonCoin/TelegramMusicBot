"""YouTube download utilities."""

import asyncio
import logging
import yt_dlp
from typing import Optional, Dict, Any
from pathlib import Path
from config import Config

logger = logging.getLogger(__name__)

class YouTubeDownloader:
    """YouTube download manager."""
    
    YDL_OPTIONS = {
        "format": "bestaudio/best",
        "outtmpl": str(Config.DOWNLOAD_DIR / "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "extractaudio": True,
        "audioformat": "mp3",
        "nocheckcertificate": True,
        "geo_bypass": True,
        "age_limit": 0,
        "cookiefile": None,
        "nocheckcertificate": True,
    }
    
    @classmethod
    async def search(cls, query: str, limit: int = 1) -> Optional[Dict[str, Any]]:
        """Search YouTube for query."""
        def _search():
            with yt_dlp.YoutubeDL(cls.YDL_OPTIONS) as ydl:
                try:
                    results = ydl.extract_info(
                        f"ytsearch{limit}:{query}",
                        download=False
                    )
                    if results and results.get("entries"):
                        return results["entries"][0]
                except Exception as e:
                    logger.error(f"Search failed: {e}")
            return None
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _search)
    
    @classmethod
    async def get_info(cls, url: str) -> Optional[Dict[str, Any]]:
        """Get video info without downloading."""
        def _get_info():
            with yt_dlp.YoutubeDL(cls.YDL_OPTIONS) as ydl:
                try:
                    return ydl.extract_info(url, download=False)
                except Exception as e:
                    logger.error(f"Info extraction failed: {e}")
            return None
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _get_info)
    
    @classmethod
    async def download(cls, url: str) -> Optional[tuple[str, Dict[str, Any]]]:
        """Download audio from URL."""
        def _download():
            options = cls.YDL_OPTIONS.copy()
            
            with yt_dlp.YoutubeDL(options) as ydl:
                try:
                    info = ydl.extract_info(url, download=True)
                    
                    # Get downloaded file path
                    filename = ydl.prepare_filename(info)
                    # Handle various extensions
                    for ext in [".mp3", ".m4a", ".webm", ".opus"]:
                        file_path = Path(filename).with_suffix(ext)
                        if file_path.exists():
                            return str(file_path), info
                    
                    # Fallback to original
                    if Path(filename).exists():
                        return filename, info
                        
                except Exception as e:
                    logger.error(f"Download failed: {e}")
            return None, None
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _download)
    
    @classmethod
    def extract_info(cls, info: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant info from yt-dlp response."""
        return {
            "title": info.get("title", "Unknown"),
            "duration": info.get("duration", 0),
            "url": info.get("webpage_url", ""),
            "thumbnail": info.get("thumbnail", ""),
            "uploader": info.get("uploader", "Unknown"),
            "view_count": info.get("view_count", 0)
        }
