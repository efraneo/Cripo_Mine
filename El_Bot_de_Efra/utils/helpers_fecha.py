# === utils/helpers_fecha.py ===
import pandas as pd
import numpy as np

def _coerce_dt_series(x):
    """Convierte serie a datetime (maneja ms/seg/iso), sin tz."""
    if x is None:
        return None
    s = pd.Series(x)
    if np.issubdtype(s.dtype, np.datetime64):
        s = pd.to_datetime(s, errors="coerce")
    else:
        if np.issubdtype(s.dtype, np.integer):
            v = int(s.dropna().iloc[0]) if s.dropna().size else None
            if v and v > 10**11:
                s = pd.to_datetime(s, unit="ms", errors="coerce")
            else:
                s = pd.to_datetime(s, unit="s", errors="coerce")
        else:
            s = pd.to_datetime(s, errors="coerce")
    try:
        s = s.dt.tz_localize(None)
    except Exception:
        pass
    return s

def fix_df_velas_datetime(df):
    """Normaliza df_velas para graficar correctamente en Telegram."""
    if df is None or getattr(df, "empty", True):
        return df
    df = df.copy()
    cand_cols = ["datetime", "time", "open_time", "fecha", "date", "timestamp"]
    col = next((c for c in cand_cols if c in df.columns), None)
    if col is None:
        if isinstance(df.index, pd.DatetimeIndex):
            df["datetime"] = df.index
        else:
            try:
                df["datetime"] = _coerce_dt_series(df.index.to_series())
            except Exception:
                pass
    else:
        df["datetime"] = _coerce_dt_series(df[col])
    if "datetime" in df.columns:
        df = df.dropna(subset=["datetime"]).sort_values("datetime")
        df["datetime"] = pd.to_datetime(df["datetime"]).dt.to_pydatetime()
    return df
