# Devil May Cry — Independent Signal Bot

Independent Pocket Option signal-only service. It never places trades; automatic execution is hard-disabled.

## Weighted 100-point scoring

| Indicator | Maximum |
|---|---:|
| ADX +DI / -DI direction and strength | 8 |
| DI separation | 7 |
| DI velocity | 6 |
| DI acceleration | 4 |
| Confirmed Fractal (setting 3) | 20 |
| Aroon Up / Down | 20 |
| OsMA | 25 |
| Williams Alligator | 10 |
| **Total** | **100** |

- ADX/DI components total 25 points. Direction, separation, velocity, and acceleration are scored independently; momentum can still earn points after a DI crossover.
- Fractal mapping: upward arrow = bearish/PUT; downward arrow = bullish/CALL. Period 3 confirms the pivot after three candles on each side.
- Aroon scores direction/separation and spread widening.
- OsMA scores histogram direction and strengthening momentum.
- Alligator scores line order and expanding mouth.
- There is no directional-margin or indicator-agreement gate. Indicator points accumulate independently. The leading direction emits a signal at 55/100.
- The displayed win-probability number is an uncalibrated model estimate, not a measured historical win rate.

## Timeframe adaptation

Aroon and OsMA lookbacks are recalculated whenever the selected chart timeframe changes, using the existing 30-second reference settings (Aroon 10; OsMA 10/20/10) and preserving their elapsed-time lookback. Other indicators are calculated from the selected timeframe's candles. Fractal period remains 3.

## Safety and operation

- Signal-only mode; automatic execution is hard-disabled.
- Broker asset update events are parsed dynamically; the seed catalog remains available while the broker catalog is pending.
- APIs: /api/health, /api/state, /api/assets, /api/timeframes.
- Set PO_AUTH_JSON to the current Pocket Option session payload. Credentials are not committed.
- Confirm authenticated live quotes before relying on a signal. Signals are not guarantees of profit.
