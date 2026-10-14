import re
from collections import Counter

for name in (r"out\build\win-amd64-perf\logs\forzahorizon_064.1.log",
             r"out\build\win-amd64-perf\logs\forzahorizon_064.log"):
    lines = open(name, encoding="utf-8", errors="replace").readlines()
    print(f"=== {name.split(chr(92))[-1]}: {len(lines)} lines")
    per_min = Counter()
    samples = []
    for ln in lines:
        m = re.match(r"\[2026-10-14 (\d\d:\d\d):", ln)
        if m and ("[fs]" in ln or "[krnl]" in ln):
            per_min[m.group(1)] += 1
            if len(samples) < 80:
                samples.append(ln.rstrip())
    for k in sorted(per_min):
        print(f"  {k}: {per_min[k]}")
    seen = set()
    shown = 0
    for s in samples:
        key = re.sub(r"0x[0-9a-fA-F]+", "X", s)
        key = re.sub(r"\d\d:\d\d:\d\d\.\d\d\d", "T", key)
        if key in seen:
            continue
        seen.add(key)
        print("   ", s[:170])
        shown += 1
        if shown > 25:
            break
