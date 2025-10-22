def format_duration(seconds: int) -> str:
    if not seconds: return "00:00"
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"

def create_progress_bar(current: int, total: int, length: int = 12) -> str:
    if not total: return "─" * length
    percent = int((current / total) * 100)
    filled = int((length * current) // total)
    bar = "◉" * filled + "─" * (length - filled)
    return f"{bar} {percent}%"
