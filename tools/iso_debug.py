import struct

f = open(r'..\Forza Horizon (USA) (En,Ja,Fr,De,Es,It,Pt,Zh,Pl,Ru).iso', 'rb')
for lba in (16, 17, 18, 19, 20):
    f.seek(lba * 2048)
    vd = f.read(2048)
    print(f'sector {lba}: type={vd[0]} magic={vd[1:6]!r} ver={vd[6]}')
    if vd[0] == 1:
        rec = vd[156:190]
        print(f'  PVD root: lba={struct.unpack("<I", rec[2:6])[0]} size={struct.unpack("<I", rec[10:14])[0]}')
    if vd[0] == 2:
        rec = vd[156:190]
        print(f'  SVD root: lba={struct.unpack("<I", rec[2:6])[0]} size={struct.unpack("<I", rec[10:14])[0]}')

root_lba, root_size = 24, 112
f.seek(root_lba * 2048)
data = f.read(2048)
off = 0
count = 0
while off < 2048 and count < 10:
    rl = data[off]
    if rl == 0:
        off = ((off // 2048) + 1) * 2048
        continue
    rec = data[off:off + rl]
    off += rl
    nl = rec[32]
    raw = rec[33:33 + nl]
    flags = rec[25]
    lba = struct.unpack('<I', rec[2:6])[0]
    size = struct.unpack('<I', rec[10:14])[0]
    try:
        u = raw.decode('utf-16-be')
    except Exception:
        u = '?'
    safe = raw.hex()
    usafe = u.encode('unicode_escape').decode('ascii')
    print(f'rec: len={rl} flags={flags} lba={lba} size={size} raw_hex={safe} utf16={usafe!r}')
    count += 1
