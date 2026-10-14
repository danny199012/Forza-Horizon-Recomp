#!/usr/bin/env python3
"""Filter the bulk-pinned thunk list: drop pins that are inline dispatch
tails instead of standalone thunks.

A vtable-referenced standalone thunk is placed after a function END: its
linear predecessor is an unconditional transfer (b/blr/bctr), padding, or
data. An INLINE dispatch tail is entered by fallthrough from ordinary
instructions (e.g. 'beq -> fallthrough -> dispatch tail'), and pinning it
splits the enclosing emitted function -> runtime
REX_FATAL("Unresolved branch ...").

Keep rule: predecessor word at P-4 is
  * any branch opcode (top 6 bits 18 or 19 -> first byte 0x48..0x4F), or
  * 0x60000000 (nop) / 0x00000000 padding, or
  * not decodable as a 4-byte PPC instruction (constant pool / data).

Usage:  python tools/filter_thunk_pins.py
"""
import glob
import os
import re
import struct
import sys

import capstone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "forzahorizon_manifest.toml")
BASEFILE = os.path.join(ROOT, "tools", "xexdump", "default_base.bin")
BASE = 0x82000000

BULK_HEADER = "# --- Bulk-pinned vtable dispatch thunks (tools/pin_thunks.py) ---"
PIN_RE = re.compile(r'^\[entrypoint\.functions\."0x([0-9A-Fa-f]+)"\]', re.M)
SETFUNC_RE = re.compile(r"SetFunction\(0x([0-9A-Fa-f]+)")

md = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_32 | capstone.CS_MODE_BIG_ENDIAN)


def standalone(data, off):
    """True if the word before off ends the previous code flow."""
    if off < 4:
        return False
    prev = struct.unpack_from(">I", data, off - 4)[0]
    top = prev >> 26
    if 18 <= top <= 19:          # b/bl/ba/bla, bclr/bcctr group (incl. blr/bctr)
        return True
    if prev in (0x60000000, 0x00000000):  # nop / zero padding
        return True
    if prev >> 2 == 0x1998F001 >> 2:      # unreachable, kept for clarity
        return True
    ins = next(md.disasm(data[off - 4:off], BASE + off - 4), None)
    if ins is None or ins.size != 4:
        return True               # data / constant pool
    return False


def main():
    text = open(MANIFEST, encoding="utf-8").read()
    idx = text.find(BULK_HEADER)
    if idx < 0:
        sys.exit("no bulk-pin block found in manifest")
    head, block = text[:idx], text[idx:]

    bulk = sorted({int(m.group(1), 16) for m in PIN_RE.finditer(block)})
    data = open(BASEFILE, "rb").read()
    print(f"bulk pins: {len(bulk)}")

    keep, drop = [], []
    for p in bulk:
        (keep if standalone(data, p - BASE) else drop).append(p)

    print(f"standalone (keep): {len(keep)}, inline tail (drop): {len(drop)}")
    for a in drop[:30]:
        print(f"  drop 0x{a:08X}")
    if len(drop) > 30:
        print(f"  ... and {len(drop) - 30} more")

    new_block = (BULK_HEADER + "\n"
                 "# Every 'lwz r11,0(r3) ... mtctr r11; bctr' stub in the entrypoint image\n"
                 "# the scanner failed to emit (reachable only via vtables), filtered by\n"
                 "# tools/filter_thunk_pins.py: a pin is kept only when its linear\n"
                 "# predecessor ends the previous code flow (unconditional branch, padding\n"
                 "# or data); anything entered by fallthrough is an inline dispatch tail\n"
                 "# of an emitted function and pinning it would split that function.\n")
    for a in keep:
        new_block += '[entrypoint.functions."0x%08X"]\nname = "sub_%08X"\n' % (a, a)
    open(MANIFEST, "w", encoding="utf-8", newline="").write(head + new_block)
    print(f"manifest rewritten with {len(keep)} bulk pins")
    return 0


if __name__ == "__main__":
    sys.exit(main())
