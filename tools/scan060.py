import glob
import re

for path in sorted(glob.glob(r"out\build\win-amd64-perf\logs\forzahorizon_060*.log")):
    with open(path, "rb") as f:
        lines = f.read().decode("utf-8", "replace").splitlines()
    spins = [(ln[11:23], re.search(r"count\(r3\)=(\d+)", ln).group(1))
             for ln in lines if "site=0x823F4F64" in ln]
    marks = {}
    for key in ("AMB_Festival", "replay_stream", "colourgradingmaps", "ForzaProfile"):
        hits = [ln[11:23] for ln in lines if key in ln]
        if hits:
            marks[key] = (len(hits), hits[0])
    print(path.split("\\")[-1], len(lines), "lines | spins:", spins[:8],
          "| marks:", marks)
