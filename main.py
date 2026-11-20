import asyncio
import logging
import time
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from config import APP_NAME, TIMEFRAMES, ASSETS, WS_URL, AUTH_JSON, DEFAULT_ASSET, DEFAULT_TIMEFRAME
from candles import CandleBuilder
from pocket_feed import PocketOptionFeed
from indicators import calculate
from engine import DMCSignalEngine

logging.basicConfig(level=logging.INFO)
app = FastAPI(title=APP_NAME)
state = {
    "asset": DEFAULT_ASSET,
    "timeframe": DEFAULT_TIMEFRAME,
    "price": None,
    "last_tick": 0,
    "signal": {"signal": "WAIT", "confidence": 0, "reason": "Waiting for live feed"},
    "indicators": {},
}
builder = CandleBuilder(TIMEFRAMES.get(DEFAULT_TIMEFRAME, 10), 300)
engine = DMCSignalEngine()
feed = None
feed_task = None
broker_assets = {}

def flatten_catalog(obj):
    found = set()
    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if str(k).lower() in ("name", "symbol", "ticker", "asset", "active_name") and isinstance(v, str):
                    s = v.strip().lstrip("#")
                    if 2 <= len(s) <= 32 and any(ch.isalpha() for ch in s) and " " not in s:
                        found.add(s)
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(obj)
    return sorted(found)

def on_assets(payload):
    global broker_assets
    names = flatten_catalog(payload)
    if names:
        broker_assets = {x: True for x in names}

def on_history(items):
    if builder.load_candles(items):
        refresh()

def on_tick(asset, price, ts):
    if str(asset).lower() != state["asset"].lower():
        return
    state["price"] = price
    state["last_tick"] = time.time()
    builder.update(price, ts)
    refresh()

def refresh():
    result = calculate(builder.snapshot(), TIMEFRAMES[state["timeframe"]])
    if result.get("ready"):
        state["indicators"] = result["values"]
        state["signal"] = engine.evaluate(result)
    else:
        state["signal"] = {"signal": "WAIT", "score": 0, "confidence": 0,
                           "reason": result.get("reason", "Waiting for candle history"), "votes": []}

@app.on_event("startup")
async def startup():
    global feed, feed_task
    feed = PocketOptionFeed(WS_URL, AUTH_JSON, on_tick, on_history,
                            asset=state["asset"], period=TIMEFRAMES[state["timeframe"]],
                            on_assets=on_assets)
    feed_task = asyncio.create_task(feed.run())

@app.on_event("shutdown")
async def shutdown():
    if feed:
        await feed.stop()
    if feed_task:
        feed_task.cancel()

@app.get("/api/health")
async def health():
    age = time.time() - state["last_tick"] if state["last_tick"] else None
    return {
        "service": APP_NAME, "feed_connected": bool(feed and feed.connected),
        "authenticated": bool(feed and feed.authenticated), "last_tick_age": age,
        "auth_configured": bool(AUTH_JSON), "last_feed_error": feed.last_error if feed else "",
        "automatic_execution": False, "mode": "SIGNAL_ONLY",
    }

@app.get("/api/state")
async def api_state():
    return {
        **state, "candles": builder.snapshot()[-120:],
        "automatic_execution": False, "mode": "SIGNAL_ONLY",
        "feed_connected": bool(feed and feed.connected),
    }

@app.post("/api/generate")
async def generate():
    # Generate always evaluates the latest available market data; it never invents candles.
    refresh()
    return {
        **state["signal"], "asset": state["asset"], "timeframe": state["timeframe"],
        "price": state["price"], "candle_count": len(builder.snapshot()),
        "live_tick_age": time.time() - state["last_tick"] if state["last_tick"] else None,
        "feed_connected": bool(feed and feed.connected),
        "authenticated": bool(feed and feed.authenticated),
        "automatic_execution": False, "mode": "SIGNAL_ONLY",
    }

@app.get("/api/assets")
async def api_assets():
    if broker_assets:
        names = sorted(broker_assets)
        return {"source": "Pocket Option updateAssets event", "complete_from_broker": True,
                "assets": names, "categories": {"Broker catalog": names}, "count": len(names)}
    return {"source": "seed catalog; broker catalog pending", "complete_from_broker": False,
            "assets": ASSETS, "categories": ASSETS, "count": sum(map(len, ASSETS.values()))}

@app.get("/api/timeframes")
async def api_timeframes():
    return {"timeframes": TIMEFRAMES}

