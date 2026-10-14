#!/usr/bin/env python3
"""Bulk-pin every vtable dispatch thunk the scanner missed.

The default.xex is full of 4-6 instruction vtable dispatch stubs:

    lwz r11, 0(r3)          ; 81630000  load vtable ptr
    lwz r11, slot(r11)      ; 816bNNNN  load function pointer
    [optional reg setup]
    mtctr r11               ; 7d6903a6
    bctr                    ; 4e800420

The recompiler's scanner misses a subset of them (they are only reachable
through vtables, never via direct branches), which is what produced the long
tail of "Call to invalid or unregistered function" fatals.

This dumps the decrypted basefile (xextool -b), finds every such stub in the
entrypoint image, subtracts the ones codegen already emits, and appends pins
for the rest to the manifest. Two adjacent exact 32-bit magic words make
false positives in data effectively impossible.

Usage:
    python tools/pin_thunks.py            # pin everything missed
    python tools/pin_thunks.py --dry-run  # report only
"""
import argparse
import glob
import os
import re
import struct
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "forzahorizon_manifest.toml")
BASEFILE = os.path.join(ROOT, "tools", "xexdump", "default_base.bin")
XEX = os.path.join(ROOT, "Forza Horizon", "default.xex")
XEXTOOL = r"C:\Users\cuz_c\Downloads\iso2god-v1.6.0\xextool.exe"
BASE, SIZE = 0x82000000, 0x1620000

PIN_ENTRY_RE = re.compile(r'^\[entrypoint\.functions\."0x([0-9A-Fa-f]+)"\]', re.M)
SETFUNC_RE = re.compile(r"SetFunction\(0x([0-9A-Fa-f]+)")

MTCTR_R11, BCTR = 0x7D6903A6, 0x4E800420  # mtctr r11 + bctr tail


def registered_addresses():
    reg = set()
    for path in glob.glob(os.path.join(ROOT, "generated", "default", "*register*.cpp")):
        for m in SETFUNC_RE.finditer(open(path, encoding="utf-8", errors="replace").read()):
            reg.add(int(m.group(1), 16))
    return reg


def pinned_addresses():
    if not os.path.exists(MANIFEST):
        return set()
    return {int(m.group(1), 16)
            for m in PIN_ENTRY_RE.finditer(open(MANIFEST, encoding="utf-8").read())}


def find_thunks():
    """Find vtable dispatch stubs of any shape: straight-line code starting
    'lwz rX, 0(r3)' (rX in r10/r11/r12 - thunks use either), containing a
    'lwz rX, slot(rX)' load, ending 'mtctr rX; bctr', no control flow in
    between. Variants interleave 0-8 parameter-setup instructions."""
    data = open(BASEFILE, "rb").read()
    n = len(data) // 4
    words = struct.unpack_from(f">{n}I", data, 0)
    stubs = []
    for i in range(0, n - 13):
        w0 = words[i]
        # lwz r10/r11/r12, 0(r3)
        if w0 not in (0x81430000, 0x81630000, 0x81830000):
            continue
        rx = (w0 >> 21) & 31
        slot_top16 = 0x8000 | (rx << 5) | rx  # lwz rX, disp(rX) top half
        mtctr = 0x7C0903A6 | (rx << 21)       # mtctr rX (empirical: r10/r11/r12)
        saw_slot = False
        ok = False
        for j in range(i + 1, i + 13):
            w = words[j]
            if w >> 26 in (16, 17, 18, 19):  # any control flow -> not a stub
                break
            if w >> 16 == slot_top16:        # lwz rX, slot(rX)
                saw_slot = True
            if w == mtctr:
                if j + 1 < n and words[j + 1] == BCTR and saw_slot:
                    ok = True
                break
        if ok:
            stubs.append(BASE + i * 4)
    return stubs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(BASEFILE):
        print("basefile missing - dumping with xextool...")
        os.makedirs(os.path.dirname(BASEFILE), exist_ok=True)
        res = subprocess.run([XEXTOOL, "-b", BASEFILE, XEX],
                             capture_output=True, text=True)
        if not os.path.exists(BASEFILE):
            sys.exit(f"xextool dump failed:\n{res.stdout}\n{res.stderr}")

    stubs = find_thunks()
    reg = registered_addresses()
    pinned = pinned_addresses()
    missed = [a for a in stubs if a not in reg and a not in pinned]
    print(f"thunk stubs total: {len(stubs)}  (registered: "
          f"{sum(1 for a in stubs if a in reg)}, pinned: "
          f"{sum(1 for a in stubs if a in pinned)}, missed: {len(missed)})")

    if args.dry_run or not missed:
        for a in missed[:20]:
            print(f"  missed 0x{a:08X}")
        if len(missed) > 20:
            print(f"  ... and {len(missed) - 20} more")
        return 0

    with open(MANIFEST, "a", encoding="utf-8") as fh:
        fh.write("\n\n# --- Bulk-pinned vtable dispatch thunks (tools/pin_thunks.py) ---\n"
                 "# Every 'lwz r11,0(r3) ... mtctr r11; bctr' stub in the entrypoint image\n"
                 "# the scanner failed to emit (reachable only via vtables). Signature found\n"
                 "# by disassembling the decrypted basefile; same shape as the manually\n"
                 "# pinned rounds 6-19. Addresses already emitted or pinned are excluded.\n")
        for a in sorted(missed):
            fh.write('[entrypoint.functions."0x%08X"]\nname = "sub_%08X"\n' % (a, a))
    print(f"[pinned] {len(missed)} thunk stubs -> [entrypoint.functions]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
