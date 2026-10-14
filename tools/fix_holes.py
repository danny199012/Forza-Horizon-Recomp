#!/usr/bin/env python3
"""Drive the pin -> codegen -> build -> run loop until the game stops crashing.

The ReXGlue recompiler misses a scattering of thin thunk functions, and the
only reliable way to find each one is to run the game and read the address out
of the [FATAL] line. That is slow by hand: each round is a ~3 min codegen of
the 16 MB XEX plus a link, and the crash you are chasing may not even be the
next one.

This automates that loop:

    1. launch the game headless for --seconds
    2. read the newest [FATAL] guest address from its log
    3. if already pinned, stop and say why (pinning will not help)
    4. otherwise append a pinned entry to forzahorizon_manifest.toml,
       choosing the section from the module whose code range contains
       the address (entrypoint vs XMediaFacade_default)
    5. run codegen, then build, then go back to 1

Each round is one codegen + one incremental build, the minimum possible. It
stops on --rounds, on a clean run, or when a pinned address still faults.

Usage:
    python tools/fix_holes.py --rounds 5
    python tools/fix_holes.py --dry-run     # report only, change nothing
"""
import argparse
import glob
import os
import re
import subprocess
import sys
import time

FATAL_RE = re.compile(
    r"Call to invalid or unregistered function at guest address 0x([0-9A-Fa-f]+)")
REGISTER_RE = re.compile(r"SetFunction\(0x([0-9A-Fa-f]+),")
MODULE_RANGE_RE = re.compile(
    r"Function table initialized for module: code=([0-9A-Fa-f]+)-([0-9A-Fa-f]+)")
PIN_ENTRY_RE = re.compile(r'^\[entrypoint\.functions\."0x([0-9A-Fa-f]+)"\]')
PIN_MODULE_RE = re.compile(r'^\[modules\.functions\."0x([0-9A-Fa-f]+)"\]')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "forzahorizon_manifest.toml")
REXGLUE = os.path.join(ROOT, "rexglue", "win-amd64", "bin", "rexglue.exe")


def pinned_addresses():
    """Addresses already pinned in the manifest, so we never duplicate one."""
    out = set()
    if not os.path.exists(MANIFEST):
        return out
    with open(MANIFEST, "r", encoding="utf-8") as fh:
        for line in fh:
            for pat in (PIN_ENTRY_RE, PIN_MODULE_RE):
                m = pat.match(line.strip())
                if m:
                    out.add(int(m.group(1), 16))
    return out


def registered_addresses():
    addrs = set()
    for path in glob.glob(os.path.join(ROOT, "generated", "**", "*register*.cpp"),
                          recursive=True):
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = REGISTER_RE.search(line)
                if m:
                    addrs.add(int(m.group(1), 16))
    return addrs


def module_ranges(log_text):
    """Map 'code_lo-code_hi' ranges from the run log to a pin section name.

    Entrypoint ranges go to [entrypoint.functions], anything else (guest
    modules loaded via XexLoadImage) to [modules.functions].
    """
    ranges = []
    for m in MODULE_RANGE_RE.finditer(log_text):
        lo = int(m.group(1), 16)
        hi = int(m.group(2), 16)
        # The entrypoint is the module based at 0x82000000; guest DLLs land
        # in the 0x88xxxxxx region.
        section = "entrypoint" if lo < 0x84000000 else "modules"
        ranges.append((lo, hi, section))
    return ranges


def section_for(addr, ranges):
    for lo, hi, section in ranges:
        if lo <= addr <= hi:
            return section
    # Unknown address: default to the entrypoint table, which is where calls
    # outside any loaded module range would still resolve.
    return "entrypoint"


def newest_log(config):
    logs = glob.glob(os.path.join(ROOT, "out", "build", config, "logs", "*.log"))
    return max(logs, key=os.path.getmtime) if logs else None