@app.post("/api/config")
async def config(request: Request):
    body = await request.json()
    asset = body.get("asset", state["asset"])
    tf = body.get("timeframe", state["timeframe"])
    known = set(x for group in ASSETS.values() for x in group) | set(broker_assets)
    if asset not in known:
        return {"ok": False, "error": "Unknown asset. Refresh the broker catalog first."}
    if tf not in TIMEFRAMES:
        return {"ok": False, "error": "Unsupported timeframe."}
    state.update(asset=asset, timeframe=tf, price=None, last_tick=0,
                 signal={"signal": "WAIT", "confidence": 0, "reason": "Loading selected market"},
                 indicators={})
    global builder
    builder = CandleBuilder(TIMEFRAMES[tf], 300)
    if feed:
        await feed.change_subscription(asset, TIMEFRAMES[tf])
    return {"ok": True, "asset": asset, "timeframe": tf, "automatic_execution": False}

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse("""<!doctype html>
<html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DEVIL MAY CRY — SIGNAL LAB</title>
<style>
*{box-sizing:border-box}body{margin:0;background:linear-gradient(180deg,rgba(5,6,11,.68),rgba(5,6,11,.91)),url('https://i.playground.ru/p/bagp1B2UZx51YcXXs55Arg.jpeg') center 18%/cover fixed no-repeat,#090a10;color:#f5f5f5;font:15px Arial,sans-serif}
header{padding:22px;background:linear-gradient(90deg,#100d12,#451015);border-bottom:2px solid #b52a32}
h1{margin:0;font-size:28px;letter-spacing:3px}small{color:#e0a5a5;letter-spacing:2px}
.wrap{max-width:1000px;margin:auto;padding:16px}.panel{background:#14151d;border:1px solid #56323a;border-radius:12px;padding:16px;margin:12px 0;box-shadow:0 8px 25px #0008}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
select,button{width:100%;padding:13px;border-radius:8px;background:#222530;color:white;border:1px solid #69434a}
button{background:#a51f2a;font-weight:bold;margin-top:10px;cursor:pointer}.generate{background:linear-gradient(90deg,#b31f2a,#68121b);font-size:18px;padding:16px}
.signal{font-size:38px;font-weight:900;text-align:center;padding:20px}.up{color:#4fe08b}.down{color:#ff5964}.wait{color:#ffd36a}\n.metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:12px 0}.metric{background:#20212b;border:1px solid #56323a;border-radius:10px;padding:14px;text-align:center}.metric strong{display:block;font-size:30px;margin-top:6px}.metric .muted{letter-spacing:1px}.probfill{height:9px;background:#30313a;border-radius:10px;overflow:hidden;margin-top:10px}.probfill>div{height:100%;width:50%;background:linear-gradient(90deg,#a51f2a,#4fe08b)}
.muted{color:#a6a8b2;font-size:12px}.status{display:flex;gap:8px;flex-wrap:wrap}.chip{background:#242631;border:1px solid #41434e;border-radius:20px;padding:7px 10px;font-size:12px}
.meter{height:9px;background:#30313a;border-radius:10px;overflow:hidden;margin:12px 0}.fill{height:100%;width:0;background:#b52a32}
@media(max-width:600px){.grid{grid-template-columns:1fr}h1{font-size:21px}}
</style></head><body>
<header><h1>DEVIL MAY CRY</h1><small>DANTE EDITION • INDEPENDENT AI SIGNAL LAB • ANALYZE BEFORE YOU ACT</small></header>
<div class="wrap">
<div class="panel"><b>MARKET SELECTOR</b><input id="assetSearch" type="search" placeholder="Search all Pocket Option assets…" oninput="filterAssets()" style="width:100%;margin:10px 0;padding:13px;border-radius:8px;background:#222530;color:white;border:1px solid #69434a"><div class="grid" style="margin-top:10px"><select id="market"></select><select id="tf"></select></div>
<button onclick="apply()">APPLY MARKET & TIMEFRAME</button><p class="muted" id="catalog">Loading Pocket Option catalog…</p></div>
<div class="panel"><div class="status"><span class="chip">SIGNAL-ONLY MODE</span><span class="chip">AUTO-TRADING OFF</span></div>
<div id="sig" class="signal wait">WAIT</div><div class="metrics"><div class="metric"><span class="muted">SIGNAL SCORE</span><strong id="confidence">0 / 100</strong></div><div class="metric"><span class="muted">WIN PROBABILITY</span><strong id="winProbability">—%</strong><div class="probfill"><div id="probMeter"></div></div><span class="muted" id="probLabel">Awaiting analysis</span></div></div><div class="meter"><div id="meter" class="fill"></div></div>
<p id="reason" class="muted">Waiting for live market data.</p><button class="generate" id="generate" onclick="generate()">⚔ GENERATE SIGNAL</button>
<p class="muted" id="result"></p></div>
<div class="panel"><b>INDICATOR CONFLUENCE</b><div id="indicators" class="grid" style="margin-top:12px"></div><div id="scoreBreakdown" style="margin-top:14px"></div></div>
<div class="panel"><b>LIVE FEED STATUS</b><p id="status" class="muted">Connecting…</p></div>
</div>
<script>
let catalog={}, allAssetGroups={};
function filterAssets(){const q=document.getElementById("assetSearch").value.trim().toLowerCase();const sel=document.getElementById("market");const chosen=sel.value;sel.innerHTML="";for(const [group,items] of Object.entries(allAssetGroups)){const matches=items.filter(name=>name.toLowerCase().includes(q));if(!matches.length)continue;const o=document.createElement("optgroup");o.label=group;for(const name of matches){const op=document.createElement("option");op.value=name;op.textContent=name;o.append(op)}sel.append(o)}if([...sel.options].some(o=>o.value===chosen))sel.value=chosen;}
async function load(){
 const a=await fetch('/api/assets').then(r=>r.json());catalog=a;
 allAssetGroups=a.categories||{};filterAssets();const sel=document.getElementById("market");
 document.getElementById('catalog').textContent=a.count+' symbols • '+a.source+(a.complete_from_broker?' • broker catalog received':' • broker catalog pending');
 const t=await fetch('/api/timeframes').then(r=>r.json());const tf=document.getElementById('tf');
 tf.innerHTML=Object.keys(t.timeframes).map(x=>'<option value="'+x+'">'+x+'</option>').join('');
 sel.value='EURUSD_otc';tf.value='10s';
}
async function apply(){
 const r=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({asset:document.getElementById('market').value,timeframe:document.getElementById('tf').value})}).then(r=>r.json());
 if(r.ok!==true){alert(r.error||'Could not apply selection');return}
 document.getElementById('result').textContent='Loading selected market history…';
}
async function generate(){
 const b=document.getElementById('generate');b.disabled=true;b.textContent='ANALYZING LIVE DATA…';
 try{const r=await fetch('/api/generate',{method:'POST'}).then(x=>x.json());
 renderSignal(r);document.getElementById("result").textContent=r.candle_count+" candles • "+(r.live_tick_age===null?"No live tick received":"last tick "+r.live_tick_age.toFixed(1)+"s ago")+" • "+(r.feed_connected?"feed connected":"feed not connected")+" • "+(r.authenticated?"authenticated":"not authenticated");
 }catch(e){document.getElementById('result').textContent='Could not generate: '+e.message}
 finally{b.disabled=false;b.textContent='⚔ GENERATE SIGNAL'}
}
function renderSignal(s){
 const raw=s.signal||"WAIT";const sig=raw==="CALL"?"UP":raw==="PUT"?"DOWN":raw;const el=document.getElementById("sig");el.textContent=sig;el.className="signal "+(sig==="UP"?"up":sig==="DOWN"?"down":"wait");
 const c=s.confidence||0;document.getElementById('confidence').textContent=c+' / 100 • '+(s.asset||'')+' • '+(s.timeframe||'');
 const p=Number.isFinite(Number(s.win_probability))?Number(s.win_probability):null;document.getElementById('winProbability').textContent=p===null?'—%':p+'%';document.getElementById('probMeter').style.width=(p===null?0:p)+'%';document.getElementById('probLabel').textContent=s.probability_label||'Model estimate — not historically calibrated';
 document.getElementById('meter').style.width=c+'%';document.getElementById('reason').textContent=s.reason||'';
}
async function poll(){
 const [s,h]=await Promise.all([fetch('/api/state').then(r=>r.json()),fetch('/api/health').then(r=>r.json())]);
 renderSignal({...s.signal,asset:s.asset,timeframe:s.timeframe});
 const votes=(s.signal&&s.signal.votes)||[];document.getElementById('scoreBreakdown').innerHTML='<b class="muted">LIVE SCORE BREAKDOWN • 100-POINT CONFLUENCE</b>'+votes.map(x=>'<div style="display:flex;justify-content:space-between;gap:10px;padding:7px 0;border-bottom:1px solid #343540"><span>'+x.indicator+' <small>'+x.direction+'</small></span><b>'+x.points+' / '+(x.max_points??0)+'</b></div>').join('');
 const v=s.indicators||{};document.getElementById('indicators').innerHTML=['jaw','teeth','lips','adx','plus_di','minus_di','di_spread','di_velocity','di_acceleration','ema9','ema21','macd_hist','rsi5','aroon_up','aroon_down','osma_hist','fractal_up_arrow','fractal_down_arrow','fractal_period','aroon_period','osma_fast','osma_slow','osma_signal_period'].map(k=>'<div><span class="muted">'+(k==='fractal_up_arrow'?'FRACTAL UP = BEARISH':k==='fractal_down_arrow'?'FRACTAL DOWN = BULLISH':k==='fractal_period'?'FRACTAL SETTING':k.replaceAll('_',' ').toUpperCase())+'</span><br><b>'+(v[k]??'—')+'</b></div>').join('');
 document.getElementById("status").textContent="Feed: "+(h.feed_connected?"CONNECTED":"DISCONNECTED")+" • Auth: "+(h.authenticated?"OK":"NOT VERIFIED")+" • Auth configured: "+h.auth_configured+" • Live price: "+(s.price??"—")+" • Auto-trading: OFF"+(h.last_feed_error?" • "+h.last_feed_error:"");
}
load().then(()=>{poll();setInterval(poll,1500)});
</script></body></html>""")
