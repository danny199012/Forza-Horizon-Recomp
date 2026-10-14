import glob

for path in sorted(glob.glob(r"out\build\win-amd64-perf\logs\forzahorizon_0*.log")):
    with open(path, "rb") as f:
        data = f.read()
    lines = data.decode("utf-8", "replace").splitlines()
    hits = [ln for ln in lines if "unstick" in ln]
    print(f"{path.split(chr(92))[-1]}: {len(lines)} lines, unstick: {len(hits)}")
    for h in hits[:12]:
        print("   ", h[:150])
    for key in ("AMB_Festival", "replay_stream", "colourgradingmaps", "ForzaProfile"):
        n = sum(1 for ln in lines if key in ln)
        if n:
            print(f"    {key}: {n}")
