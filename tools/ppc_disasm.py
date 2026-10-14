#!/usr/bin/env python3
"""Disassemble PowerPC code from the decrypted Xbox 360 basefile.

Usage: python tools/ppc_disasm.py <guest_addr_hex> [count]
The basefile maps guest VA 0x82000000 -> file offset 0.
"""
import sys
from capstone import Cs, CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN

BASE = 0x82000000
BASEFILE = "tools/xexdump/default_base.bin"


def main() -> int:
    addr = int(sys.argv[1], 16)
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 150
    with open(BASEFILE, "rb") as f:
        data = f.read()
    off = addr - BASE
    if off < 0 or off + 4 > len(data):
        print(f"address {addr:08X} outside basefile")
        return 1
    md = Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN)
    md.skipdata = True
    code = data[off : off + count * 4]
    printed = 0
    for i in md.disasm(code, addr):
        print(f"{i.address:08X}: {i.bytes.hex():<8}  {i.mnemonic:<8} {i.op_str}")
        printed += 1
        if printed >= count:
            break
    else:
        # resume past any skipped data
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
