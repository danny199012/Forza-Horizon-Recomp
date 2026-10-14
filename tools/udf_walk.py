#!/usr/bin/env python3
"""Minimal UDF (ECMA-167/ISO-13346) walker for Xbox 360 GDFX disc images.

Usage:
  python tools/udf_walk.py <iso> find <substring>
  python tools/udf_walk.py <iso> ls <dir_path>
  python tools/udf_walk.py <iso> extract <disc_path> <out_file>
  python tools/udf_walk.py <iso> diff <local_root>
"""
import struct
import sys
import os

SECTOR = 2048


def read_tag(data):
    """UDF descriptor tag: (tag_id, tag_location).
    Checksum = sum of all tag bytes except the checksum byte itself (offset 4)."""
    tag_id, version, cksum, _res, _serial, _crc, _crc_len, loc = struct.unpack(
        "<HHBBHHHI", data[:16])
    ck = (sum(data[0:4]) + sum(data[5:16])) & 0xFF
    if ck != cksum:
        return None, None
    return tag_id, loc


class Udf:
    def __init__(self, path):
        self.f = open(path, "rb")
        self.block_size = SECTOR
        self.partition_start = None
        self.root_icb = None
        self._parse_volume()

    def read_block(self, lba, count=1):
        self.f.seek(lba * self.block_size)
        return self.f.read(count * self.block_size)

    def _parse_volume(self):
        avdp = None
        # GDFX places the UDF descriptors past the ISO shell: scan for the
        # first valid Anchor Volume Descriptor Pointer.
        for lba in range(240, 1024):
            data = self.read_block(lba)
            tag, _ = read_tag(data)
            if tag == 8:
                avdp = data
                break
        if avdp is None:
            size = os.path.getsize(self.f.name)
            last = size // self.block_size - 1
            for lba in (last, last - 256):
                data = self.read_block(lba)
                tag, _ = read_tag(data)
                if tag == 8:
                    avdp = data
                    break
        if avdp is None:
            raise RuntimeError("no UDF anchor found")
        if avdp is None:
            pass
        # GDFX images write the anchor with empty extents; the volume
        # descriptors live in a fixed sequence right after the ISO shell.
        # Scan 240..1024 for the first Partition (5) and Logical Volume (6)
        # descriptors directly.
        pd = None
        lvd = None
        for lba in range(240, 1024):
            data = self.read_block(lba)
            tag, _ = read_tag(data)
            if tag == 5 and pd is None:
                pd = data
            elif tag == 6 and lvd is None:
                lvd = data
            if pd and lvd:
                break
        if pd is None or lvd is None:
            raise RuntimeError("missing partition/logical volume descriptor")
        self.partition_start = struct.unpack("<I", pd[184:188])[0]
        self.block_size = struct.unpack("<I", lvd[212:216])[0]
        fsd_len, fsd_loc = struct.unpack("<II", lvd[248:256])
        fsd_lba = self.partition_start + fsd_loc
        fsd = self.read_block(fsd_lba)
        tag, _ = read_tag(fsd)
        if tag != 256:
            raise RuntimeError(f"expected FSD at {fsd_lba}, got tag {tag}")
        _len, root_loc = struct.unpack("<II", fsd[400:408])
        self.root_icb = self.partition_start + root_loc

    def read_icb(self, lba):
        """Read a File/Extended File Entry; returns (file_type, info_len, extents)."""
        data = self.read_block(lba)
        tag, _ = read_tag(data)
        if tag not in (261, 266):
            raise RuntimeError(f"expected file entry at {lba}, got tag {tag}")
        file_type = data[39]
        info_len = struct.unpack("<Q", data[56:64])[0]
        l_ea = struct.unpack("<H", data[168:170])[0]
        l_ad = struct.unpack("<I", data[170:174])[0]
        flags = struct.unpack("<H", data[46:48])[0]
        ad_type = flags & 7
        extents = []
        ad_base = 176 + l_ea
        ad_data = data[ad_base : ad_base + l_ad]
        if ad_type == 0:  # short_ad
            for off in range(0, len(ad_data) - 7, 8):
                entry_len, pos = struct.unpack("<II", ad_data[off : off + 8])
                etype = entry_len >> 30
                if etype in (0, 1):
                    extents.append((self.partition_start + (pos & 0x3FFFFFFF),
                                    entry_len & 0x3FFFFFFF))
                elif etype == 3:
                    cont = self.read_block(self.partition_start + pos,
                                           (entry_len + self.block_size - 1) // self.block_size)
                    for c in range(0, len(cont) - 7, 8):
                        el, p = struct.unpack("<II", cont[c : c + 8])
                        if el >> 30 in (0, 1):
                            extents.append((self.partition_start + p, el & 0x3FFFFFFF))
        elif ad_type == 1:  # long_ad
            for off in range(0, len(ad_data) - 15, 16):
                entry_len, pos = struct.unpack("<II", ad_data[off : off + 8])
                etype = entry_len >> 30
                if etype in (0, 1):
                    extents.append((self.partition_start + pos, entry_len & 0x3FFFFFFF))
        elif ad_type == 3:  # embedded in the ICB itself
            extents.append((lba, info_len))
        return file_type, info_len, extents

    def read_dir(self, lba):
        """Read a directory ICB; yields (name, child_icb_lba, is_dir)."""
        _ftype, info_len, extents = self.read_icb(lba)
        data = b"".join(self.read_block(l, (n + self.block_size - 1) // self.block_size)[:n]
                        for l, n in extents)[:info_len]
        off = 0
        while off + 38 <= len(data):
            tag, _ = read_tag(data[off : off + 16])
            if tag != 257:
                break
            total_len = struct.unpack("<H", data[off + 16 : off + 18])[0]
            l_fi = data[off + 19]
            icb_lba = struct.unpack("<I", data[off + 20 : off + 24])[0]
            name = data[off + 36 : off + 36 + l_fi].decode("utf-8", "replace")
            is_dir = (data[off + 18] & 0x08) != 0
            if name not in (".", ".."):
                yield name, self.partition_start + icb_lba, is_dir
            off += total_len
            off = (off + 3) & ~3

    def walk(self, path="/", lba=None):
        """Yield (full_path, icb_lba, size) for every file."""
        if lba is None:
            lba = self.root_icb
        for name, child, is_dir in self.read_dir(lba):
            child_path = (path.rstrip("/") + "/" + name)
            if is_dir:
                yield from self.walk(child_path, child)
            else:
                _ft, info_len, _ = self.read_icb(child)
                yield child_path, child, info_len


def find_entry(iso, disc_path):
    """Resolve a disc path to (icb_lba, size, is_dir) or None."""
    parts = [p for p in disc_path.split("/") if p]
    lba = iso.root_icb
    entry = None
    for part in parts:
        found = False
        for name, child, is_dir in iso.read_dir(lba):
            if name.lower() == part.lower():
                lba = child
                entry = (child, is_dir)
                found = True
                break
        if not found:
            return None
    if entry is None:
        return None
    child, is_dir = entry
    if is_dir:
        return child, 0, True
    _ft, info_len, _ = iso.read_icb(child)
    return child, info_len, False


def extract_file(iso, disc_path, out):
    target = find_entry(iso, disc_path)
    if not target or target[2]:
        print("not found:", disc_path)
        return False
    lba, size, _ = target
    _ft, info_len, extents = iso.read_icb(lba)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    written = 0
    with open(out, "wb") as w:
        for elba, elen in extents:
            remaining = min(elen, size - written)
            src = 0
            while remaining > 0:
                n = min(64 * SECTOR, remaining)
                w.write(iso.read_block(elba + src // SECTOR, (n + SECTOR - 1) // SECTOR)[:n])
                remaining -= n
                written += n
                src += n
    print(f"extracted {disc_path} ({size} bytes) -> {out}")
    return True


def main():
    iso = Udf(sys.argv[1])
    cmd = sys.argv[2]
    if cmd == "find":
        needle = sys.argv[3].lower()
        for path, lba, size in iso.walk():
            if needle in path.lower():
                print(f"{path} icb={lba} size={size}")
    elif cmd == "ls":
        target = find_entry(iso, sys.argv[3])
        if not target or not target[2]:
            print("not a directory")
            return 1
        for name, child, is_d in iso.read_dir(target[0]):
            _ft, info_len, _ = iso.read_icb(child)
            print(f"{'<DIR>' if is_d else info_len:>12} {name}")
    elif cmd == "extract":
        return 0 if extract_file(iso, sys.argv[3], sys.argv[4]) else 1
    elif cmd == "diff":
        local_root = sys.argv[3]
        missing = 0
        total = 0
        for path, lba, size in iso.walk():
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

