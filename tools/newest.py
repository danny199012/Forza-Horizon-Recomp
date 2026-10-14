import glob
import re

paths = sorted(glob.glob(r"out\build\win-amd64-perf\logs\forzahorizon_001*.log"))
path = paths[-1]
with open(path, "rb") as f:
    lines = f.read().decode("utf-8", "replace").splitlines()
print("newest:", path.split(chr(92))[-1], len(lines), "lines")
noise = ("XamXStudioRequest", "XMPGetPlayback", "XMPGetStatus", "getsockopt", "[gpu]",
         "yield-spin", "node@", "ring ", "unstick")
tail = [ln for ln in lines[-6000:] if not any(k in ln for k in noise)]
print("last 12 non-noise:")
for ln in tail[-12:]:
    print("   ", ln[:170])
banks = [ln for ln in lines if ".fsb" in ln]
print("fsb lines:", len(banks))
for b in banks[-6:]:
    print("   ", b[:150])
