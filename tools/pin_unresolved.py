#!/usr/bin/env python3
"""Bulk-pin scanner holes that codegen's own validation can see.

The runtime FATAL loop (tools/fix_holes.py) finds holes one interactive crash
at a time, but codegen's analysis phase already knows about a subset of them
for free: every direct branch from a discovered (or pinned) function body to
an address that is not a function is reported as an UnresolvedCall. Pinning a
thunk exposes its body, whose branches expose the next hop - so a few codegen
passes can drain a whole thunk chain that would otherwise cost one
crash + rebuild each.

This runs that cycle:

    1. rexglue -f codegen <manifest>   (capture full output)
    2. parse "UnresolvedCall 0xTARGET from 0xSITE" entries
    3. skip targets already pinned; stop if none are new
    4. pin each target in the manifest section its address range belongs to
       (entrypoint table entries are absolute TOML and append at EOF;
        module pins must go into [modules.functions] AFTER their [[modules]]
        element, so they are inserted before the next module's header)
    5. back to 1 (--passes)

Then build once with build.cmd - the caller does that; this script only pins
and re-analyses (analysis needs no emitted code, so no build in the loop).

Usage:
    python tools/pin_unresolved.py --passes 4
    python tools/pin_unresolved.py --dry-run
"""
import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "forzahorizon_manifest.toml")
REXGLUE = os.path.join(ROOT, "rexglue", "win-amd64", "bin", "rexglue.exe")

UNRESOLVED_RE = re.compile(
    r"^\s+0x([0-9A-Fa-f]+) from 0x([0-9A-Fa-f]+):")
PIN_ENTRY_RE = re.compile(r'^\[entrypoint\.functions\."0x([0-9A-Fa-f]+)"\]')
PIN_MODULE_RE = re.compile(r'^\[modules\.functions\."0x([0-9A-Fa-f]+)"\]')
MODULE_HEADER_RE = re.compile(r'^\[\[modules\]\]\s*$')
MODULE_NAME_RE = re.compile(r'^name\s*=\s*"([^"]+)"')

# Guest image ranges -> manifest pin target. Entrypoint pins are absolute
# TOML table headers and can go anywhere; module pins attach to the most
# recent [[modules]] element, so placement matters (see insert_point below).
RANGES = [
    (0x82000000, 0x84000000, "entrypoint"),
    (0x88000000, 0x89000000, "XMediaFacade_default"),
    (0x89000000, 0x8A000000, "SpeechFacade_default"),
]


def section_for(addr):
    for lo, hi, name in RANGES:
        if lo <= addr < hi:
            return name
    return "entrypoint"


