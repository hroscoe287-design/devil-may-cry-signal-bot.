class DMCSignalEngine:
    """Independent 100-point Alligator + Aroon + OSMA confluence model."""
    def evaluate(self,result):
        if not result.get("ready"):return {"signal":"WAIT","score":0,"confidence":0,"reason":result.get("reason","Waiting for data"),"votes":[]}
        v=result["values"]; call=put=0; votes=[]
        def vote(name,side,weight):
            nonlocal call,put
            if side=="CALL":call+=weight
            elif side=="PUT":put+=weight
            votes.append({"indicator":name,"direction":side,"weight":weight})
        jaw,teeth,lips=v["jaw"],v["teeth"],v["lips"]
        alligator="CALL" if lips>teeth>jaw else "PUT" if lips<teeth<jaw else "WAIT"
        vote("Williams Alligator",alligator,35)
        au,ad=v["aroon_up"],v["aroon_down"]
        aroon="CALL" if au is not None and ad is not None and au>ad else "PUT" if au is not None and ad is not None and ad>au else "WAIT"
        # Aroon strength is proportional to separation, not a binary crossover alone.
        aroon_weight=25 if au is not None and ad is not None and abs(au-ad)>=20 else 15
        vote("Aroon",aroon,aroon_weight)
        hist=v["osma_hist"]; prev=v["osma_hist_prev"]
        osma="CALL" if hist is not None and hist>0 and (prev is None or hist>=prev) else "PUT" if hist is not None and hist<0 and (prev is None or hist<=prev) else "WAIT"
        vote("OSMA",osma,25)
        # Expansion/slope is a confirmation boost; never fabricates a direction.
        spread=abs(lips-jaw); prior=abs(v["lips_prev"]-v["jaw_prev"]) if v["lips_prev"] is not None and v["jaw_prev"] is not None else spread
        expansion=spread>prior
        if expansion and alligator=="CALL":call+=10
        elif expansion and alligator=="PUT":put+=10
        # Momentum alignment adds a small bonus, capped at 100.
        if alligator==aroon==osma and alligator in ("CALL","PUT"):
            if alligator=="CALL":call+=5
            else:put+=5
        score=max(call,put); side="CALL" if call>put else "PUT" if put>call else "WAIT"
        # Permissive directional threshold, but WAIT remains when evidence is tied or missing.
        confidence=min(100,round(score))
        signal=side if score>=35 and abs(call-put)>=10 else "WAIT"
        return {"signal":signal,"score":confidence,"confidence":confidence,"call_score":round(call,1),"put_score":round(put,1),
                "reason":"Weighted Alligator/Aroon/OSMA confluence" if signal!="WAIT" else "No decisive directional edge yet",
                "votes":votes,"alligator_expanding":expansion,"settings":{k:v[k] for k in ("aroon_period","osma_fast","osma_slow","osma_signal_period")}}
