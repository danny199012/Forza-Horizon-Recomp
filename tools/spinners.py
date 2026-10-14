import re

samples = []
cur = None
for ln in open(r"out\build\win-amd64-perf\logs\watchdog.log", encoding="utf-8", errors="replace"):
    m = re.match(r"--- sample (\d\d:\d\d:\d\d\.\d\d\d)", ln)
    if m:
        cur = (m.group(1), {})
        samples.append(cur)
    elif cur is not None and ln.startswith("  tid"):
        tid = ln.split()[1]
        cur[1][tid] = ln.strip()

# For each thread, classify each sample: WAITING (host wait), RUNNING (guest code, no host wait)
from collections import defaultdict
states = defaultdict(list)
for tstamp, threads in samples:
    for tid, t in threads.items():
        waiting = "NtWaitForSingleObject" in t or "ZwDelayExecution" in t or "WaitForMultipleObjects" in t or "WaitForWorkViaWorkerFactory" in t or "SignalAndWait" in t or "WaitForSingleObjectEx" in t
        guest = re.findall(r"G_imp__sub_[0-9A-F]{8}", t)
        key = re.findall(r"G_imp__sub_([0-9A-F]{8})\+0x([0-9a-fA-F]+)", t)
        states[tid].append((tstamp, "W" if waiting else "R", key[:6]))

# threads that are RUNNING (R) in >=3 samples
print("threads RUNNING in >=3 samples (potential spins):")
for tid, st in states.items():
    runs = [s for s in st if s[1] == "R"]
    if len(runs) >= 3:
        print(f"tid {tid}: {len(runs)}/{len(st)} samples RUNNING")
        for s in runs[:12]:
            print("   ", s[0], " <- ".join(f"{a}+{b}" for a, b in s[2]))
