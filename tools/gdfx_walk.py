#!/usr/bin/env python3
"""GDFX (Xbox 360 game disc) filesystem walker.

Format (per free60.org): descriptor at some LBA with "MICROSOFT*XBOX*MEDIA",
root sector/size at +20/+24. Directory entries:
  [0..3] unk, [4..7] sector, [8..11] size, [12] flags, [13] name_len, [14..] name
Records are 4-byte aligned (0xFF padded). DIRECTORY flag = 0x10.

Usage:
  python tools/gdfx_walk.py <iso> find <substring>
  python tools/gdfx_walk.py <iso> ls <dir_path>
  python tools/gdfx_walk.py <iso> extract <disc_path> <out_file>
  python tools/gdfx_walk.py <iso> diff <local_root>
"""
import struct
import sys
import os

SECTOR = 2048
MAGIC = b"MICROSOFT*XBOX*MEDIA"


class Gdfx:
    def __init__(self, path):
        self.f = open(path, "rb")
        self.root_sector = None
        self.root_size = None
        self.offset = 0
        self._find_descriptor()

    def read(self, lba, count=1):
        self.f.seek(lba * SECTOR)
        return self.f.read(count * SECTOR)

    def _try_offset(self, delta):
        """Check whether root_sector+delta parses as a dirent table."""
        data = self.read(self.root_sector + delta,
                         (self.root_size + SECTOR - 1) // SECTOR)[: self.root_size]
        off = 0
        ok = 0
        while off + 14 <= len(data):
            unk, sector, fsize = struct.unpack("<III", data[off : off + 12])
            nl = data[off + 13]
            if nl == 0 or sector == 0xFFFFFFFF or fsize == 0xFFFFFFFF:
                break
            name = data[off + 14 : off + 14 + nl]
            if not (0 < nl < 256) or any(b < 32 or b > 126 for b in name):
                return False
            ok += 1
            off += (14 + nl + 3) & ~3
        return ok >= 3

    def _find_descriptor(self):
        size = os.path.getsize(self.f.name)
        pos = 0
        chunk_size = 32 * 1024 * 1024
        while pos < size:
            self.f.seek(pos)
            data = self.f.read(chunk_size + len(MAGIC))
            idx = data.find(MAGIC)
            while idx != -1:
                off = pos + idx
                base = off % SECTOR
                sec = self.read(off // SECTOR)
                if sec[base : base + 20] == MAGIC and base + 32 <= SECTOR:
                    root_sector = struct.unpack("<I", sec[base + 20 : base + 24])[0]
                    root_size = struct.unpack("<I", sec[base + 24 : base + 28])[0]
                    if 0 < root_size < 64 * 1024 * 1024:
                        # Some images (XGD3 redumps) shift the whole GDFX
                        # partition by a constant physical offset. Probe the
                        # known shift, then plain.
                        for delta in (16640, 0, 16639, 16641):
                            self.root_sector = root_sector
                            self.root_size = root_size
                            self.offset = delta
                            if self._try_offset(delta):
                                return
                idx = data.find(MAGIC, idx + 1)
            pos += chunk_size
        raise RuntimeError("GDFX descriptor not found")

    def read_dir(self, lba, size):
        """Yield (name, sector, file_size, flags, unk) dirents (logical LBAs)."""
        size = min(size, 8 * 1024 * 1024)  # guard against bogus dirent sizes
        data = self.read(lba + self.offset,
                         (size + SECTOR - 1) // SECTOR)[:size]
        off = 0
        while off + 14 <= len(data):
            unk, sector, fsize = struct.unpack("<III", data[off : off + 12])
            flags = data[off + 12]
            nl = data[off + 13]
            if nl == 0 or sector == 0xFFFFFFFF or fsize == 0xFFFFFFFF:
                break
            name = data[off + 14 : off + 14 + nl].decode("latin-1")
            rec = (14 + nl + 3) & ~3
            yield name, sector, fsize, flags, unk
            off += rec

    def walk(self, path="/", lba=None, size=None):
        """Yield (full_path, sector, file_size, flags)."""
        if lba is None:
            lba, size = self.root_sector, self.root_size
        for name, sector, fsize, flags, _unk in self.read_dir(lba, size):
            child_path = path.rstrip("/") + "/" + name
            if flags & 0x10:
                yield from self.walk(child_path, sector, fsize)
            else:
                yield child_path, sector, fsize, flags


def find_entry(g, disc_path):
    parts = [p for p in disc_path.split("/") if p]
    lba, size = g.root_sector, g.root_size
    entry = None
    for part in parts:
        found = False
        for name, sector, fsize, flags, _unk in g.read_dir(lba, size):
            if name.lower() == part.lower():
                lba, size = sector, fsize
                entry = (sector, fsize, flags)
                found = True
                break
        if not found:
            return None
    return entry


def extract_file(g, disc_path, out):
    entry = find_entry(g, disc_path)
    if not entry or (entry[2] & 0x10):
        print("not found:", disc_path)
        return False
    sector, fsize, _flags = entry
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    written = 0
    with open(out, "wb") as w:
        while written < fsize:
            n = min(64 * SECTOR, fsize - written)
            w.write(g.read(sector + written // SECTOR + g.offset,
                           (n + SECTOR - 1) // SECTOR)[:n])
            written += n
    print(f"extracted {disc_path} ({fsize} bytes) -> {out}")
    return True


def main():
    g = Gdfx(sys.argv[1])
    cmd = sys.argv[2]
    if cmd == "find":
        needle = sys.argv[3].lower()
        for path, sector, size, flags in g.walk():
            if needle in path.lower():
                print(f"{path} sector={sector} size={size}")
    elif cmd == "ls":
        entry = find_entry(g, sys.argv[3])
        if not entry or not (entry[2] & 0x10):
            print("not a directory")
            return 1
        for name, sector, fsize, flags, _u in g.read_dir(entry[0], entry[1]):
            kind = "<DIR>" if flags & 0x10 else str(fsize)
            print(f"{kind:>12} {name}  flags={flags:#04x}")
    elif cmd == "extract":
        return 0 if extract_file(g, sys.argv[3], sys.argv[4]) else 1
    elif cmd == "diff":
        local_root = sys.argv[3]
        missing = 0
        total = 0
        for path, sector, size, flags in g.walk():
            rel = path.lstrip("/")
            local = os.path.join(local_root, *rel.split("/"))
            total += 1
            if not os.path.exists(local):
                if missing < 300:
                    print(f"MISSING {rel} ({size} bytes)")
                missing += 1
        print(f"total files on disc: {total}, missing locally: {missing}")
    else:
        print("unknown command")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
