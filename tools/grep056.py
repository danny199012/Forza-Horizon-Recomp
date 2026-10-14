for ln in open(r"out\build\win-amd64-perf\logs\forzahorizon_056.log",
               encoding="utf-8", errors="replace"):
    if "bin.zip" in ln.lower() or "AMB_Festival" in ln:
        print(ln.rstrip()[:170])
