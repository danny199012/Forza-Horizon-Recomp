import sys

log = sys.argv[1] if len(sys.argv) > 1 else r"out\build\win-amd64-perf\logs\forzahorizon_064.log"
lines = open(log, encoding="utf-8", errors="replace").readlines()
idx = [i for i, ln in enumerate(lines) if "AMB_Festival.fsb" in ln]
print("AMB_Festival.fsb hits:", len(idx))
if idx:
    start = max(0, idx[0] - 400)
    end = min(len(lines), idx[-1] + 200)
    shown = 0
    for i in range(start, end):
        t = lines[i].rstrip()
        if "[fs]" not in t and "[krnl]" not in t:
            continue
        if "XamXStudioRequest" in t or "XMPGetPlaybackController" in t or "XMPGetStatus" in t:
            continue
        print(t[:200])
        shown += 1
        if shown > 120:
            break
else:
    print("no hits yet")
