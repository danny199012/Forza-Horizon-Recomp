import re
from collections import Counter

path = r"out\build\win-amd64-perf\logs\forzahorizon_060.log"
with open(path, "rb") as f:
    lines = f.read().decode("utf-8", "replace").splitlines()
print("lines:", len(lines))
per_min = Counter()
last_lines = []
for ln in lines:
    m = re.match(r"\[2026-10-14 (\d\d:\d\d):", ln)
    noise = ("XamXStudioRequest" in ln or "XMPGetPlayback" in ln
             or "XMPGetStatus" in ln or "getsockopt" in ln
             or "yield-spin" in ln or "[gpu]" in ln)
    if m and ("[fs]" in ln or "[krnl]" in ln) and not noise:
        per_min[m.group(1)] += 1
        last_lines.append(ln)
for k in sorted(per_min):
    print(f"  {k}: {per_min[k]}")
print("--- last 12 real fs/krnl lines:")
for t in last_lines[-12:]:
    print("   ", t[:175])
