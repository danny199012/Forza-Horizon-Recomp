import sys

path = sys.argv[1] if len(sys.argv) > 1 else r"out\build\win-amd64-perf\logs\forzahorizon_066.log"
with open(path, "rb") as f:
    data = f.read()
lines = data.decode("utf-8", "replace").splitlines()
print("lines:", len(lines))
out = []
for i, ln in enumerate(lines):
    if "yield-spin #512" in ln and "site=0x823F4F64" in ln:
        out.append(ln)
        for j in range(i + 1, min(len(lines), i + 32)):
            if "[obj+" in lines[j]:
                out.append(lines[j])
            else:
                break
        out.append("----")
for ln in out[-40:]:
    print(ln[:150])
