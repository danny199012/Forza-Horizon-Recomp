import re

samples = []
cur = None
for ln in open(r"out\build\win-amd64-perf\logs\watchdog.log", encoding="utf-8", errors="replace"):
    m = re.match(r"--- sample (\d\d:\d\d:\d\d\.\d\d\d)", ln)
    if m:
        cur = (m.group(1), {})
        samples.append(cur)
    elif cur is not None and ln.startswith("  tid"):
        tid = ln.split()[1]
        cur[1][tid] = ln.strip()

print("samples:", [s[0] for s in samples])
for s in samples:
    t = s[1].get("24776")
    if t:
        g = re.findall(r"G_imp__sub_[0-9A-F]{8}\+0x[0-9a-fA-F]+", t)
        print(s[0], "t24776:", " <- ".join(g[:8]))
