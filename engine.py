class DMCSignalEngine:
    """Independent 100-point weighted confluence engine; signal-only."""

    WEIGHTS = {
        "ADX DI direction / strength": 8,
        "DI separation": 7,
        "DI velocity": 6,
        "DI acceleration": 4,
        "Fractal": 20,
        "Aroon Up / Down": 20,
        "OsMA": 25,
        "Williams Alligator": 10,
    }

    @staticmethod
    def _clamp(value, low=0.0, high=1.0):
        return max(low, min(high, float(value)))

    @staticmethod
    def _duration_guidance(values, votes, di_side, spread, velocity, acceleration):
        """Recommend a signal horizon from current DI momentum; never execute a trade."""
        tf = max(1, int(values.get("selected_timeframe_seconds") or 10))
        gap = abs(spread or 0.0)
        small_x, wide_x = gap < 8.0, gap >= 15.0
        velocity_side = "CALL" if (velocity or 0) > 0 else "PUT" if (velocity or 0) < 0 else "WAIT"
        acceleration_side = "CALL" if (acceleration or 0) > 0 else "PUT" if (acceleration or 0) < 0 else "WAIT"
        aligned = sum(1 for item in votes if item["direction"] == di_side) if di_side != "WAIT" else 0
        opposing = sum(1 for item in votes if item["direction"] not in (di_side, "WAIT")) if di_side != "WAIT" else 0
        reversing = di_side == "WAIT" or velocity_side not in ("WAIT", di_side) or (acceleration_side not in ("WAIT", di_side) and opposing >= 2)
        if reversing:
            state, risk, fraction = "MOMENTUM_REVERSING", "HIGH", None
        elif small_x:
            state = "SMALL_X_DEVELOPING" if velocity_side == di_side else "SMALL_X_UNCONFIRMED"
            risk = "LOW" if velocity_side == di_side and aligned >= 3 else "MODERATE"
            fraction = 0.45 if velocity_side == di_side and aligned >= 2 else 0.35
        elif wide_x and velocity_side == di_side and acceleration_side in ("WAIT", di_side):
            state, risk, fraction = "WIDE_X_EXPANDING", "LOW", 0.90
        elif wide_x:
            state, risk, fraction = "WIDE_X_FADING", "MODERATE", 0.55
        else:
            state, risk = "DI_CROSSOVER_BUILDING", "MODERATE"
            fraction = 0.65 if velocity_side == di_side else 0.40
        seconds = max(2, min(tf, int(round(tf * fraction)))) if fraction is not None else None
        warning = ("DI momentum is reversing; current direction is unstable." if risk == "HIGH" else
                   "Small DI separation: use a shorter horizon and watch for reversal." if small_x else
                   "DI spread is weakening; shorten the expected signal horizon." if state == "WIDE_X_FADING" else
                   "DI spread and momentum are expanding; longer horizon is only a model estimate." if state == "WIDE_X_EXPANDING" else
                   "Watch the next DI updates for confirmation.")
        return {"momentum_state": state, "fakeout_risk": risk, "fakeout_warning": warning,
                "recommended_duration_seconds": seconds,
                "duration_basis": "chart timeframe multiplied by momentum-adjusted fraction; recommendation only",
                "di_spread": round(spread, 3) if spread is not None else None,
                "di_velocity": round(velocity, 3) if velocity is not None else None,
                "di_acceleration": round(acceleration, 3) if acceleration is not None else None,
                "small_x": small_x, "wide_x": wide_x}

    def evaluate(self, result):
        if not result.get("ready"):
            return {"signal": "WAIT", "score": 0, "confidence": 0,
                    "win_probability": 50, "reason": result.get("reason", "Waiting for data"),
                    "votes": [], "automatic_execution": False, "mode": "SIGNAL_ONLY"}

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

        # ADX/DI is scored as four independent components. No directional
        # margin or indicator-agreement gate blocks the accumulated score.
        plus_di, minus_di = v.get("plus_di"), v.get("minus_di")
        spread = plus_di - minus_di if plus_di is not None and minus_di is not None else None
        di_side = ("CALL" if spread is not None and spread > 0 else
                   "PUT" if spread is not None and spread < 0 else "WAIT")
        adx = v.get("adx") or 0.0
        award("ADX DI direction / strength", di_side,
              8 * self._clamp(adx / 25.0) if di_side != "WAIT" else 0,
              f"+DI {plus_di} | -DI {minus_di} | ADX {adx}")
        award("DI separation", di_side,
              7 * self._clamp(abs(spread or 0.0) / 25.0) if di_side != "WAIT" else 0,
              f"DI spread {spread}; wider separation earns more")
        velocity, acceleration = v.get("di_velocity"), v.get("di_acceleration")
        velocity_side = ("CALL" if velocity is not None and velocity > 0 else
                         "PUT" if velocity is not None and velocity < 0 else "WAIT")
        acceleration_side = ("CALL" if acceleration is not None and acceleration > 0 else
                             "PUT" if acceleration is not None and acceleration < 0 else "WAIT")
        award("DI velocity", velocity_side,
              6 * self._clamp(abs(velocity or 0.0) / 2.5) if velocity_side != "WAIT" else 0,
              f"DI spread change per candle {velocity}")
        award("DI acceleration", acceleration_side,
              4 * self._clamp(abs(acceleration or 0.0) / 1.5) if acceleration_side != "WAIT" else 0,
              f"Change in DI velocity {acceleration}")

        # User-defined fractal mapping: upper arrow bearish, lower arrow bullish.
        fractal_side = "PUT" if v.get("fractal_up_arrow") else (
                       "CALL" if v.get("fractal_down_arrow") else "WAIT")
        award("Fractal", fractal_side, 20 if fractal_side != "WAIT" else 0,
              "Setting 3; confirmed pivot; up arrow=PUT/bearish, down arrow=CALL/bullish")

        # Aroon receives points for direction/separation and independently
        # for an expanding spread; no crossover gate is applied.
        au, ad = v.get("aroon_up"), v.get("aroon_down")
        aroon_spread = au - ad if au is not None and ad is not None else None
        previous_spread = v.get("aroon_spread_prev")
        aroon_side = ("CALL" if aroon_spread is not None and aroon_spread > 0 else
                      "PUT" if aroon_spread is not None and aroon_spread < 0 else "WAIT")
        widening = (aroon_spread is not None and previous_spread is not None and
                    abs(aroon_spread) > abs(previous_spread))
        aroon_points = (15 * self._clamp(abs(aroon_spread) / 60.0) +
                        (5 if widening else 0)) if aroon_side != "WAIT" else 0
        award("Aroon Up / Down", aroon_side, aroon_points,
              f"Up {au} | Down {ad} | spread {aroon_spread} | period {v.get('aroon_period')} | widening {widening}")

        # OsMA sign contributes 15; strengthening momentum contributes 10.
        hist, previous_hist = v.get("osma_hist"), v.get("osma_hist_prev")
        osma_side = ("CALL" if hist is not None and hist > 0 else
                     "PUT" if hist is not None and hist < 0 else "WAIT")
        strengthening = (hist is not None and previous_hist is not None and
                         ((hist > 0 and hist > previous_hist) or
                          (hist < 0 and hist < previous_hist)))
        osma_points = (15 + (10 if strengthening else 0)) if osma_side != "WAIT" else 0
        award("OsMA", osma_side, osma_points,
              f"Histogram {hist} | previous {previous_hist} | adaptive settings {v.get('osma_fast')}/{v.get('osma_slow')}/{v.get('osma_signal_period')}")

        # Alligator contributes trend order plus mouth expansion.
        jaw, teeth, lips = v.get("jaw"), v.get("teeth"), v.get("lips")
        alligator_side = "WAIT"
        if None not in (jaw, teeth, lips):
            if lips > teeth > jaw:
                alligator_side = "CALL"
            elif lips < teeth < jaw:
                alligator_side = "PUT"
        mouth = abs(lips - jaw) if alligator_side != "WAIT" else 0
        previous_mouth = v.get("alligator_mouth_prev")
        expanding = previous_mouth is not None and mouth > previous_mouth
        alligator_points = (6 + (4 if expanding else 0)) if alligator_side != "WAIT" else 0
        award("Williams Alligator", alligator_side, alligator_points,
              f"Jaw {jaw} | Teeth {teeth} | Lips {lips} | expanding {expanding}")

        score = max(call, put)
        side = "CALL" if call > put else "PUT" if put > call else "WAIT"
        signal = side if score >= 55 else "WAIT"
        confidence = min(100, round(score))
        win_probability = (max(50, min(85, round(50 + max(0, score - 55) * 0.6)))
                           if signal != "WAIT" else 50)
        aligned = sum(1 for vote in votes if vote["direction"] == side) if side != "WAIT" else 0
        duration = self._duration_guidance(v, votes, di_side, spread, velocity, acceleration)
        return {
            "signal": signal, "score": confidence, "confidence": confidence,
            "win_probability": win_probability,
            "probability_label": "UNCALIBRATED MODEL ESTIMATE",
            "call_score": round(call, 1), "put_score": round(put, 1),
            "score_threshold": 55, "directional_margin": round(abs(call - put), 1),
            "aligned_components": aligned,
            "reason": (f"{aligned}/8 scored components favor {side}; independent weighted scoring"
                       if signal != "WAIT" else
                       f"WAIT: leading side has {round(score, 1)}/55 points; indicators still accumulate independently"),
            "votes": votes, **duration, "automatic_execution": False, "mode": "SIGNAL_ONLY",
            "settings": {k: v[k] for k in ("fractal_period", "aroon_period", "osma_fast",
                         "osma_slow", "osma_signal_period") if k in v},
        }
