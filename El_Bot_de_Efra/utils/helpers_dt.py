# === utils/helpers_dt.py ===
from datetime import datetime, timedelta
import pandas as pd

def safe_is_valid_df(df):
    try:
        return df is not None and hasattr(df, "empty") and not df.empty
    except Exception:
        return False

def _parse_dt_like(x):
    if x is None:
        return None
    if isinstance(x, datetime):
        return x
    if isinstance(x, (int, float)):
        if x > 10**11:
            return datetime.fromtimestamp(x / 1000.0)
        return datetime.fromtimestamp(x)
    try:
        return pd.to_datetime(x).to_pydatetime()
    except Exception:
        return None

def safe_add_minutes(dt_like, minutes):
    try:
        base = _parse_dt_like(dt_like)
        mins = int(minutes) if minutes else 0
        if base is None:
            return None
        return base + timedelta(minutes=mins)
    except Exception:
        return None
