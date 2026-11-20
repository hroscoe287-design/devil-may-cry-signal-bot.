class DMCSignalEngine:
    """Weighted 100-point DMC confluence engine. Signal-only; never places orders."""

    WEIGHTS = {
        "DI direction / ADX strength": 10,
        "DI separation": 10,
        "DI velocity": 8,
        "DI acceleration": 7,
        "Fractal": 15,
        "Aroon Up / Down": 15,
        "OsMA": 12,
        "Williams Alligator": 10,
        "EMA 9 / 21": 5,
        "MACD": 4,
        "RSI 5": 2,
        "Fakeout protection": 2,
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
            votes.append({"indicator": name, "direction": side or "WAIT",
                          "points": points, "max_points": self.WEIGHTS[name],
                          "detail": detail})

        # ADX DI is the primary engine. Velocity and acceleration remain active
        # after crossover; widening spread is not discarded as a late signal.
        plus_di, minus_di = v.get("plus_di"), v.get("minus_di")
        spread = (plus_di-minus_di) if plus_di is not None and minus_di is not None else None
        di_side = "CALL" if spread is not None and spread > 0.05 else (
                  "PUT" if spread is not None and spread < -0.05 else "WAIT")
        adx = v.get("adx") or 0.0
        award("DI direction / ADX strength", di_side,
              10.0*self._clamp(adx/25.0) if di_side != "WAIT" else 0,
              f"+DI {plus_di} | -DI {minus_di} | ADX {adx}")
        award("DI separation", di_side,
              10.0*self._clamp(abs(spread or 0.0)/25.0) if di_side != "WAIT" else 0,
              f"DI spread {spread}; full separation points at 25+")
        velocity, acceleration = v.get("di_velocity"), v.get("di_acceleration")
        # Score DI momentum independently: opposing momentum earns points on
        # its own side instead of being vetoed by the current DI crossover.
        velocity_side = "CALL" if velocity is not None and velocity > 0 else (
                        "PUT" if velocity is not None and velocity < 0 else "WAIT")
        acceleration_side = "CALL" if acceleration is not None and acceleration > 0 else (
                            "PUT" if acceleration is not None and acceleration < 0 else "WAIT")
        award("DI velocity", velocity_side,
              8.0*self._clamp(abs(velocity or 0.0)/2.5) if velocity_side != "WAIT" else 0,
              f"Spread change per candle {velocity}")
        award("DI acceleration", acceleration_side,
              7.0*self._clamp(abs(acceleration or 0.0)/1.5) if acceleration_side != "WAIT" else 0,
              f"Change in DI velocity {acceleration}")

        # Confirmed Bill Williams fractal: user's requested arrow mapping.
        fractal_side = "PUT" if v.get("fractal_up_arrow") else (
                       "CALL" if v.get("fractal_down_arrow") else "WAIT")
        award("Fractal", fractal_side, 15 if fractal_side != "WAIT" else 0,
              "Setting 3; 3 closed candles on each side; up arrow=SELL, down arrow=BUY")

        # Aroon direction, separation, and widening.
        au, ad = v.get("aroon_up"), v.get("aroon_down")
        aroon_spread = au-ad if au is not None and ad is not None else None
        prev_aroon = v.get("aroon_spread_prev")
        aroon_side = "CALL" if aroon_spread is not None and aroon_spread > 0.5 else (
                     "PUT" if aroon_spread is not None and aroon_spread < -0.5 else "WAIT")
        aroon_widening = (aroon_spread is not None and prev_aroon is not None and
                          aroon_spread*(aroon_spread-prev_aroon) > 0)
        aroon_points = (10*self._clamp(abs(aroon_spread)/60.0) +
                        5*float(aroon_widening)) if aroon_side != "WAIT" else 0
        award("Aroon Up / Down", aroon_side, aroon_points,
              f"Up {au} | Down {ad} | spread {aroon_spread} | period {v.get('aroon_period')}")

        # OsMA sign plus histogram strengthening.
        hist, prev_hist = v.get("osma_hist"), v.get("osma_hist_prev")
        osma_side = "CALL" if hist is not None and hist > 1e-12 else (
                    "PUT" if hist is not None and hist < -1e-12 else "WAIT")
        strengthening = (hist is not None and prev_hist is not None and
                         ((hist > 0 and hist > prev_hist) or (hist < 0 and hist < prev_hist)))
        osma_points = (8 + (4 if strengthening else 0)) if osma_side != "WAIT" else 0
        award("OsMA", osma_side, osma_points,
              f"Histogram {hist} | previous {prev_hist} | scaled settings {v.get('osma_fast')}/{v.get('osma_slow')}/{v.get('osma_signal_period')}")

        # Alligator line order plus expanding mouth.
        jaw, teeth, lips = v.get("jaw"), v.get("teeth"), v.get("lips")
        alligator_side = "WAIT"
        if None not in (jaw, teeth, lips):
            if lips > teeth > jaw: alligator_side = "CALL"
            elif lips < teeth < jaw: alligator_side = "PUT"
        mouth = abs(lips-jaw) if alligator_side != "WAIT" else 0
        prev_mouth = v.get("alligator_mouth_prev")
        expanding = prev_mouth is not None and mouth > prev_mouth
        alligator_points = (6 + (4 if expanding else 0)) if alligator_side != "WAIT" else 0
        award("Williams Alligator", alligator_side, alligator_points,
              f"Jaw {jaw} | Teeth {teeth} | Lips {lips} | expanding {expanding}")

        # EMA 9/21 and MACD provide separate, lower-weight momentum checks.
        ema9, ema21 = v.get("ema9"), v.get("ema21")
        ema_side = "CALL" if ema9 is not None and ema21 is not None and ema9 > ema21 else (
                   "PUT" if ema9 is not None and ema21 is not None and ema9 < ema21 else "WAIT")
        award("EMA 9 / 21", ema_side, 5 if ema_side != "WAIT" else 0,
              f"EMA 9 {ema9} | EMA 21 {ema21}")

        macd_hist = v.get("macd_hist")
        macd_side = "CALL" if macd_hist is not None and macd_hist > 0 else (
                    "PUT" if macd_hist is not None and macd_hist < 0 else "WAIT")
        award("MACD", macd_side, 4 if macd_side != "WAIT" else 0,
              f"MACD histogram {macd_hist} | standard 12/26/9")

        rsi_value = v.get("rsi5")
        rsi_side = "CALL" if rsi_value is not None and rsi_value > 50 else (
                   "PUT" if rsi_value is not None and rsi_value < 50 else "WAIT")
        award("RSI 5", rsi_side, 2 if rsi_side != "WAIT" else 0,
              f"RSI(5) {rsi_value}; midpoint 50")

        # The 2-point guard rewards a clean candle in the selected direction;
        # weak bodies or a large opposing wick receive zero protection points.
        candle_side = v.get("candle_direction", "WAIT")
        body = v.get("candle_body_ratio") or 0.0
        wick = v.get("opposing_wick_ratio")
        wick = 1.0 if wick is None else wick
        candidate = "CALL" if call > put else "PUT" if put > call else "WAIT"
        clean = body >= 0.50 and wick <= 0.25
        fakeout_points = 2 if candidate != "WAIT" and candle_side == candidate and clean else 0
        award("Fakeout protection", candidate, fakeout_points,
              f"Body ratio {body:.2f} | opposing wick {wick:.2f} | clean candle {clean}")

        score = max(call, put)
        side = "CALL" if call > put else "PUT" if put > call else "WAIT"
        margin = abs(call-put)
        # No directional-margin / indicator-agreement gate: all component
        # scores accumulate independently. The stronger side signals at 55+.
        signal = side if score >= 55 else "WAIT"
        confidence = min(100, round(score))
        win_probability = (max(50, min(85, round(50 + max(0, score-55)*0.6)))
                           if signal != "WAIT" else 50)
        aligned = sum(1 for vote in votes if vote["direction"] == side) if side != "WAIT" else 0
        return {
            "signal": signal, "score": confidence, "confidence": confidence,
            "win_probability": win_probability,
            "probability_label": "UNCALIBRATED MODEL ESTIMATE",
            "call_score": round(call, 1), "put_score": round(put, 1),
            "score_threshold": 55, "directional_margin": round(margin, 1),
            "aligned_components": aligned,
            "reason": (f"{aligned}/12 components currently favor {side}; independent weighted confluence"
                       if signal != "WAIT" else "WAIT: neither direction has reached the 55-point signal threshold"),
            "votes": votes, "automatic_execution": False, "mode": "SIGNAL_ONLY",
            "settings": {k: v[k] for k in ("fractal_period", "aroon_period", "osma_fast",
                         "osma_slow", "osma_signal_period") if k in v},
        }
