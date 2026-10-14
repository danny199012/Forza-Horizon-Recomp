import re

path = r"out\build\win-amd64-perf\logs\forzahorizon_060.log"
with open(path, "rb") as f:
    lines = f.read().decode("utf-8", "replace").splitlines()
print("lines:", len(lines))
for i, ln in enumerate(lines):
    if "site=0x823F4F64" in ln:
        m = re.search(r"count\(r3\)=(\d+)", ln)
        print("spin @", ln[11:23], "pending:", m.group(1) if m else "?")
for key in ("AMB_Festival", "replay_stream", "ghost_stream", "colourgradingmaps",
            "PlayerDatabase", "ForzaProfile", "BaseHeap::Release"):
    hits = [ln for ln in lines if key in ln]
    print(f"{key}: {len(hits)}", ("| first: " + hits[0][11:23]) if hits else "")
