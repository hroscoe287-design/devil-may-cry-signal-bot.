import numpy as np
import pandas as pd

def ema(s,n): return s.ewm(span=n,adjust=False).mean()
def smma(s,n):
    out=pd.Series(np.nan,index=s.index,dtype=float)
    if len(s)<n:return out
    out.iloc[n-1]=s.iloc[:n].mean()
    for i in range(n,len(s)): out.iloc[i]=(out.iloc[i-1]*(n-1)+s.iloc[i])/n
    return out
def alligator(df):
    median=(df.high.astype(float)+df.low.astype(float))/2
    return smma(median,13),smma(median,8),smma(median,5)
def aroon(df,period):
    hi=df.high.astype(float); lo=df.low.astype(float)
    up=hi.rolling(period+1).apply(lambda x:100*(np.argmax(x)/period),raw=True)
    down=lo.rolling(period+1).apply(lambda x:100*(np.argmin(x)/period),raw=True)
    return up,down
def osma(close,fast,slow,signal):
    osc=ema(close,fast)-ema(close,slow)
    sig=ema(osc,signal)
    return osc,sig,osc-sig
def atr(df,n=14):
    pc=df.close.shift()
    tr=pd.concat([df.high-df.low,(df.high-pc).abs(),(df.low-pc).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/n,adjust=False).mean()
def calculate(candles,tf):
    if len(candles)<35:return {"ready":False,"reason":"Waiting for 35 candles","values":{}}
    df=pd.DataFrame(candles); c=df.close.astype(float)
    # 10s baseline: Aroon 10 and OSMA 10/20/10. Scale lookbacks with chart duration.
    scale=max(1,round(tf/10))
    aroon_n=max(10,min(50,10*scale))
    osma_fast=max(5,min(30,10*scale)); osma_slow=max(osma_fast+2,min(60,20*scale)); osma_signal=max(5,min(30,10*scale))
    jaw,teeth,lips=alligator(df); au,ad=aroon(df,aroon_n); om,oms,oh=osma(c,osma_fast,osma_slow,osma_signal)
    atrv=atr(df)
    last=lambda s:float(s.iloc[-1]) if pd.notna(s.iloc[-1]) else None
    return {"ready":True,"values":{
      "price":float(c.iloc[-1]),"jaw":last(jaw),"teeth":last(teeth),"lips":last(lips),
      "jaw_prev":float(jaw.iloc[-2]) if pd.notna(jaw.iloc[-2]) else None,
      "teeth_prev":float(teeth.iloc[-2]) if pd.notna(teeth.iloc[-2]) else None,
      "lips_prev":float(lips.iloc[-2]) if pd.notna(lips.iloc[-2]) else None,
      "aroon_up":last(au),"aroon_down":last(ad),"osma":last(om),"osma_signal":last(oms),"osma_hist":last(oh),
      "osma_hist_prev":float(oh.iloc[-2]) if pd.notna(oh.iloc[-2]) else None,"atr":last(atrv),
      "aroon_period":aroon_n,"osma_fast":osma_fast,"osma_slow":osma_slow,"osma_signal_period":osma_signal
    }}
