# Devil May Cry — Independent Signal Bot

Independent Pocket Option signal-only service. It does not place trades and automatic execution is hard-disabled.

## Features
- Selectable chart periods: 5s, 10s, 15s, 30s, 1m, 2m, 3m, 5m, 10m, 15m, 30m, 1h, 4h, 1d.
- Williams Alligator baseline (SMMA 13/8/5).
- Aroon and OSMA adapt to the selected timeframe. The 10-second baseline is Aroon 10 and OSMA 10/20/10.
- Weighted 100-point confluence: Alligator 35, Aroon up to 25, OSMA 25, plus expansion/alignment confirmation.
- Broker asset update events are parsed dynamically; the seed list remains available while the broker catalog is pending.
- Dashboard and JSON APIs: /api/health, /api/state, /api/assets, /api/timeframes.

## Deploy
Create a Render Web Service from this repository. Build: `pip install -r requirements.txt`; Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`.
Set `PO_AUTH_JSON` to your current Pocket Option session payload. No credentials are committed.

## Important
The broker's updateAssets payload varies by account/region. The app only labels the catalog complete when it receives and parses broker-published symbols. The bundled list is a starter catalog, not a claim that all 361 instruments are present. Validate feed authentication and live quotes before relying on any signal. Signals are not guarantees of profit.
