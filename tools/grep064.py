import glob

for p in sorted(glob.glob(r"out\build\win-amd64-perf\logs\forzahorizon_064*.log")):
    hits = {"SectorInformation": 0, "bin.zip": 0, "soundbank_lookup": 0}
    samples = []
    for ln in open(p, encoding="utf-8", errors="replace"):
        for k in hits:
            if k in ln:
                hits[k] += 1
                if len(samples) < 12:
                    samples.append((k, ln.strip()[:150]))
    name = p.split("\\")[-1]
    print(f"=== {name}: {hits}")
    for k, s in samples:
        print("   ", s)
