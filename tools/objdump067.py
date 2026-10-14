import sys

path = sys.argv[1] if len(sys.argv) > 1 else r"out\build\win-amd64-perf\logs\forzahorizon_067.log"
try:
    with open(path, "rb") as f:
        data = f.read()
except FileNotFoundError:
    print("no log yet")
    sys.exit(0)
lines = data.decode("utf-8", "replace").splitlines()
print("lines:", len(lines))
hits = [i for i, ln in enumerate(lines) if "site=0x823F4F64" in ln]
print("queue-wait spins:", len(hits))
shown = 0
for i in hits[-3:]:
    for j in range(i, min(len(lines), i + 45)):
        ln = lines[j]
        if "[obj+" in ln or "node@" in ln or "mgr(" in ln or "[mgr+" in ln or "yield-spin" in ln or "obj=" in ln:
            print(ln[:160])
            shown += 1
    print("----")
    if shown > 90:
        break
