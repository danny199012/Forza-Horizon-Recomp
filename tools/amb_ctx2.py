import sys

log = sys.argv[1] if len(sys.argv) > 1 else r"out\build\win-amd64-perf\logs\forzahorizon_064.log"
lines = open(log, encoding="utf-8", errors="replace").readlines()
for key in ("SectorInformation", "soundbank_lookup", "bin.zip", "SetCurrentDirectory"):
    hits = [ln.rstrip() for ln in lines if key in ln]
    print(f"=== {key}: {len(hits)}")
    for h in hits[:5]:
        print("   ", h[:170])

idx = [i for i, ln in enumerate(lines) if "AMB_Festival.fsb" in ln]
if idx:
    last = idx[-1]
    print(f"=== after last failure (line {last}):")
    shown = 0
    for i in range(last + 1, min(len(lines), last + 3000)):
        t = lines[i].rstrip()
        if "[fs]" not in t and "[krnl]" not in t:
            continue
        if "XamXStudioRequest" in t or "XMPGetPlayback" in t or "XMPGetStatus" in t:
            continue
        print("   ", t[:190])
        shown += 1
        if shown > 60:
            break
else:
    print("no AMB hits")
