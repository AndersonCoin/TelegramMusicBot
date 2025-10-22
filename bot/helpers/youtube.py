import yt_dlp
import asyncio
from config import Config

async def download_audio(url: str) -> dict:
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'outtmpl': str(Config.DOWNLOAD_DIR / '%(id)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
    }

    loop = asyncio.get_event_loop()
    
    def extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=True)

    info = await loop.run_in_executor(None, extract)
    
    file_path = Config.DOWNLOAD_DIR / f"{info['id']}.{info['ext']}"
    
    return {
        'id': info.get('id'),
        'title': info.get('title', 'Unknown Title'),
        'duration': int(info.get('duration', 0)),
        'thumbnail': info.get('thumbnail'),
        'url': info.get('webpage_url'),
        'file_path': str(file_path)
    }
