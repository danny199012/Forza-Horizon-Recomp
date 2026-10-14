import re
from collections import Counter

name = r"out\build\win-amd64-perf\logs\forzahorizon_064.1.log"
lines = open(name, encoding="utf-8", errors="replace").readlines()
window = [ln.rstrip() for ln in lines
          if "10:24:" in ln and ("[fs]" in ln or "[krnl]" in ln)
          and "XamXStudioRequest" not in ln and "XMPGetPlayback" not in ln
          and "XMPGetStatus" not in ln and "getsockopt" not in ln]
print("10:24 fs/krnl non-noise:", len(window))
pat = Counter()
for s in window:
    key = re.sub(r"0x[0-9a-fA-F]+", "X", s)
    key = re.sub(r"\d\d:\d\d:\d\d\.\d\d\d", "T", key)
    key = re.sub(r"\[t\d+\]", "[t]", key)
    pat[key[:130]] += 1
for k, c in pat.most_common(25):
    print(f"{c:5d}  {k}")
