import re, collections, glob, sys
c = collections.Counter()
examples = {}
for p in glob.glob(r'out\build\win-amd64-perf\logs\forzahorizon_*.log'):
    for ln in open(p, encoding='utf-8', errors='replace'):
        if 'cache:' not in ln:
            continue
        m = re.search(r"cache:\\([^'\"\\\r\n]*)", ln)
        key = m.group(1) if m else '<root>'
        c[key] += 1
        examples.setdefault(key, (p.split('\\')[-1], ln.strip()[:150]))
for k, v in c.most_common(20):
    print(v, repr(k), examples[k][0])
print('total', sum(c.values()))
