import asyncio,logging,time
from fastapi import FastAPI,Request
from fastapi.responses import HTMLResponse
from config import APP_NAME,TIMEFRAMES,ASSETS,WS_URL,AUTH_JSON,DEFAULT_ASSET,DEFAULT_TIMEFRAME
from candles import CandleBuilder
from pocket_feed import PocketOptionFeed
from indicators import calculate
from engine import DMCSignalEngine
logging.basicConfig(level=logging.INFO)
app=FastAPI(title=APP_NAME)
state={"asset":DEFAULT_ASSET,"timeframe":DEFAULT_TIMEFRAME,"price":None,"last_tick":0,"signal":{"signal":"WAIT","confidence":0,"reason":"Waiting for feed"},"indicators":{}}
builder=CandleBuilder(TIMEFRAMES.get(DEFAULT_TIMEFRAME,10),300)
engine=DMCSignalEngine(); feed=None; feed_task=None
broker_assets={}
def flatten_catalog(obj):
    found=set()
    def walk(x):
        if isinstance(x,dict):
            # Common broker payload shapes: {name, symbol, ticker, asset}
            for k,v in x.items():
                if str(k).lower() in ("name","symbol","ticker","asset","active_name") and isinstance(v,str):
                    s=v.strip().lstrip("#")
                    if 2<=len(s)<=32 and any(ch.isalpha() for ch in s) and not " " in s: found.add(s)
                walk(v)
        elif isinstance(x,list):
            for v in x: walk(v)
    walk(obj); return sorted(found)
def on_assets(payload):
    global broker_assets
    names=flatten_catalog(payload)
    if names: broker_assets={x:True for x in names}
def on_history(items):
    if builder.load_candles(items): refresh()
def on_tick(asset,price,ts):
    if str(asset).lower()!=state["asset"].lower(): return
    state["price"]=price; state["last_tick"]=time.time(); builder.update(price,ts); refresh()
def refresh():
    r=calculate(builder.snapshot(),TIMEFRAMES[state["timeframe"]])
    if r.get("ready"):
        state["indicators"]=r["values"]; state["signal"]=engine.evaluate(r)
@app.on_event("startup")
async def startup():
    global feed,feed_task
    feed=PocketOptionFeed(WS_URL,AUTH_JSON,on_tick,on_history,asset=state["asset"],period=TIMEFRAMES[state["timeframe"]],on_assets=on_assets)
    feed_task=asyncio.create_task(feed.run())
@app.on_event("shutdown")
async def shutdown():
    if feed: await feed.stop()
    if feed_task: feed_task.cancel()
@app.get("/api/health")
async def health():
    age=time.time()-state["last_tick"] if state["last_tick"] else None
    return {"service":APP_NAME,"feed_connected":bool(feed and feed.connected),"authenticated":bool(feed and feed.authenticated),"last_tick_age":age,"auth_configured":bool(AUTH_JSON),"automatic_execution":False,"mode":"SIGNAL_ONLY"}
@app.get("/api/state")
async def api_state():
    return {**state,"candles":builder.snapshot()[-120:],"automatic_execution":False,"mode":"SIGNAL_ONLY","feed_connected":bool(feed and feed.connected)}
@app.get("/api/assets")
async def api_assets():
    # Broker-published symbols take precedence; seed list fills categories until broker catalog arrives.
    if broker_assets:
        return {"source":"Pocket Option updateAssets event","complete_from_broker":True,"assets":sorted(broker_assets),"categories":{"Broker catalog":sorted(broker_assets)},"count":len(broker_assets)}
    return {"source":"seed catalog; broker catalog pending","complete_from_broker":False,"assets":ASSETS,"categories":ASSETS,"count":sum(map(len,ASSETS.values()))}
@app.get("/api/timeframes")
async def api_timeframes(): return {"timeframes":TIMEFRAMES}
@app.post("/api/config")
async def config(request:Request):
    body=await request.json(); asset=body.get("asset",state["asset"]); tf=body.get("timeframe",state["timeframe"])
    known=set(x for group in ASSETS.values() for x in group)|set(broker_assets)
    if asset not in known: return {"ok":False,"error":"Unknown asset; refresh broker catalog first"}
    if tf not in TIMEFRAMES:return {"ok":False,"error":"Unsupported timeframe"}
    state.update(asset=asset,timeframe=tf,price=None,last_tick=0,signal={"signal":"WAIT","confidence":0,"reason":"Loading selected market"},indicators={})
    global builder
    builder=CandleBuilder(TIMEFRAMES[tf],300)
    if feed: await feed.change_subscription(asset,TIMEFRAMES[tf])
    return {"ok":True,"asset":asset,"timeframe":tf,"automatic_execution":False}
