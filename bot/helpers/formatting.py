"""Text formatting utilities."""

from typing import Optional

def format_duration(seconds: int) -> str:
    """Format duration in seconds to readable format."""
    if seconds < 0:
        return "00:00"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"

def create_progress_bar(
    current: int,
    total: int,
    length: int = 10
) -> str:
    """Create a progress bar string."""
    if total <= 0:
        return "─" * length
    
    filled = int((current / total) * length)
    bar = "█" * filled + "─" * (length - filled)
    return bar

def format_track_title(title: str, max_length: int = 50) -> str:
    """Format track title with max length."""
    if len(title) <= max_length:
        return title
    return title[:max_length-3] + "..."

def format_queue_list(tracks: list, page: int = 1, per_page: int = 10) -> tuple[str, int]:
    """Format queue list for display."""
    if not tracks:
        return "", 0
    
    total_pages = (len(tracks) + per_page - 1) // per_page
    start = (page - 1) * per_page
    end = min(start + per_page, len(tracks))
    
    lines = []
    for i in range(start, end):
        track = tracks[i]
        lines.append(
            f"{i+1}. **{format_track_title(track.title)}** - "
            f"{format_duration(track.duration)}"
        )
    
    return "\n".join(lines), total_pages
