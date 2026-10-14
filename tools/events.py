import glob
import re
from collections import Counter

for path in sorted(glob.glob(r"out\build\win-amd64-perf\logs\forzahorizon_001*.log")):
    with open(path, "rb") as f:
        lines = f.read().decode("utf-8", "replace").splitlines()
    counts = Counter()
    samples = {}
    for ln in lines:
        for key in ("KeSetEvent", "KeReleaseSemaphore", "KePulseEvent", "NtReleaseSemaphore"):
            if key in ln and "STUB" not in ln:
                counts[key] += 1
                samples.setdefault(key, [])
                if len(samples[key]) < 3:
                    samples[key].append(ln.strip()[:150])
    if counts:
        print(f"== {path.split(chr(92))[-1]}")
        for k, c in counts.most_common():
            print(f"   {k}: {c}")
            for s in samples[k]:
                print("      ", s)
