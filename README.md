# Devil May Cry — Independent Signal Bot

Independent Pocket Option signal-only service. It does not place trades and automatic execution is hard-disabled.

## Weighted 100-point scoring
- ADX directional engine: 35 points (DI direction/ADX strength 10, DI separation 10, DI velocity 8, DI acceleration 7).
- Confirmed Fractal: 15 points; period 3, three closed candles on each side. User mapping: downward arrow = bullish/BUY; upward arrow = bearish/SELL.
- Aroon Up/Down: 15 points.
- OsMA: 12 points.
- Williams Alligator: 10 points.
- EMA 9/21: 5 points.
- MACD 12/26/9: 4 points.
- RSI period 5: 2 points.
- Fakeout protection: 2 points for a clean candle aligned with the leading side; weak bodies or large opposing wicks receive no protection points.

A signal is emitted only when the leading side scores at least 55/100 and leads the opposite side by at least 8 points. The displayed win-probability figure is an uncalibrated model estimate, not a measured historical win rate.

## Indicators and timeframe scaling
- Williams Alligator baseline: SMMA 13/8/5.
- Aroon and OsMA preserve the 30-second-candle baseline of Aroon 10 and OsMA 10/20/10, scaled proportionally with the selected timeframe.
- EMA 9/21, MACD 12/26/9, RSI 5, and ADX/DI are calculated from the selected timeframe's candle series.
- Selectable chart periods: 5s, 10s, 15s, 30s, 1m, 2m, 3m, 5m, 10m, 15m, 30m, 1h, 4h, 1d.

## Safety and operation
- Signal-only mode; automatic execution is hard-disabled.
- Broker asset update events are parsed dynamically; the seed list remains available while the broker catalog is pending.
- Dashboard and JSON APIs: /api/health, /api/state, /api/assets, /api/timeframes.
- Set PO_AUTH_JSON to the current Pocket Option session payload. No credentials are committed.
- Validate feed authentication and live quotes before relying on any signal. Signals are not guarantees of profit.
