class DMCSignalEngine:
    """100-point DMC confluence engine. Signal-only; no order execution."""
    def evaluate(self, result):
        if not result.get("ready"):
            return {"signal": "WAIT", "score": 0, "confidence": 0,
                    "reason": result.get("reason", "Waiting for data"), "votes": []}

        v = result["values"]
        call = put = 0.0
        votes = []

        def award(name, side, points, detail=""):
            nonlocal call, put
            points = max(0.0, min(float(points), 100.0))
            if side == "CALL":
                call += points
            elif side == "PUT":
                put += points
            votes.append({"indicator": name, "direction": side if side else "WAIT",
                          "points": round(points, 1), "detail": detail})

        # 1) Williams Alligator — 20 points
        jaw, teeth, lips = v.get("jaw"), v.get("teeth"), v.get("lips")
        alligator = "WAIT"
        if None not in (jaw, teeth, lips):
            if lips > teeth > jaw:
                alligator = "CALL"
            elif lips < teeth < jaw:
                alligator = "PUT"
        award("Williams Alligator", alligator, 20 if alligator != "WAIT" else 0,
              "Lips/teeth/jaw alignment")

        # 2) ADX directional movement — 25 points
        plus_di, minus_di, adx = v.get("plus_di"), v.get("minus_di"), v.get("adx")
        di_side, di_points = "WAIT", 0.0
        di_spread = (plus_di - minus_di) if plus_di is not None and minus_di is not None else 0.0
        if plus_di is not None and minus_di is not None and di_spread != 0:
            di_side = "CALL" if di_spread > 0 else "PUT"
            separation = min(1.0, abs(di_spread) / 30.0)
            trend_factor = 0.55 + 0.45 * min(1.0, (adx or 0.0) / 35.0)
            di_points = 25.0 * separation * trend_factor
            # Reward a DI spread that is widening in the same direction.
            prev_spread = v.get("di_spread_prev")
            if prev_spread is not None and di_spread * (di_spread - prev_spread) > 0:
                di_points = min(25.0, di_points + 2.0)
        award("ADX +DI / -DI", di_side, di_points,
              f"+DI {plus_di!s} | -DI {minus_di!s} | ADX {adx!s} | spread {round(di_spread, 2)}")

        # 3) Aroon — 15 points
        au, ad = v.get("aroon_up"), v.get("aroon_down")
        aroon_side, aroon_points = "WAIT", 0.0
        if au is not None and ad is not None and au != ad:
            aroon_side = "CALL" if au > ad else "PUT"
            aroon_points = 15.0 * min(1.0, abs(au - ad) / 60.0)
        award("Aroon", aroon_side, aroon_points, f"Up {au!s} | Down {ad!s}")

        # 4) OsMA — 15 points
        hist, prev_hist = v.get("osma_hist"), v.get("osma_hist_prev")
        osma_side, osma_points = "WAIT", 0.0
        if hist is not None and hist != 0:
            osma_side = "CALL" if hist > 0 else "PUT"
            osma_points = 11.0
            if prev_hist is not None and ((hist > 0 and hist > prev_hist) or (hist < 0 and hist < prev_hist)):
                osma_points = 15.0
        award("OsMA", osma_side, osma_points, f"Histogram {hist!s}")

        # 5) Confirmed Williams fractals — 15 points.
        # User's explicit mapping: upward arrow = bearish/PUT; downward arrow = bullish/CALL.
        fractal_side = "WAIT"
        if v.get("fractal_up_arrow"):
            fractal_side = "PUT"
        elif v.get("fractal_down_arrow"):
            fractal_side = "CALL"
        award("Fractal", fractal_side, 15 if fractal_side != "WAIT" else 0,
              "Up arrow = bearish; down arrow = bullish")

        # 6) Candle body/momentum — 5 points
        candle_side, candle_points = v.get("candle_direction", "WAIT"), 0.0
        if candle_side in ("CALL", "PUT"):
            candle_points = 5.0 * min(1.0, max(0.0, v.get("candle_body_ratio", 0.0)) / 0.65)
        award("Candle strength", candle_side, candle_points,
              f"Body/range {round(v.get('candle_body_ratio', 0.0), 2)}")

        # 7) Fakeout / entry protection — up to 5 points for cleaner entries.
        # Large opposing wick or very small body receives no protection points.
        risk_side = di_side if di_side != "WAIT" else alligator
        wick_ratio = v.get("opposing_wick_ratio", 1.0)
        protection = 5.0 * max(0.0, min(1.0, (0.75 - wick_ratio) / 0.55))
        if risk_side not in ("CALL", "PUT") or v.get("candle_body_ratio", 0.0) < 0.12:
            protection = 0.0
        award("Fakeout / entry protection", risk_side, protection,
              f"Opposing wick ratio {round(wick_ratio, 2)}")

        score = max(call, put)
        side = "CALL" if call > put else "PUT" if put > call else "WAIT"
        margin = abs(call - put)
        signal = side if score >= 25 and margin >= 5 else "WAIT"
        confidence = min(100, round(score))
        # This is an uncalibrated display estimate, not a measured win rate.
        win_probability = (max(50, min(85, round(50 + max(0, score - 25) * 0.45)))
                           if signal != "WAIT" else 50)

        return {
            "signal": signal, "score": confidence, "confidence": confidence,
            "win_probability": win_probability,
            "probability_label": "UNCALIBRATED MODEL ESTIMATE",
            "call_score": round(call, 1), "put_score": round(put, 1),
            "reason": "Weighted Alligator/ADX/Aroon/OsMA/Fractal confluence" if signal != "WAIT"
                      else "No decisive directional edge yet",
            "votes": votes, "automatic_execution": False, "mode": "SIGNAL_ONLY",
            "settings": {k: v[k] for k in ("aroon_period", "osma_fast", "osma_slow", "osma_signal_period")
                         if k in v},
        }
