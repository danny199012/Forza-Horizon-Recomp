import glob

hits = []
for p in glob.glob(r"generated/default/forzahorizon_recomp.*.cpp"):
    with open(p, encoding="utf-8", errors="replace") as f:
        for i, ln in enumerate(f, 1):
            if "0x7D0" in ln or "0x7d0" in ln:
                hits.append((p.split("\\")[-1], i, ln.strip()[:130]))
print(len(hits), "hits")
for h in hits[:25]:
    print(f"{h[0]}:{h[1]}:", h[2])
