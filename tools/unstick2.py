import glob

for path in sorted(glob.glob(r"out\build\win-amd64-perf\logs\forzahorizon_0*.log")):
    with open(path, "rb") as f:
        lines = f.read().decode("utf-8", "replace").splitlines()
    hits = [ln for ln in lines
            if "unstick" in ln or "ring " in ln or "node@" in ln
            or "node+0->" in ln or "node+4->" in ln]
    print(f"== {path.split(chr(92))[-1]}: {len(lines)} lines")
    for h in hits[:60]:
        print("   ", h[:150])
