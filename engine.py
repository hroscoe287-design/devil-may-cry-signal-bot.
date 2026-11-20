class DMCSignalEngine:
    """Directional 100-point confluence engine. Signal-only; no order execution."""

    WEIGHTS = {
        "Fractal": 20,
        "ADX +DI / -DI": 30,
        "Aroon Up / Down": 20,
        "OsMA": 15,
        "Williams Alligator": 15,
    }

    @staticmethod
    def _clamp(value, low=0.0, high=1.0):
        return max(low, min(high, float(value)))

    def evaluate(self, result):
        if not result.get("ready"):
            return {"signal": "WAIT", "score": 0, "confidence": 0,
                    "reason": result.get("reason", "Waiting for data"), "votes": [],
                    "automatic_execution": False, "mode": "SIGNAL_ONLY"}

        v = result["values"]
        call = put = 0.0
        votes = []

        def award(name, side, points, detail):
            nonlocal call, put
            points = round(self._clamp(points, 0, self.WEIGHTS[name]), 1)
            if side == "CALL":
                call += points
            elif side == "PUT":
                put += points
            votes.append({
                "indicator": name, "direction": side or "WAIT",
                "points": points, "max_points": self.WEIGHTS[name],
                "detail": detail,
            })

        # Fractal setting 2 = faster three-candle pivot, confirmed after its right candle closes.
        # User mapping: downward arrow bullish; upward arrow bearish.
        fractal_side = "PUT" if v.get("fractal_up_arrow") else (
            "CALL" if v.get("fractal_down_arrow") else "WAIT")
        award("Fractal", fractal_side, 20 if fractal_side != "WAIT" else 0,
              "Setting 2 | upward arrow = bearish/SELL; downward arrow = bullish/BUY")

        # ADX directional lines: crossover side + spread size + widening strength.
        plus_di, minus_di = v.get("plus_di"), v.get("minus_di")
        di_spread = (plus_di - minus_di) if plus_di is not None and minus_di is not None else None
        prev_spread = v.get("di_spread_prev")
        di_side, di_points = "WAIT", 0.0
        if di_spread is not None and abs(di_spread) > 0.05:
            di_side = "CALL" if di_spread > 0 else "PUT"
            separation = self._clamp(abs(di_spread) / 25.0)
            widening = (di_spread * (di_spread - prev_spread) > 0) if prev_spread is not None else False
            adx_strength = self._clamp((v.get("adx") or 0) / 35.0)
            # A clear, widening DI X receives the full directional confirmation.
            di_quality = 0.55 * separation + 0.25 * float(widening) + 0.20 * adx_strength
            di_points = 30.0 * self._clamp(di_quality)
        award("ADX +DI / -DI", di_side, di_points,
              f"+DI {plus_di!s} | -DI {minus_di!s} | ADX {v.get('adx')!s} | spread {di_spread!s}")

        # Aroon mirrors the DI logic: direction, line separation, and widening.
        au, ad = v.get("aroon_up"), v.get("aroon_down")
        aroon_spread = (au - ad) if au is not None and ad is not None else None
        prev_aroon_spread = v.get("aroon_spread_prev")
        aroon_side, aroon_points = "WAIT", 0.0
        if aroon_spread is not None and abs(aroon_spread) > 0.5:
            aroon_side = "CALL" if aroon_spread > 0 else "PUT"
            separation = self._clamp(abs(aroon_spread) / 60.0)
            widening = (aroon_spread * (aroon_spread - prev_aroon_spread) > 0) if prev_aroon_spread is not None else False
            aroon_points = 20.0 * self._clamp(0.70 * separation + 0.30 * float(widening))
        award("Aroon Up / Down", aroon_side, aroon_points,
              f"Aroon Up {au!s} | Aroon Down {ad!s} | spread {aroon_spread!s}")

        # OsMA: sign establishes momentum direction; strengthening histogram earns full points.
        hist, prev_hist = v.get("osma_hist"), v.get("osma_hist_prev")
        osma_side, osma_points = "WAIT", 0.0
        if hist is not None and abs(hist) > 1e-12:
            osma_side = "CALL" if hist > 0 else "PUT"
            strengthening = (hist > prev_hist) if hist > 0 and prev_hist is not None else (
                hist < prev_hist if hist < 0 and prev_hist is not None else False)
            osma_points = 15.0 if strengthening else 11.0
        award("OsMA", osma_side, osma_points,
              f"Histogram {hist!s} | previous {prev_hist!s}")

        # Alligator: ordered lines plus widening mouth confirm trend quality.
        jaw, teeth, lips = v.get("jaw"), v.get("teeth"), v.get("lips")
        alligator_side, alligator_points = "WAIT", 0.0
        if None not in (jaw, teeth, lips):
            if lips > teeth > jaw:
                alligator_side = "CALL"
            elif lips < teeth < jaw:
                alligator_side = "PUT"
            if alligator_side != "WAIT":
                mouth = abs(lips - jaw)
                prev_mouth = v.get("alligator_mouth_prev")
                expanding = prev_mouth is not None and mouth > prev_mouth
                alligator_points = 15.0 if expanding else 11.0
        award("Williams Alligator", alligator_side, alligator_points,
              f"Jaw {jaw!s} | Teeth {teeth!s} | Lips {lips!s}")

        score = max(call, put)
        side = "CALL" if call > put else "PUT" if put > call else "WAIT"
        margin = abs(call - put)
        signal = side if score >= 20 and margin >= 5 else "WAIT"
        confidence = min(100, round(score))
        win_probability = (max(50, min(85, round(50 + max(0, score - 20) * 0.4375)))
                           if signal != "WAIT" else 50)

        aligned = sum(1 for vote in votes if vote["direction"] == side) if side != "WAIT" else 0
        return {
            "signal": signal, "score": confidence, "confidence": confidence,
            "win_probability": win_probability,
            "probability_label": "UNCALIBRATED MODEL ESTIMATE",
            "call_score": round(call, 1), "put_score": round(put, 1),
            "aligned_indicators": aligned,
            "reason": (f"{aligned}/5 indicators aligned {side}; weighted confluence"
                       if signal != "WAIT" else "No decisive directional edge yet"),
            "votes": votes, "automatic_execution": False, "mode": "SIGNAL_ONLY",
            "settings": {k: v[k] for k in ("fractal_period", "aroon_period", "osma_fast",
                         "osma_slow", "osma_signal_period") if k in v},
        }