def pinned_module_addresses():
    """module name -> set of pinned addresses ([modules.functions] blocks)."""
    out = {}
    current = None
    with open(MANIFEST, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            m = MODULE_HEADER_RE.match(line)
            if m:
                current = None  # name comes on a later line
                continue
            m = MODULE_NAME_RE.match(line)
            if m and current is None and line.startswith("name"):
                current = m.group(1)
                out.setdefault(current, set())
                continue
            m = PIN_MODULE_RE.match(line.strip())
            if m and current:
                out[current].add(int(m.group(1), 16))
            elif m:
                # [modules.functions] seen while current module unknown
                # (header already closed by a previous table) - track under
                # the last [[modules]] seen, best effort.
                pass
    return out


def pinned_entry_addresses():
    out = set()
    with open(MANIFEST, "r", encoding="utf-8") as fh:
        for line in fh:
            m = PIN_ENTRY_RE.match(line.strip())
            if m:
                out.add(int(m.group(1), 16))
    return out


def append_entry_pin(addr):
    with open(MANIFEST, "a", encoding="utf-8") as fh:
        fh.write("\n# auto-pinned by tools/pin_unresolved.py (codegen validation)"
                 "\n[entrypoint.functions.\"0x%08X\"]\nname = \"sub_%08X\"\n"
                 % (addr, addr))
    print(f"[pinned] 0x{addr:08X} -> [entrypoint.functions]")


def find_module_insert_line(module_name):
    """Line index BEFORE which a [modules.functions] pin for module_name
    must be inserted: the start of the NEXT module's block (or EOF)."""
    lines = open(MANIFEST, "r", encoding="utf-8").read().splitlines(keepends=True)
    current = None
    current_start = None
    for i, line in enumerate(lines):
        if MODULE_HEADER_RE.match(line.rstrip("\n")):
            current = None
            current_start = i
            continue
        m = MODULE_NAME_RE.match(line.strip())
        if m and current is None and current_start is not None:
            current = m.group(1)
            if current == module_name:
                # found our module; now find the next [[modules]] header (or
                # EOF) and insert before it (skipping back over its leading
                # comment block so comments stay attached to their module).
                j = i + 1
                while j < len(lines) and not MODULE_HEADER_RE.match(lines[j].rstrip("\n")):
                    j += 1
                k = j
                while k - 1 > i and lines[k - 1].lstrip().startswith("#"):
                    k -= 1
                return k
    return len(lines)


def append_module_pin(addr, module_name):
    idx = find_module_insert_line(module_name)
    lines = open(MANIFEST, "r", encoding="utf-8").read().splitlines(keepends=True)
    block = ("\n# auto-pinned by tools/pin_unresolved.py (codegen validation)"
             "\n[modules.functions.\"0x%08X\"]\nname = \"sub_%08X\"\n"
             % (addr, addr))
    if idx >= len(lines):
        lines.append(block)
    else:
        lines.insert(idx, block)
    with open(MANIFEST, "w", encoding="utf-8", newline="") as fh:
        fh.writelines(lines)
    print(f"[pinned] 0x{addr:08X} -> [modules.functions] ({module_name})")


def pin(addr, dry_run):
    section = section_for(addr)
    if dry_run:
        print(f"[dry-run] would pin 0x{addr:08X} ({section})")
        return
    if section == "entrypoint":
        append_entry_pin(addr)
    else:
        append_module_pin(addr, section)


def run_codegen():
    print("--- codegen (analysis + emit) ---", flush=True)
    res = subprocess.run([REXGLUE, "-f", "codegen", MANIFEST], cwd=ROOT,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    text = res.stdout.decode("utf-8", "replace")
    # Keep the interesting lines visible, drop per-function noise.
    for line in text.splitlines():
        if any(k in line for k in ("UnresolvedCall", "ANALYSIS ERRORS",
                                   "Total:", "Codegen summary",
                                   "Validation failed", "error]", "FATAL")):
            print("   " + line.strip())
    return res.returncode, text


def unresolved_targets(text):
    """Ordered unique (target, site) pairs from the UnresolvedCall block(s)."""
    pairs = []
    seen = set()
    in_block = False
    for line in text.splitlines():
        if "UnresolvedCall" in line and ":" in line and "from" not in line:
            in_block = True
            continue
        if in_block:
            m = UNRESOLVED_RE.match(line)
            if not m:
                if line.strip() and "from" not in line:
                    in_block = False
                continue
            t = int(m.group(1), 16)
            s = int(m.group(2), 16)
            if t not in seen:
                seen.add(t)
                pairs.append((t, s))
    return pairs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--passes", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(REXGLUE):
        sys.exit(f"rexglue not found at {REXGLUE}")

    total = 0
    for p in range(1, args.passes + 1):
        print(f"\n=========== pass {p}/{args.passes} ===========", flush=True)
        rc, text = run_codegen()
        if rc != 0 and "UnresolvedCall" not in text:
            print(f"codegen FAILED (rc={rc}) without unresolved calls")
            return 1

        pairs = unresolved_targets(text)
        if not pairs:
            print("Validation clean - no unresolved calls. Done!")
            break

        entry_pins = pinned_entry_addresses()
        mod_pins = pinned_module_addresses()
        new = []
        for t, s in pairs:
            sec = section_for(t)
            known = (t in entry_pins if sec == "entrypoint"
                     else t in mod_pins.get(sec, set()))
            if not known and t >= 0x80000000:
                new.append((t, s))
            elif known:
                print(f"[skip]   0x{t:08X} already pinned but still unresolved")
            else:
                print(f"[skip]   0x{t:08X} out of known ranges / null")

        if not new:
            print("No NEW pins available (all targets pinned or ignorable). "
                  "If any 'already pinned' lines printed above, codegen still "
                  "rejects them - investigate by hand.")
            break

        for t, s in new:
            print(f"[hole]   0x{t:08X} (from 0x{s:08X}, {section_for(t)})")
        if args.dry_run:
            print(f"[dry-run] would pin {len(new)} address(es); rerun without "
                  "--dry-run")
            return 0
        for t, s in new:
            pin(t, args.dry_run)
        total += len(new)

    print(f"\n{total} new pin(s) across this invocation. "
          "Now build: build.cmd forzahorizon")
    return 0


if __name__ == "__main__":
    sys.exit(main())
