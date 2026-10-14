import re

BASE = r"out\build\win-amd64-perf\logs"

for num, label in (("049", "049-working"), ("051", "051-working"),
                   ("056", "056-frozen"), ("058", "058-frozen"),
                   ("063", "063-frozen")):
    p = rf"{BASE}\forzahorizon_{num}.log"
    try:
        lines = open(p, encoding="utf-8", errors="replace").readlines()
    except FileNotFoundError:
        print(label, "missing")
        continue
    n_eff = sum(1 for ln in lines if "media\\effects\\" in ln and "FAILED" in ln)
    n_cg = sum(1 for ln in lines if "colourgradingmaps" in ln and "FAILED" in ln)
    n_amb = sum(1 for ln in lines if "AMB_Festival.fsb" in ln)
    n_bx = sum(1 for ln in lines if "bin.zip" in ln.lower())
    # last successful fs resolution (non-failed)
    last_ok = None
    for ln in lines:
        if "[fs]" in ln and "resolved" in ln and "FAILED" not in ln:
            last_ok = ln.strip()
    print(f"{label}: effectsFAILED={n_eff} colourFAILED={n_cg} ambFest={n_amb} binzip={n_bx}")
    if last_ok:
        print("   last ok fs:", last_ok[:150])