@app.get("/",response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse("""<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'><title>DEVIL MAY CRY</title><style>
    *{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 80% 10%,#4b1115,#090a10 55%);color:#f5f5f5;font:15px Arial,sans-serif}header{padding:22px;background:linear-gradient(90deg,#100d12,#451015);border-bottom:2px solid #b52a32}h1{margin:0;font-size:28px;letter-spacing:3px;color:#f2e8e8}small{color:#e0a5a5;letter-spacing:2px}.wrap{max-width:1000px;margin:auto;padding:16px}.panel{background:#14151d;border:1px solid #4d3037;border-radius:12px;padding:16px;margin:12px 0;box-shadow:0 8px 25px #0008}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}select,button{width:100%;padding:13px;border-radius:8px;background:#222530;color:white;border:1px solid #69434a}button{background:#9e1d28;font-weight:bold;margin-top:10px}.signal{font-size:34px;font-weight:900;text-align:center;padding:20px}.up{color:#4fe08b}.down{color:#ff5964}.wait{color:#ffd36a}.muted{color:#a6a8b2;font-size:12px}@media(max-width:600px){.grid{grid-template-columns:1fr}h1{font-size:21px}}</style></head><body><header><h1>DEVIL MAY CRY</h1><small>DANTE EDITION • INDEPENDENT AI SIGNAL LAB • SIGNAL ONLY</small></header><div class='wrap'><div class='panel'><b>MARKET SELECTOR</b><div class='grid'><select id='market'></select><select id='tf'></select></div><button onclick='apply()'>APPLY MARKET & TIMEFRAME</button><p class='muted' id='catalog'>Loading asset catalog…</p></div><div class='panel'><div class='muted'>LIVE SIGNAL • AUTO-EXECUTION OFF</div><div id='sig' class='signal wait'>WAIT</div><div id='confidence' style='text-align:center'>0 / 100</div><p id='reason' class='muted'></p></div><div class='panel'><b>INDICATOR CONFLUENCE</b><div id='indicators' class='grid'></div></div><div class='panel'><b>FEED STATUS</b><p id='status' class='muted'>Connecting…</p></div></div><script>
    let catalog={};async function load(){let a=await fetch('/api/assets').then(r=>r.json());catalog=a;let sel=document.getElementById('market');sel.innerHTML='';for(let [group,items] of Object.entries(a.categories)){let o=document.createElement('optgroup');o.label=group;for(let name of items){let op=document.createElement('option');op.value=name;op.textContent=name;o.append(op)}sel.append(o)}document.getElementById('catalog').textContent=a.count+' symbols • '+a.source;let t=await fetch('/api/timeframes').then(r=>r.json());let tf=document.getElementById('tf');tf.innerHTML=Object.keys(t.timeframes).map(x=>'<option>'+x+'</option>').join('');sel.value='EURUSD_otc';tf.value='10s';}
    async function apply(){let r=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({asset:document.getElementById('market').value,timeframe:document.getElementById('tf').value})}).then(r=>r.json());if(!r.ok)alert(r.error||'Could not apply selection')}
    async function poll(){let [s,h]=await Promise.all([fetch('/api/state').then(r=>r.json()),fetch('/api/health').then(r=>r.json())]);let sig=s.signal||{};let el=document.getElementById('sig');el.textContent=sig.signal||'WAIT';el.className='signal '+(sig.signal==='CALL'?'up':sig.signal==='PUT'?'down':'wait');document.getElementById('confidence').textContent=(sig.confidence||0)+' / 100 • '+(s.asset||'')+' • '+(s.timeframe||'');document.getElementById('reason').textContent=sig.reason||'';let v=s.indicators||{};document.getElementById('indicators').innerHTML=['jaw','teeth','lips','aroon_up','aroon_down','osma_hist','aroon_period','osma_fast','osma_slow','osma_signal_period'].map(k=>'<div><span class=muted>'+k.replaceAll('_',' ').toUpperCase()+'</span><br><b>'+(v[k]??'—')+'</b></div>').join('');document.getElementById('status').textContent='Connected: '+h.feed_connected+' • Authenticated: '+h.authenticated+' • Price: '+(s.price??'—')+' • Automatic execution: OFF';}
    load().then(()=>{poll();setInterval(poll,1500)});</script></body></html>""")
