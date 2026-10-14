import re

target = 0x82CD1BB8
funcs = []
pat = re.compile(r"\{\s*(0x[0-9A-Fa-f]+),\s*(sub_[0-9A-Fa-f]+)\s*\}")
for ln in open(r"generated/default/forzahorizon_init.cpp", encoding="utf-8", errors="replace"):
    m = pat.search(ln)
    if m:
        funcs.append((int(m.group(1), 16), m.group(2)))
funcs.sort()
for i, (a, n) in enumerate(funcs):
    if a == target:
        print(hex(a), n, "-> next:", hex(funcs[i + 1][0]), funcs[i + 1][1],
              "size:", funcs[i + 1][0] - a)
        break
