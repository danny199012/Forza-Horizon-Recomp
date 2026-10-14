import re

path = r"..\rexglue-sdk\src\system\xmemory.cpp"
for i, ln in enumerate(open(path, encoding="utf-8", errors="replace"), 1):
    s = ln.rstrip()
    if re.match(r"^\}+", s) or "namespace" in s or "DumpGuestCrashState" in s or "InGuestCodeRange" in s:
        if len(s) < 60:
            print(f"{i}: {s}")
