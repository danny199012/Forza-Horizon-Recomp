import glob
import re

pat = re.compile(r"REX_STORE_U32\(ctx\.r(\d+)\.u32 \+ (132|136|156|160), ([^;]+)\)")
hits = []
for p in glob.glob(r"generated/default/forzahorizon_recomp.*.cpp"):
    with open(p, encoding="utf-8", errors="replace") as f:
        for i, ln in enumerate(f, 1):
            m = pat.search(ln)
            if m:
                hits.append((p.split("\\")[-1], i, ln.strip()[:140]))
print(len(hits), "hits")
for h in hits[:40]:
    print(f"{h[0]}:{h[1]}:", h[2])
