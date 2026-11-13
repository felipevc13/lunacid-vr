#!/usr/bin/env python3
"""Per-scene headset telemetry from a session log.

The Quest compositor logs one VrApi line per second (FPS, GPU%/CPU% utilisation, CPU/GPU clock
levels, app frame time, temperature); the port logs "LUNA_PERF scene <name>" on every scene change.
Record a session with
    adb logcat -v time | grep --line-buffered -E "LUNA|VrApi" > session.log
then: python3 tools/telemetry/scene_telemetry.py session.log
"""
import re,sys,statistics as st
scene=None; rows={}
for line in open(sys.argv[1],errors='ignore'):
    m=re.search(r'LUNA_PERF scene (\S+)',line)
    if m: scene=m.group(1); continue
    if 'VrApi' not in line or 'FPS=' not in line or scene is None: continue
    f=dict(re.findall(r'(\w[\w%&/]*)=([^,]+)',line))
    try:
        fps=int(f['FPS'].split('/')[0]); gpu=float(f['GPU%']); cpu=float(f['CPU%'].split('(')[0])
        app=float(f['App'].rstrip('ms')); lv=f['CPU4/GPU']; temp=f['Temp'].split('C')[0]
    except Exception: continue
    rows.setdefault(scene,[]).append((fps,gpu,cpu,app,lv,float(temp)))
print(f"{'cena':12} {'seg':>4} {'fps med':>7} {'fps min':>7} {'GPU% med':>8} {'GPU% max':>8} {'CPU% med':>8} {'App ms':>6} {'nivel CPU/GPU':>13} {'temp':>5}")
for s,r in rows.items():
    fps=[x[0] for x in r]; g=[x[1] for x in r]; c=[x[2] for x in r]; a=[x[3] for x in r]
    print(f"{s:12} {len(r):4} {st.mean(fps):7.1f} {min(fps):7} {st.mean(g)*100:7.0f}% {max(g)*100:7.0f}% {st.mean(c)*100:7.0f}% {st.mean(a):6.2f} {st.mode([x[4] for x in r]):>13} {max(x[5] for x in r):5.1f}")
