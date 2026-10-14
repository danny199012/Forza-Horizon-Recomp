import struct

data = open(r"tools/xexdump/default_base.bin", "rb").read()


def rd(va, n):
    off = va - 0x82000000
    return data[off:off + n]


for va in (0x82020FCC, 0x82020CFC):
    b = rd(va, 40)
    txt = "".join(chr(c) if 32 <= c < 127 else "." for c in b)
    print(f"{va:#010x}: {txt!r}")
