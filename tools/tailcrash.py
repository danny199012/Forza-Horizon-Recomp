path = r"out\build\win-amd64-perf\logs\forzahorizon_001.log"
with open(path, "rb") as f:
    lines = f.read().decode("utf-8", "replace").splitlines()
print("lines:", len(lines))
for key in ("Access violation", "guest ctx", "CRITICAL", "Unhandled", "fatal"):
    hits = [ln for ln in lines if key.lower() in ln.lower()]
    if hits:
        print(f"=== {key}: {len(hits)}")
        for h in hits[:6]:
            print("   ", h[:180])
print("=== last 25 non-noise lines:")
noise = ("XamXStudioRequest", "XMPGetPlayback", "XMPGetStatus", "getsockopt", "[gpu]")
shown = 0
for ln in reversed(lines):
    if any(k in ln for k in noise):
        continue
    print("   ", ln[:180])
    shown += 1
    if shown >= 25:
        break