def run_and_get_fatal(config, game_root, seconds):
    """Launch the game headless; return (fatal_address, log_text or None)."""
    build_dir = os.path.join(ROOT, "out", "build", config)
    exe = os.path.join(build_dir, "forzahorizon.exe")
    if not os.path.exists(exe):
        sys.exit(f"{exe} not found - build first (build.cmd forzahorizon)")

    log_dir = os.path.join(build_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    for stale in glob.glob(os.path.join(log_dir, "*.log")):
        try:
            os.remove(stale)
        except PermissionError:
            # A leftover process (or an indexer) still holds the file; the
            # newest-log lookup below may then pick a stale file, so keep
            # going but note it.
            print(f"[warn] could not remove stale log {stale}")

    proc = subprocess.Popen(
        [exe, "--game_data_root", game_root, "--headless",
         "--gpu_plugin", "xenos"],
        cwd=build_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    deadline = time.time() + seconds
    addr = None
    log_text = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            break
        # Crash out as soon as a FATAL lands rather than idling the full
        # window - otherwise every round costs the full --seconds.
        path = newest_log(config)
        if path:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    log_text = fh.read()
                hits = FATAL_RE.findall(log_text)
                if hits:
                    addr = int(hits[-1], 16)
                    break
            except OSError:
                pass
        time.sleep(1)

    if proc.poll() is None:
        proc.kill()
        proc.wait()

    # Always re-read the log once the process is gone. When the game crashes
    # it exits almost immediately, so the polling loop above usually breaks on
    # proc.poll() before it ever sees the FATAL line - without this final read
    # every crash would be misreported as "the run stayed clean".
    path = newest_log(config)
    if path:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                log_text = fh.read()
            hits = FATAL_RE.findall(log_text)
            if hits:
                addr = int(hits[-1], 16)
        except OSError:
            pass
    return addr, log_text


def pin(address, section, dry_run):
    key = "entrypoint.functions" if section == "entrypoint" else "modules.functions"
    entry = ("\n# auto-pinned by tools/fix_holes.py"
             "\n[%s.\"0x%08X\"]\nname = \"sub_%08X\"\n" % (key, address, address))
    if dry_run:
        print("[dry-run] would append:\n" + entry)
        return True
    with open(MANIFEST, "a", encoding="utf-8") as fh:
        fh.write(entry)
    print(f"[pinned] 0x{address:08X} -> [{key}]")
    return True


def preset_flag(config):
    """build.cmd preset selector for a cmake preset name ('' = its default)."""
    if config == "win-amd64-debug":
        return ""  # debug is build.cmd's default preset
    return "-" + config.replace("win-amd64-", "")


def sh(args, label):
    print(f"--- {label} ---", flush=True)
    res = subprocess.run(args, cwd=ROOT, shell=False,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for line in res.stdout.decode("utf-8", "replace").strip().splitlines()[-5:]:
        print("   " + line)
    return res.returncode


def run_build(flag):
    # Invoke build.cmd by RELATIVE path (sh() already runs with cwd=ROOT).
    # Passing the absolute path through cmd /c hits two quoting layers (the
    # project path has spaces) and cmd mangles both: either "'E:\Xbox' is not
    # recognized" or "The network path was not found".
    args = ["cmd", "/c", "build.cmd"]
    if flag:
        args.append(flag)
    args.append("forzahorizon")
    return sh(args, "build")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=5,
                    help="max pin/build/run cycles (default 5)")
    ap.add_argument("--seconds", type=int, default=120,
                    help="max seconds to let each run live (default 120)")
    ap.add_argument("--config", default="win-amd64-debug",
                    help="build dir to run (default win-amd64-debug)")
    ap.add_argument("--game-root", default=os.path.join(ROOT, "Forza Horizon"),
                    help="game content dir (default ./Forza Horizon)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report the next address but change nothing")
    args = ap.parse_args()

    if not os.path.exists(REXGLUE):
        sys.exit(f"rexglue not found at {REXGLUE}")

    for rnd in range(1, args.rounds + 1):
        print(f"\n=========== round {rnd}/{args.rounds} ===========", flush=True)
        addr, log_text = run_and_get_fatal(args.config, args.game_root, args.seconds)

        if addr is None:
            print("No FATAL - the run stayed clean. Done!")
            return 0

        print(f"[FATAL] guest address 0x{addr:08X}")

        if addr in pinned_addresses():
            reg = registered_addresses()
            if addr not in reg:
                # Pinned in the manifest but not in the generated table: the
                # edit landed after the last codegen. Build it in and retry
                # instead of treating it as an unfixable crash.
                print(f"0x{addr:08X} is pinned but not generated yet - "
                      "running codegen + build to catch up.")
                if args.dry_run:
                    return 0
                if sh([REXGLUE, "-f", "codegen", MANIFEST], "codegen") != 0:
                    print("codegen FAILED")
                    return 1
                if run_build(preset_flag(args.config)) != 0:
                    print("build FAILED")
                    return 1
                continue
            print(f"0x{addr:08X} is pinned AND generated but still faulting.")
            print("Pinning is not the fix here - inspect it by hand.")
            return 1

        reg = registered_addresses()
        if addr in reg:
            print(f"0x{addr:08X} IS in the generated table but faulting - "
                  "this is not a scanner hole; investigate manually.")
            return 1

        if args.dry_run:
            print(f"[dry-run] would pin 0x{addr:08X} "
                  f"({section_for(addr, module_ranges(log_text))})")
            return 0

        pin(addr, section_for(addr, module_ranges(log_text)), args.dry_run)
        if sh([REXGLUE, "-f", "codegen", MANIFEST], "codegen") != 0:
            print("codegen FAILED")
            return 1
        if run_build(preset_flag(args.config)) != 0:
            print("build FAILED")
            return 1

    print(f"\n{args.rounds} rounds used up - rerun to keep going.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
