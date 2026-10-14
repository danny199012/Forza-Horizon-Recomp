import os

for root, dirs, files in os.walk(r"..\rexglue-sdk\include\rex\ppc"):
    for fn in files:
        p = os.path.join(root, fn)
        data = open(p, encoding="utf-8", errors="replace").read()
        if "INDIRECT_FUNC" in data:
            print("==", p)
            for i, ln in enumerate(data.splitlines(), 1):
                if "INDIRECT_FUNC" in ln:
                    print(f"   {i}: {ln.strip()[:150]}")


