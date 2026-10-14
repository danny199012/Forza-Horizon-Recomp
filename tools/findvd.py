import struct
import os
import struct

root = r"E:\Xbox 360 Games\Torrent\Minerva_Myrient\No-Intro"
root += r"\Microsoft - Xbox 360 (Digital)\Forza Horizon DLC"
n = 0
for dirpath, dirs, files in os.walk(root):
    for fn in files:
        n += 1
        if n > 5:
            break
        p = os.path.join(dirpath, fn)
        d = open(p, "rb").read(0x400)
        vt = struct.unpack(">I", d[0x3A9:0x3AD])[0]
        print(os.path.basename(fn)[:24], "| magic", d[0:4], "| voltype", vt,
              "| vd_len", d[0x379], "| ft_blocks",
              struct.unpack(">H", d[0x37C:0x37E])[0])
print("total files walked:", n)
