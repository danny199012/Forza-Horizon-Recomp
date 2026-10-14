#!/usr/bin/env python3
"""STFS (CON/LIVE/PIRS) package extractor for Xbox 360 content packages.

Mirrors rexglue's StfsContainerDevice parsing so extracted folders match
what the runtime's content manager expects.

Install a DLC pack into the runtime's content tree:

  python tools/stfs_extract.py <package-file> <content-root>

where <content-root> is the runtime's user data root (the folder holding
the per-xuid save folders, e.g. Documents\\forzahorizon). The destination
<content-root>/0000000000000000/<title-id>/00000002/<content-id>/ is
derived from the package path (No-Intro layout).

Batch mode: pass the No-Intro DLC directory instead of a single file.
"""
import struct
import sys
import os

BLOCK = 0x1000
BPH = [170, 28900, 4913000]      # kBlocksPerHashLevel
END_OF_CHAIN = 0xFFFFFF
ENTRIES_PER_DIR_BLOCK = BLOCK // 0x40  # StfsDirectoryEntry is 0x40 bytes


def u24le(b):
    return b[0] | (b[1] << 8) | (b[2] << 16)


class Stfs:
    def __init__(self, path):
        self.f = open(path, "rb")
        head = self.f.read(0x400)
        if head[0:4] not in (b"CON ", b"LIVE", b"PIRS"):
            raise ValueError(f"not an STFS package (magic {head[0:4]!r})")
        # XContentHeader (0x344) + XContentMetadata: the StfsVolumeDescriptor
        # is a metadata member at a FIXED offset 0x35 into the metadata
        # (= file offset 0x379), independent of header_size.
        vd = head[0x379 : 0x379 + 0x24]
        if vd[0] != 0x24:
            raise ValueError(f"unexpected volume descriptor length {vd[0]}")
        self.header_size = struct.unpack(">I", head[0x340:0x344])[0]
        self.read_only = bool(vd[2] & 1)
        self.root_active = bool(vd[2] & 2)
        self.file_table_block_count = struct.unpack(">H", vd[3:5])[0]
        self.file_table_block = u24le(vd[5:8])
        self.total_blocks = struct.unpack(">I", vd[0x1C:0x20])[0]
        self.bph = 1 if self.read_only else 2
        self.block_step = (BPH[0] + self.bph,
                           BPH[1] + ((BPH[0] + 1) * self.bph))
        self.data_base = (self.header_size + BLOCK - 1) // BLOCK * BLOCK
        # License table: 16 entries at 0x20C, each 0x10 bytes:
        # licensee_id u64 BE, license_bits u32 BE, license_flags u32 BE.
        self.license_mask = 0
        for i in range(16):
            base = 0x20C + i * 0x10
            bits, flg = struct.unpack(">II", head[base + 8 : base + 16])
            if flg:
                self.license_mask |= bits
        self._hash_cache = {}

    def block_to_offset(self, block_index):
        base = BPH[0]
        block = block_index
        for _ in range(3):
            block += ((block_index + base) // base) * self.bph
            if block_index < base:
                break
            base *= BPH[0]
        return self.data_base + (block << 12)

    def hash_block_number(self, block_index, level):
        if level == 0:
            if block_index < BPH[0]:
                return 0
            block = (block_index // BPH[0]) * self.block_step[0]
            block += ((block_index // BPH[1]) + 1) * self.bph
            if block_index < BPH[1]:
                return block
            return block + self.bph
        if level == 1:
            if block_index < BPH[1]:
                return self.block_step[0]
            block = (block_index // BPH[1]) * self.block_step[1]
            return block + self.bph
        return self.block_step[1]

    def get_block_hash(self, block_index):
        """Returns the level0 next-block number for a data block."""
        table_off = self.data_base + (self.hash_block_number(block_index, 0) << 12)
        table = self._hash_cache.get(table_off)
        if table is None:
            self.f.seek(table_off)
            table = self.f.read(BLOCK)
            self._hash_cache[table_off] = table
        record = (block_index % BPH[0]) * 0x18
        info = struct.unpack(">I", table[record + 0x14 : record + 0x18])[0]
        return info & 0xFFFFFF

    def read_block(self, block_index):
        self.f.seek(self.block_to_offset(block_index))
        return self.f.read(BLOCK)

    def read_directory_tree(self):
        """Returns entries: (parent_ordinal, name, is_dir, size, start_block)."""
        entries = []
        table_block = self.file_table_block
        for _ in range(self.file_table_block_count):
            self.f.seek(self.block_to_offset(table_block))
            directory = self.f.read(BLOCK)
            for m in range(ENTRIES_PER_DIR_BLOCK):
                off = m * 0x40
                ent = directory[off : off + 0x40]
                if ent[0] == 0:
                    break
                name_len = ent[0x28] & 0x3F
                is_dir = bool(ent[0x28] & 0x80)
                name = ent[0 : name_len].decode("latin-1")
                size = struct.unpack(">I", ent[0x34 : 0x38])[0]
                start = u24le(ent[0x2F : 0x32])
                parent_index = struct.unpack(">H", ent[0x32 : 0x34])[0]
                entries.append((parent_index, name, is_dir, size, start))
            table_block = self.get_block_hash(table_block)
            if table_block == END_OF_CHAIN:
                break
        return entries

    def extract(self, dest):
        entries = self.read_directory_tree()
        count = 0
        for ordinal, (parent, name, is_dir, size, start) in enumerate(entries):
            if is_dir:
                continue
            parts = [name]
            idx = parent
            while idx != 0xFFFF and idx < len(entries):
                p, pname, _, _, _ = entries[idx]
                parts.append(pname)
                idx = p
            rel = os.path.join(*reversed(parts))
            out = os.path.join(dest, rel)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "wb") as w:
                remaining = size
                block = start
                while remaining > 0 and block != END_OF_CHAIN:
                    data = self.read_block(block)
                    take = min(BLOCK, remaining)
                    w.write(data[:take])
                    remaining -= take
                    block = self.get_block_hash(block)
            count += 1
        return count


def find_packages(root):
    """Yields (package_file, content_id) for No-Intro style DLC trees.

    Both layouts are handled: .../00000002/<id>/<id> and
    .../00000002/<id-file>.
    """
    known_types = {"00000001", "00000002", "00000003", "00000004",
                   "00000005", "00040000", "00007000", "000B0000",
                   "000C0000", "000D0000", "000E0000", "000F0000"}
    for dirpath, dirs, files in os.walk(root):
        parent = os.path.basename(dirpath)
        for fn in files:
            if len(fn) not in (40, 42) or not all(c in "0123456789ABCDEFabcdef" for c in fn):
                continue
            if parent == fn or parent in known_types:
                yield os.path.join(dirpath, fn), fn


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    src, dest_root = sys.argv[1], sys.argv[2]
    packages = list(find_packages(src)) if os.path.isdir(src) else [(src, None)]
    if not packages:
        print("no STFS packages found under", src)
        return 1

    for path, content_id in packages:
        try:
            stfs = Stfs(path)
        except ValueError as e:
            print(f"skip {os.path.basename(path)}: {e}")
            continue
        # Title id + content type come from the No-Intro directory layout.
        # Two shapes exist: .../4D5309C9/00000002/<id-file> and
        # .../4D5309C9/00000002/<id-dir>/<id-file>. Find the content-type
        # folder (known 360 content types) walking up; the title id is the
        # component directly above it.
        abspath = os.path.abspath(path)
        comps = []
        d = os.path.dirname(abspath)
        for _ in range(8):
            comps.append(os.path.basename(d))
            d = os.path.dirname(d)
        known_types = {"00000001", "00000002", "00000003", "00000004",
                       "00000005", "00040000", "00007000", "000B0000",
                       "000C0000", "000D0000", "000E0000", "000F0000"}
        ctype = next((c for c in comps if c in known_types), None)
        if ctype is None:
            print(f"skip {path}: no content-type folder in path")
            continue
        ci = comps.index(ctype)
        title_dir = comps[ci + 1] if ci + 1 < len(comps) else ""
        if len(title_dir) != 8 or not all(c in "0123456789ABCDEFabcdef" for c in title_dir):
            print(f"skip {path}: no title id folder in path")
            continue
        title_id = int(title_dir, 16)
        if content_id is None:
            # File inside a content-id dir -> use that dir; file directly
            # under the type dir -> the file name is the content id.
            content_id = comps[0] if ci > 0 else os.path.splitext(os.path.basename(path))[0]
        if content_id is None:
            content_id = os.path.splitext(os.path.basename(path))[0]
        dest = os.path.join(dest_root, "0000000000000000",
                            f"{title_id:08X}", ctype, content_id)
        print(f"installing {content_id} -> {dest}")
        os.makedirs(dest, exist_ok=True)
        n = stfs.extract(dest)
        print(f"   {n} files, license mask 0x{stfs.license_mask:08X}, "
              f"{'read-only' if stfs.read_only else 'resilient'} format")
    return 0


if __name__ == "__main__":
    sys.exit(main())

