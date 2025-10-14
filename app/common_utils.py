from datetime import datetime, timezone

def get_current_utc_time() -> datetime:
    """Get the current UTC time without timezone info and microseconds."""
    return datetime.now(timezone.utc).replace(tzinfo=None).replace(microsecond=0)

