#!/usr/bin/env python3
"""Minimal ISO9660/GDFX directory walker for the Forza Horizon disc image.

Usage:
  python tools/iso_walk.py <iso> find <substring>   # list files whose path contains it
  python tools/iso_walk.py <iso> extract <iso_path> <out_path>
  python tools/iso_walk.py <iso> diff <local_root>  # list disc files missing locally
"""
import struct
import sys
import os

SECTOR = 2048


class Iso:
    def __init__(self, path):
        self.f = open(path, "rb")
        self.f.seek(16 * SECTOR)
        pvd = self.f.read(SECTOR)
        assert pvd[1:6] == b"CD001", "not an ISO9660 image"
        # Root directory record at offset 156 of the PVD.
        rec = pvd[156 : 156 + 34]
        self.root_extent = struct.unpack("<I", rec[2:6])[0]
        self.root_size = struct.unpack("<I", rec[10:14])[0]

    def read_sector(self, lba, count=1):
        self.f.seek(lba * SECTOR)
        return self.f.read(count * SECTOR)

    def walk(self):
        """Yield (path, extent_lba, size) for every file on the disc."""
        stack = [("/", self.root_extent, self.root_size)]
        while stack:
            path, extent, size = stack.pop()
            data = self.read_sector(extent, (size + SECTOR - 1) // SECTOR)
            offset = 0
            while offset < len(data):
                rec_len = data[offset]
                if rec_len == 0:
                    # Advance to the next sector boundary.
                    offset = ((offset // SECTOR) + 1) * SECTOR
                    if offset >= len(data):
                        break
                    continue
                rec = data[offset : offset + rec_len]
                offset += rec_len
                ext_attr = rec[1]
                lba = struct.unpack("<I", rec[2:6])[0]
                fsize = struct.unpack("<I", rec[10:14])[0]
                flags = rec[25]
                name_len = rec[32]
                raw_name = rec[33 : 33 + name_len]
                if ext_attr != 0:  # Joliet / SUSP entries not expected here
                    pass
                if name_len == 1 and raw_name[0] == 0:
                    continue  # "."
                if name_len == 1 and raw_name[0] == 1:
                    continue  # ".."
                # Strip the ';1' version suffix, unpad trailing dots.
                # GDFX stores names as UTF-16BE; fall back to ASCII for
                # images that use plain ISO names.
                try:
                    if name_len >= 2 and raw_name[1::2].count(0) >= name_len // 2:
                        name = raw_name.decode("utf-16-be")
                    else:
                        name = raw_name.decode("ascii")
                except UnicodeDecodeError:
                    name = raw_name.decode("latin-1")
                name = name.split(";")[0].rstrip(".")
                child_path = path + name + ("/" if flags & 2 else "")
                if flags & 2:
                    if lba and fsize:
                        stack.append((child_path, lba, fsize))
                else:
                    yield child_path, lba, fsize


def main():
    iso = Iso(sys.argv[1])
    cmd = sys.argv[2]
    if cmd == "find":
        needle = sys.argv[3].lower()
        for path, lba, size in iso.walk():
            if needle in path.lower():
                print(f"{path} lba={lba} size={size}")
    elif cmd == "extract":
        needle = sys.argv[3].lower()
        out = sys.argv[4]
        for path, lba, size in iso.walk():
            if path.lower().rstrip("/") == needle:
                os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
                with open(out, "wb") as w:
                    remaining = size
                    lba_cur = lba
                    while remaining > 0:
                        chunk = iso.read_sector(lba_cur, min(64, (remaining + SECTOR - 1) // SECTOR))
                        w.write(chunk[:remaining])
                        remaining -= len(chunk[:remaining])
                        lba_cur += 64
                print(f"extracted {path} ({size} bytes) -> {out}")
                return
        print("not found")
        return 1
    elif cmd == "diff":
        local_root = sys.argv[3]
        missing = 0
        for path, lba, size in iso.walk():
            rel = path.rstrip("/")
            local = os.path.join(local_root, *rel.split("/"))
            if not os.path.exists(local):
                print(f"MISSING {rel} ({size} bytes)")
                missing += 1
        print(f"total missing: {missing}")
    else:
        print("unknown command")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
