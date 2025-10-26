import yt_dlp
from typing import Dict, Optional

async def download_song(query: str) -> Optional[Dict]:
    """
    Download song information from YouTube
    """
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            if query.startswith(('http://', 'https://')):
                info = ydl.extract_info(query, download=False)
            else:
                info = ydl.extract_info(f"ytsearch:{query}", download=False)
                if info['entries']:
                    info = info['entries'][0]
                else:
                    return None
            
            return {
                'title': info.get('title', 'Unknown'),
                'url': info['url'],
                'duration': format_duration(info.get('duration', 0)),
                'uploader': info.get('uploader', 'Unknown'),
                'thumbnail': info.get('thumbnail', ''),
                'id': info.get('id', '')
            }
    except Exception as e:
        print(f"Error downloading: {e}")
        return None

def format_duration(seconds: int) -> str:
    """Format duration from seconds to readable format"""
    if not seconds:
        return "Unknown"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes}:{seconds:02d}"
