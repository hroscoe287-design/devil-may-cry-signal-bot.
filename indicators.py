import numpy as np
import pandas as pd

def ema(s, n): return s.ewm(span=n, adjust=False).mean()

def smma(s, n):
    out = pd.Series(np.nan, index=s.index, dtype=float)
    if len(s) < n: return out
    out.iloc[n-1] = s.iloc[:n].mean()
    for i in range(n, len(s)): out.iloc[i] = (out.iloc[i-1]*(n-1)+s.iloc[i])/n
    return out

def alligator(df):
    median = (df.high.astype(float) + df.low.astype(float)) / 2
    return smma(median, 13), smma(median, 8), smma(median, 5)

def aroon(df, period):
    hi, lo = df.high.astype(float), df.low.astype(float)
    up = hi.rolling(period+1).apply(lambda x: 100*(np.argmax(x)/period), raw=True)
    down = lo.rolling(period+1).apply(lambda x: 100*(np.argmin(x)/period), raw=True)
    return up, down

def osma(close, fast, slow, signal):
    osc = ema(close, fast)-ema(close, slow)
    sig = ema(osc, signal)
    return osc, sig, osc-sig

def atr(df, n=14):
    pc = df.close.shift()
    tr = pd.concat([df.high-df.low, (df.high-pc).abs(), (df.low-pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False, min_periods=n).mean()

def adx_di(df, n=14):
    high, low = df.high.astype(float), df.low.astype(float)
    up_move, down_move = high.diff(), -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)
    previous_close = df.close.astype(float).shift()
    tr = pd.concat([high-low, (high-previous_close).abs(), (low-previous_close).abs()], axis=1).max(axis=1)
    smooth_tr = tr.ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1/n, adjust=False, min_periods=n).mean() / smooth_tr.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1/n, adjust=False, min_periods=n).mean() / smooth_tr.replace(0, np.nan)
    dx = 100 * (plus_di-minus_di).abs() / (plus_di+minus_di).replace(0, np.nan)
    adx_line = dx.ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    return adx_line, plus_di, minus_di

def fractals(df, period=3):
    # Setting 3: three-candle pivot (one candle on either side).
    # Only emit once the right-side candle has closed.
    up_arrow = down_arrow = False
    if len(df) >= period:
        pivot = len(df) - 2
        left = period // 2
        start = pivot - left
        window_high = df.high.astype(float).iloc[start:pivot+left+1]
        window_low = df.low.astype(float).iloc[start:pivot+left+1]
        pivot_high = float(df.high.iloc[pivot])
        pivot_low = float(df.low.iloc[pivot])
        up_arrow = bool(pivot_high == window_high.max() and (window_high == pivot_high).sum() == 1)
        down_arrow = bool(pivot_low == window_low.min() and (window_low == pivot_low).sum() == 1)
    return up_arrow, down_arrow

def calculate(candles, tf):
    if len(candles) < 35:
        return {"ready": False, "reason": "Waiting for 35 candles", "values": {}}
    df = pd.DataFrame(candles)
    c = df.close.astype(float)
    scale = max(1, round(tf/10))
    aroon_n = max(10, min(50, 10*scale))
    osma_fast = max(5, min(30, 10*scale))
    osma_slow = max(osma_fast+2, min(60, 20*scale))
    osma_signal = max(5, min(30, 10*scale))
    jaw, teeth, lips = alligator(df)
    au, ad = aroon(df, aroon_n)
    om, oms, oh = osma(c, osma_fast, osma_slow, osma_signal)
    adx_line, plus_di, minus_di = adx_di(df)
    fractal_period = 3
    up_arrow, down_arrow = fractals(df, fractal_period)
    atrv = atr(df)
    last = lambda s: float(s.iloc[-1]) if pd.notna(s.iloc[-1]) else None
    prev = lambda s: float(s.iloc[-2]) if len(s) > 1 and pd.notna(s.iloc[-2]) else None
    candle_range = max(1e-12, float(df.high.iloc[-1])-float(df.low.iloc[-1]))
    body_ratio = abs(float(df.close.iloc[-1])-float(df.open.iloc[-1]))/candle_range
    direction = "CALL" if c.iloc[-1] > float(df.open.iloc[-1]) else "PUT" if c.iloc[-1] < float(df.open.iloc[-1]) else "WAIT"
    if direction == "CALL":
        opposing_wick = max(0.0, float(df.high.iloc[-1])-max(float(df.open.iloc[-1]), float(df.close.iloc[-1])))
    elif direction == "PUT":
        opposing_wick = max(0.0, min(float(df.open.iloc[-1]), float(df.close.iloc[-1]))-float(df.low.iloc[-1]))
    else:
        opposing_wick = candle_range
    wick_ratio = opposing_wick/candle_range
    plus_now, minus_now = last(plus_di), last(minus_di)
    plus_prev, minus_prev = prev(plus_di), prev(minus_di)
    di_spread = plus_now-minus_now if plus_now is not None and minus_now is not None else None
    di_spread_prev = plus_prev-minus_prev if plus_prev is not None and minus_prev is not None else None
    aroon_spread = last(au)-last(ad) if last(au) is not None and last(ad) is not None else None
    aroon_spread_prev = prev(au)-prev(ad) if prev(au) is not None and prev(ad) is not None else None
    alligator_mouth_prev = abs(prev(lips)-prev(jaw)) if prev(lips) is not None and prev(jaw) is not None else None
    return {"ready": True, "values": {
        "price": float(c.iloc[-1]), "jaw": last(jaw), "teeth": last(teeth), "lips": last(lips),
        "jaw_prev": prev(jaw), "teeth_prev": prev(teeth), "lips_prev": prev(lips),
        "alligator_mouth_prev": alligator_mouth_prev,
        "aroon_up": last(au), "aroon_down": last(ad), "aroon_spread_prev": aroon_spread_prev,
        "osma": last(om), "osma_signal": last(oms), "osma_hist": last(oh), "osma_hist_prev": prev(oh),
        "adx": last(adx_line), "plus_di": plus_now, "minus_di": minus_now,
        "plus_di_prev": plus_prev, "minus_di_prev": minus_prev,
        "di_spread": di_spread, "di_spread_prev": di_spread_prev,
        "fractal_up_arrow": up_arrow, "fractal_down_arrow": down_arrow,
        "fractal_period": fractal_period,
        "fractal_mapping": {"up_arrow": "PUT", "down_arrow": "CALL"},
        "candle_direction": direction, "candle_body_ratio": body_ratio,
        "opposing_wick_ratio": wick_ratio, "atr": last(atrv),
        "aroon_period": aroon_n, "osma_fast": osma_fast, "osma_slow": osma_slow,
        "osma_signal_period": osma_signal,
    }}
