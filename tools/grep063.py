import sys

log = sys.argv[1] if len(sys.argv) > 1 else r"out\build\win-amd64-perf\logs\forzahorizon_063.log"
keys = ["SectorInformation", "bin.zip", "soundbank_lookup", "AMB_Festival", "XSetCurrentDirectory",
        "SetCurrentDirectory", "NtSetInformationFile"]
counts = {k: 0 for k in keys}
samples = {k: [] for k in keys}
for ln in open(log, encoding="utf-8", errors="replace"):
    for k in keys:
        if k in ln:
            counts[k] += 1
            if len(samples[k]) < 4:
                samples[k].append(ln.strip()[:150])
for k in keys:
    print(f"--- {k}: {counts[k]}")
    for s in samples[k]:
        print("   ", s)
