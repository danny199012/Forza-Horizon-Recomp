import sys

path = sys.argv[1] if len(sys.argv) > 1 else r"out\build\win-amd64-perf\logs\forzahorizon_065.log"
with open(path, "rb") as f:
    data = f.read()
lines = data.decode("utf-8", "replace").splitlines()
print("lines:", len(lines))
for key in ("AMB_Festival", "caller lr=82", "yield-spin"):
    hits = [ln for ln in lines if key in ln]
    print(f"=== {key}: {len(hits)}")
    for h in hits[-14:]:
        print("   ", h[:180])
