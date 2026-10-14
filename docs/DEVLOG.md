# Forza Horizon (Xbox 360) — ReXGlue Static Recomp

A static recompilation of **Forza Horizon** (2012) for Xbox 360 using the
[ReXGlue SDK](https://github.com/rexglue/rexglue-sdk) v0.10.0. Guest PowerPC
code is translated to C++ at build time by `rexglue codegen`, driven by
`forzahorizon_manifest.toml`, and executed natively on Windows.

## Layout

| Path | What it is |
|---|---|
| `Forza Horizon/` | Game content (redump): `default.xex`, `XMediaFacade_default.xex`, `media/` (2385 files), NXE facades, `$SystemUpdate/` |
| `rexglue/win-amd64/` | ReXGlue SDK (prebuilt): `rexglue.exe` toolchain + headers/libs |
| `forzahorizon_manifest.toml` | Recomp manifest: entrypoint, modules, pinned functions |
| `generated/` | Codegen output — **do not edit**, regenerated every build |
| `src/` | Host app: `main.cpp` (crash handlers), `forzahorizon_app.h` (`ForzaHorizonApp`) |
| `out/build/` | Build trees (`win-amd64-debug`, `win-amd64-release`, `win-amd64-perf`) |
| `tools/fix_holes.py` | Automated pin → codegen → build → run loop for scanner-missed functions |
| `tools/pin_unresolved.py` | Bulk-pins the `UnresolvedCall` targets codegen validation reports, until validation is clean |
| `tools/pin_thunks.py` | Scans the decrypted basefile for vtable dispatch stubs the scanner missed and pins them |
| `tools/filter_thunk_pins.py` | Drops thunk pins that would split real functions (inline dispatch tails) |

## The two-image problem

Like TDU2, Forza Horizon is **not** a single-image game, but the split is
smaller:

- `default.xex` (16 MB of code, image `0x82000000–0x83620000`) is the game.
- The game `XexLoadImage`s **`XMediaFacade_default.xex`** from the game root
  during early startup (media/music facade). Without it declared as a module,
  the first call into facade code dies with:

  ```
  [error] [cpu] Execute(88050800): function not in function table
  [critical] [core] [FATAL] Call to invalid or unregistered function at guest address 0x88050388
  ```

Both are registered in `forzahorizon_manifest.toml`: `default.xex` as
`[entrypoint]` and `XMediaFacade_default.xex` as a `[[modules]]` entry. The
runtime loads the facade at `0x88000000+`, which is why fatal addresses there
need pins in `[modules.functions]` while everything in `0x82xxxxxx` goes to
`[entrypoint.functions]`.

`SpeechFacade_default.xex` (Kinect speech) exists in the dump but is not
loaded during startup — add it as another `[[modules]]` if a future fatal
lands in its range.

## Building

Requires **clang**, **CMake ≥ 3.25**, and **Ninja**. Plain MSVC `cl` cannot
compile the generated code (the SDK headers use clang builtins).

```
build.cmd                    codegen only (regenerates C++ from the XEXs)
build.cmd forzahorizon       build the executable (debug)
build.cmd -perf forzahorizon Release + LTO — much faster at runtime; use to play
```

Output: `out/build/win-amd64-debug/forzahorizon.exe`, alongside the staged
`rexruntimed.dll`, `rexgpu-xenosd.dll` (the Xenos GPU emulator — without it
there is no graphics at all) and `forzahorizon_XMediaFacade_default.dll` (the
recompiled guest module).

First codegen of the 16 MB XEX takes ~2.5 min and the first build compiles
~240 translation units; after that both are incremental.

## Running

The game content must be pointed at explicitly, and the GPU plugin flag is
required or the game runs with no graphics at all. **`play.cmd`** (project
root) does exactly that — double-click it to play:

```
play.cmd
```

which is equivalent to:

```
out\build\win-amd64-debug\forzahorizon.exe --game_data_root "..\..\..\Forza Horizon" --gpu_plugin xenos
```

Useful flags: `--headless` (no window), `--log_level debug`, `--resolution 720p`.
Runtime logs land in `out/build/<preset>/logs/`.

### Window size & DPI (all values are pixels)

`window_width`/`window_height` are **physical pixels** on Windows (SDL3 runs
the process per-monitor-v2 DPI-aware; SDK patch 12). They are NOT multiplied
by the display scale — a 4K panel at 200% scaling and `window_width = 3840`
gives an exactly-3840-pixel window. The auto path ("the auto method" that
fixed the same zoom in the TDU2 project): leave `window_width`/`window_height`
unset and the window sizes itself from `video_mode_width`/`video_mode_height`,
or from the `resolution` preset (`720p`/`1080p`/`1440p`/`4k`/`WxH`) when
those are unset too. The guest video mode (`video_mode_*`, default 1280×720)
is what the kernel reports to the game and is independent of the window; the
presenter scales the guest frame to the window (stretch, or letterbox with
`present_letterbox = true`).

## The pin loop (scanner holes)

The recompiler's scanner misses thin thunk functions (vtable dispatch stubs
with no prologue to anchor on). The game runs until it calls one, then aborts
with `Call to invalid or unregistered function at guest address 0x…`. Each
hole is fixed by pinning the address in the manifest, which forces codegen to
emit its body:

```toml
[entrypoint.functions."0x82B1ABD0"]     # or [modules.functions."0x88…"]
name = "sub_82B1ABD0"
```

`tools/fix_holes.py` automates the whole cycle — run, read the FATAL address
from the log, pick the right manifest section by address range, pin, codegen,
build, repeat:

```
python tools/fix_holes.py --rounds 6 --seconds 90
python tools/fix_holes.py --dry-run      # report only, change nothing
```

Expect a long tail of these (the TDU2 project accumulated 40+ pins); opening
more of the game (menus, races, streaming) surfaces more.

## Status

- Project bootstrapped with `rexglue init`; codegen clean.
- Executable builds and boots the guest: kernel init, VFS mount of `game:\`,
  input driver (DualSense works; `--mnk_mode` enables keyboard with
  Enter = Start), XAudio endpoint, **Xenos GPU emulation live on D3D12**
  (shader translation, pipeline creation), and the XMediaFacade guest module
  (3197 functions).
- **The FMV intro renders and plays** (dashboard scene, ~60s in).
- **Press-start → main menu transition works** (SDK patch 3: fiber-backed
  `KeSetCurrentStackPointers`), and the game runs past the main menu.
- 218 functions pinned total: 52 individually (16 found by codegen
  validation, 13 by `tools/fix_holes.py`, 23 across the post-FMV task-system
  / front-end / race-load rounds) plus 166 vtable dispatch thunks bulk-pinned
  via the decoded-basefile scan (see below).

### SDK patches (this project uses a locally built SDK)

The game now runs against a **patched SDK** built from
`../rexglue-sdk` (installed to `../rexglue-sdk/out/install/win-amd64`;
the debug build dir's `rexglue_DIR` cache points there). Two changes on top of
v0.10.0 (commit c94f5eb):

1. `UserModule::GetProcAddressByOrdinal` (src/system/user_module.cpp): thunk
   cache per (caller module, ordinal) like KernelModule, plus fallback to the
   registered guest address when the thunk pool is exhausted. Without it the
   64 KB per-module thunk pool ran dry ~35 s into boot and the game received
   null exports (`XexGetProcedureAddress ordinal 6 in 'XMediaFacade_default'
   not found` → call to 0x0).
2. `draw.cpp` (GPU plugin): removed the modal `assert_true(x0 < x1 && y0 < y1)`
   before the empty-resolve check. Forza emits **empty resolves constantly**
   (572 in a 3-minute run, including bursts during FMV playback); the empty
   case is handled gracefully right below the assert, but in Debug builds the
   assert popped a modal dialog and blocked the process.

To rebuild the SDK after further patches:

```
cd ..\rexglue-sdk
cmake --preset win-amd64
cmake --build out/build/win-amd64 --config Debug   (and --config Release)
cmake --install out/build/win-amd64 --config Debug (and --config Release)
cd ..\"Forza Horizon project"
cmake -S . -B out\build\win-amd64-debug -Drexglue_DIR="..\rexglue-sdk\out\install\win-amd64\lib\cmake\rexglue"
cmake --build out\build\win-amd64-debug --target forzahorizon
```

(The SDK checkout's thirdparty submodules were seeded by copying from the
Tdu2 project's populated `rexglue-sdk` checkout — same commit c94f5eb — plus
hand-written `gitdir:` pointer files, since CMake verifies `thirdparty/<name>/.git`.)

3. `KeSetCurrentStackPointers` (src/kernel/xboxkrnl/xboxkrnl_threading.cpp):
   the export now performs a **real host fiber switch**. Forza implements its
   cooperative task system on this export: guest code saves the yielding
   task's PPC register file, restores the target's, reprograms LR with the
   target's resume address, and tail-calls the export, which on real hardware
   "returns" through that LR. The bookkeeping-only implementation instead
   returned straight into the yielding call chain with the target's registers,
   so the first switch to a fresh task crashed with `read/write of guest
   0x00000000` (the fresh task's register file and mailbox are zero). Each
   guest stack now gets one host fiber (`rex::thread::Fiber`, keyed by
   `(guest thread, stack alloc base)`): switching parks the yielding chain
   inside the export and resumes the target chain wherever it parked before;
   a never-run stack dispatches its resume LR through the function table.
   This is what unlocks the press-start → main menu transition and beyond.

5. `Shader::GatherVertexFetchInformation` (graphics/pipeline/shader/translator.cpp):
   removed the `assert_true(!stride || vertex_binding.stride_words ==
   fetch_instr.attributes.stride)` before reusing a vertex binding. A shader
   may legally fetch the same fetch constant with different per-instruction
   strides (Xenos honors the stride in each vfetch instruction), and Forza
   does exactly that when the race scene loads — the assert popped a MODAL
   dialog over the game (the GPU DLL's CRT ignores the exe's
   `_CrtSetReportMode`) and froze the run right before the first race. The
   binding's stride is translator bookkeeping only: it is consumed nowhere
   else, and the emitted shader code uses each instruction's own stride.

6. `KernelState::LoadUserModule` (src/system/kernel_state.cpp): when the
   recompiled shared library for a module is already wired, return the
   existing UserModule instead of refusing the load. On real hardware
   `XexLoadImage` on an already-loaded module succeeds (refcount semantics),
   and Forza reloads `XMediaFacade_default.xex` when the festival loads —
   with a path string that differs in form from the boot-time load, so the
   same-file check missed and the refusal made the game raise the
   dirty-disc UI (`XamShowDirtyDiscErrorUI`).

7. `RingBuffer::Write` (src/core/ring_buffer.cpp): the two overflow
   `assert_true`s became one-time warnings. The XMA audio ring overflows
   under load; the memcpy overwrites unread data either way (same as
   clicking Ignore), so the modal dialog only froze the game. Note the
   Release/perf build compiles asserts out entirely.

8. `XThread::Resume` (src/system/xthread.cpp, Win32 path): resuming a thread
   whose suspend count is already 0 used to `fetch_sub(1)` a `uint8_t`,
   underflowing 0 → 255 — which *suspended* the thread. Forza double-resumes
   threads while the front-end engages (session 006: guest thread F8001558
   left at count 254 after a double resume, i.e. wedged). It now follows NT
   semantics: count 0 → no change, returns `X_STATUS_INVALID_PARAMETER`
   (CAS-guarded decrement otherwise). The NtResumeThread shim passes the
   error through. Additionally `xeXamContentCreate` (src/kernel/xam/
   xam_content.cpp) now traces every content create/mount: user_index,
   root_name, file_name, type, flags, xuid, overlapped, and the result —
   this is the call that mounts save/marketplace packages (krnl=trace shows
   it; before this the mount was invisible in logs).

9. `KeSetCurrentStackPointers` fiber map lifetime (src/kernel/xboxkrnl/
   xboxkrnl_threading.cpp): the guest-stack → host-fiber map is keyed by
   (thread, stack alloc_base) with no lifetime management, and the guest
   frees task stacks and reuses their bases. A switch to a reused base then
   found the PREVIOUS task's parked fiber and resumed the dead chain with
   the new task's context — wild guest pointers crashing the task system,
   timing-dependently (save-load crashes in sessions 005/006/009/010, race
   start in 011: "alloc_base=70898000 sp=base-0x50" took the resume path and
   died inside the old chain). The guest switcher always dispatches a NEW
   stack with sp exactly base-0x50 (its initial frame), while a parked chain
   sits strictly deeper (it parked inside this export). The resume path now
   treats an sp within 0x200 of the stack top as a stale entry, retires it
   and starts a fresh stack; the trampoline also retires the map entry when
   a chain returns to its stack start (task completed). Verified via the
   perf PDB (see below), which symbolized the crash to the task chain
   sub_830ED900 → sub_830EBEA0 → sub_8310C238 → sub_83109D98 → sub_830ED910.

10. `NtQueryInformationFile(XFileSectorInformation)` (src/kernel/xboxkrnl/
    xboxkrnl_io_info.cpp): returned a **hash of the file path** as the
    "sector size" (inherited from Xenia). Hardware returns the device sector
    size (512 on the FATX HDD), and games use it to align streaming reads —
    a per-file random value misaligns every read made with it, so the parsed
    data grows data-derived wild pointers. This was the second corruption
    source behind the "wild guest pointers" family: the world-data parse
    (Colorado .oww/.owr/.nav) crashed at a *deterministic* call chain
    (sub_82A7D410 → … → sub_82D3DB00, identical host offsets across
    sessions 012/013) with per-session garbage pointer values — the same
    wrong lengths/offsets against per-run heap layouts. Now returns 512 and
    traces the query. (Session 014's crash after the fiber-map fix is
    consistent with already-corrupted world data reaching the race-start
    task code.)

11. `kDeferredOverlappedDelayMillis` (src/system/kernel_state.cpp): every
    deferred overlapped completion slept 100 ms **on the single kernel
    dispatch thread**, serializing the game's whole async pipeline at ~10
    ops/second (hardware: microseconds, concurrent). Symptoms consistent
    with the resulting timing distortion: the loading screen staying over
    gameplay behind a backed-up queue (session 015) and world-resource
    objects consumed half-initialized — the persistent `sub_82D3DB00+0x24f`
    fault (sessions 012/013/016-019) reads a struct field containing
    `1.0f`/packed tag bytes where a pointer belongs, i.e. an object read
    before its async fill-in completed. Reduced to 1 ms; the structural
    asynchrony (dispatch thread, `X_ERROR_IO_PENDING` set at queue time)
    makes a long sleep unnecessary.

12. `WindowSDL::OpenImpl` + resize handler (src/ui/window_sdl.cpp): window
   sizes are **physical pixels on Windows**. SDL3 declares the process
   per-monitor-v2 DPI-aware by default (`WIN_InitDPIAwareness` in the bundled
   SDL3: no `SDL_WINDOWS_DPI_AWARENESS` hint → PMv2), so `SDL_CreateWindow`
   takes physical pixels — and the resolved desired size (window cvars /
   guest video mode / resolution preset) is already pixels. The old code ran
   it through `SizeToPhysical()` again, multiplying by the display scale: a
   requested 3840×2160 became a 7680×4320 window on a 4K panel at 200%
   scaling — the picture drawn at 2× and cropped ("heavily zoomed in",
   fullscreen or windowed). Windows now tracks the desired size 1:1 with
   what SDL reports, like the Mac path already did; only X11 keeps the
   conversion. This also removes the resize-induced surface/rect mismatch
   class at fullscreen transitions.

### Current wall: the wild-guest-pointer family — three causes fixed, one open

The "wild guest pointers after loading the save / at race start" crashes
(sessions 005–019) trace to a sequence of independent sources, all fixed so
far:

1. **Fiber-map stale entries** (patch 9): the guest-stack → host-fiber map
   kept entries for freed stack bases; a new task dispatched onto a dead
   parked fiber. Timing-dependent (required allocator base reuse).
2. **Fake sector sizes** (patch 10): `XFileSectorInformation` returned a
   per-file path hash instead of 512; every aligned streaming read made with
   it was misaligned, corrupting the parsed world data. Deterministic crash
   site, per-session garbage values.
3. **100 ms deferred-overlapped sleep** (patch 11): serialized the whole
   async pipeline through the dispatch thread — loading screen stuck over
   gameplay (015), half-initialized resource objects (persistent
   `sub_82D3DB00+0x24f` fault, 012/013/016-019).

After each fix the crash signature moved or persisted, which is how the
sequence was found. The persistent `sub_82D3DB00` fault reads a struct field
holding `1.0f`/packed tag bytes where a pointer belongs — an object consumed
before its async fill-in; patch 11 removes the timing distortion most likely
responsible. If it still reproduces, the perf PDB names the chain — keep
reading logs.

### Wall update (13 Oct): the persistent fault, now at instruction level

It still reproduced — sessions 033/037/042–046/049 — in two contexts that share
one worker chain, and the perf PDB + `tools/ppc_disasm.py` (capstone over
`tools/xexdump/default_base.bin`) now pin it to exact guest instructions:

- **Fault A** (`_imp__sub_82D3DB00+0x24f`, the save-load crash and sometimes
  driving): the host `movzbl (%rdx,%rcx)` decodes to guest `lbzx r8, r11, r30`
  in the record loop — `record->ptr4[i]`, where the record is
  `[r3+0x54] + (r4 & 0xFF) * 12` (a 12-byte record `{ptr0, ptr4, byte8,
  count9}`). Observed fault addresses `0x0` / `0x1A8D2693` / `0x643E0D0A` are
  the record's `+4` field being null or garbage.
- **Fault B** (`_imp__sub_82D3CD48+0x207`, the driving crash): a byte load
  through the pointer stored at `[r5]`, where the caller (82D3DB00's loop)
  passes `r5 = (table_byte << 3) + obj->0x5c`. Observed `0x0` / `0x3FDDD430`
  are that slot pointer or its target being null/garbage.

Full chain (worker thread via `sub_82A7D410` task dispatch):
`8255AE10 → 823ED888 → 823E40D8 → 823E3218 → 82D4E2E0 → 82D4DE30 →
82D4DCC8 → 82D43818 → 82D42638 → (indirect) 82D44B90 → 82D3DB00 → 82D3CD48`.
The save-load variant enters at `82D4D9D0` instead (→ `82D4D1C8`, a
mutex-guarded ring-buffer pop from `[manager]+0x454`, draining items and
running each through `82D43818`). Both faults therefore read pointer fields of
streamed-resource objects consumed off that queue — the same
"consumed before its async fill-in" family, now with the exact fields known.

Session 049 context: the crash landed ~100 ms after the game streamed a
VW Scirocco traffic car (`media\brakes\*.rmb.carbin` reads, then
`cars\vw_sciroccor_11\car_skeleton_lod05.gr2` / `car_animations_lod05.gr2` /
`colorshadersettings1.xml` probes). The `.gr2` probes are benign (no `.gr2`
exists anywhere in the media tree or the zips — cars are built from `.carbin`;
the zips and `zipmanifest.xml` are disc-accurate, and `colorado.oww/.owr` being
32/12 bytes is correct OWWF referral records, not truncation).

Tooling added with this update:

- **SDK patch 13: guest-state crash dump** (`src/system/xmemory.cpp`): when the
  unhandled-AV handler fires, it now also dumps the faulting thread's PPC
  register file (`guest ctx:` lines), walks the guest stack (`guest stack NN:
  r1=… lr=…`, backchain `[r1]`, saved LR `[r1-8]` per `__savegprlr`), and —
  when the faulting frame is `sub_82D3DB00` or `sub_82D3CD48` — dumps the
  object header (`[r3+0x40..0x60]` / `[r4+0x50..0x5c]`), the 12-byte record
  (`+0/+4/+8/+9`) and the `[r5]` slot pointer and its target. All reads are
  guarded by heap-commit + host page-protection checks so the handler cannot
  fault itself. Rebuild the SDK (Debug+Release), `cmake --install`, re-copy all
  DLLs into both build dirs and relink the exe.
- `tools/ppc_disasm.py` — disassembles guest PPC code from the decrypted
  basefile: `python tools/ppc_disasm.py 82D3DB00 150`.
- `tools/sym_line.ps1` — dbghelp-based perf-VA → `symbol+offset` resolver (the
  PDB carries publics but not line info for the LTO'd recomp functions).

Next step when it crashes again: read the `guest ctx`/`guest stack`/record
dumps in the log, identify which of the dumped pointer fields is garbage, and
walk the queue producer (`82D4D348`/`82D4D3D8`/`82D4D488`/`82D4D510` family
around the `82D4D1C8` pop) for the fill-in that never landed.

### Wall update (14 Oct): first guest dumps — the record index is stale stack data

The dumps fired on sessions 053/054/055 (three save-load crash loops). All
three went through the `sub_82D4D9D0` dequeue loop (`guest stack 04:
lr=0x82D4DA24`), and the first two faults were **both at record index
`r4 = 0xBE` (190) on two different objects**:

- 054: object `r3=0x4238BEE0`, record `r29=0x4238CA58`, `record->ptr4` =
  `0x3F800000` (**1.0f** as a pointer), loop index `r30=0`, call site
  `0x82D45084` (the second `bl 0x82d3db00`).
- 055: object `r3=0x420CEA60`, record `r29=0x420CF5E8`, `record->ptr4` = `2`,
  call site `0x82D45054` (the first call).
- 053 (fault B): slot `r5=0x431D1148` (object `r4=0x431D0800`), `[r5]=0x12C`
  (300) — again a small integer where a pointer belongs.

The "pointers" are structured small values, not random garbage: the record
index 0xBE is read from stack slots `[r1+0x18C]`/`[r1+0x19C]` in
`sub_82D44B90`, and **nothing in that function ever writes those slots** (no
stores, no `addi rX, r1/rY, 384..419` anywhere in the emitted body — only the
two `lwz` reads at generated lines 26351/26371). They are stale stack bytes
left by whatever previously occupied that stack region — deterministic for
this call context, which is why every observed crash picks record 190. On real
hardware the same stale read happens, but there the table presumably has ≥191
populated records, so the question is why our record table holds floats/tags
at those offsets: either the producer filled fewer records than the game
expects, or the array base/extent fields on the object are stale. The enhanced
dump (below) answers this by probing records 0–2 and index−2/index−1/index:
the transition from plausible pointers to floats/tags marks the effective end
of the table.

Session 056 (the frozen load screen, audio still playing): after the save
content mount (`B13EBABEBABEBABE:\`) resolved at 09:34:31 there was **zero
file activity for ~50 s** while the UI/audio threads kept polling
(`XamXStudioRequest`/`XMPGetPlaybackController` continue past 09:34:59) — the
item-processing pipeline stalled instead of crashing. Same subsystem, benign
outcome; treat a future freeze as the same investigation target.

Dump fix in this round: dbghelp reports the recompiled functions with an
import-decoration prefix (`_imp__sub_82D3DB00`), which the previous strict
`strlen == 12` check rejected — so the object/record dumps never printed. The
detector now matches `sub_` anywhere in the symbol and strips the prefix. The
`sub_82D3DB00` dump additionally prints `[r3+0x54]` (the record-array base)
and records 0/1/2 plus `index-2/index-1/index` so the table's real extent is
visible.

### ROOT CAUSE FOUND + FIXED (14 Oct): the 0xBE stack junk fill

Session 059 (a headless boot crashed on its own at ~20 s, same signature)
produced the first complete dump:

```
object r3=0x426EF300 index(r4)=0xBE record r29=0x426EFE18
  [r3+0x4C] = 0x3F800000        (1.0f in the object header)
  [r3+0x54] record array base = 0x426EF530
  record[0] +0=0x426EF620 +4=0x426EF626 +8=0x06 +9=0x03   <- valid records
  record[1] +0=0x426EF629 +4=0x426EF62F +8=0x06 +9=0x03
  record[2] +0=0x426EF632 +4=0x426EF638 +8=0x06 +9=0x03
  record[188] +0=0x4233FED9 +4=0x00070027 +8=0xFF +9=0xFF  <- different structure
  record[189] +0=0x4233FF00 +4=0x00070027 +8=0x00 +9=0x00     (odd-address
  record[190] +0=0x4233FF11 +4=0x00070027 +8=0xFF +9=0xFF      pointers = strings)
```

The record table holds ~190 valid 12-byte records; index 0xBE = 190 lands in a
neighbouring structure (string descriptors with a 0x00070027 tag). The record
index comes from stack slots `[r1+0x18C]`/`[r1+0x19C]` in `sub_82D44B90` that
nothing in that frame ever writes — and the reason those reads returned a
consistent `0xBE` was **`XThread::AllocateStack` junk-filling every guest
stack with 0xBE**. The Xbox 360 kernel hands out zeroed physical memory, so on
hardware those same reads return 0 → record index 0 → a valid record → no
crash. SDK patch 14: zero the stack instead of the 0xBE fill
(src/system/xthread.cpp).

Validation: a headless boot that previously crashed by itself at ~20 s
(session 059) ran ~50 s past that point with zero access violations
(session 060), and then hit a NEW, different wall: `read of guest 0x0` in
`sub_82C7E4F0+0x3ae ← sub_82E3DB18+0x2a2 ← sub_82E41288+0x114 ←
sub_82632368+0x3cd ← 8251CE14/8251E888 ← 82483750/82483864 ← 82C0A1D4 ←
82C0BF44 ← 830EBED4/830ED908` — possibly another uninitialized-stack read
(this one getting 0 where a previous frame on hardware would have left
valid data) or a genuine next bug. Investigate with the same tooling when it
reproduces in interactive play.

Also added this round: `src/system/watchdog.cpp` — a symbolized host-stack
sampler for every thread, appended to `logs/watchdog.log` every 30 s (started
from the KernelState constructor; writes to its own file, never through the
shared logger, since a sampled thread may hold the logger mutex while
suspended). This is what catches the "load screen frozen, audio playing"
stalls: each sample names which guest function every thread is parked in
(`G_` = recompiled guest, `R` = runtime, `H` = host/OS frames). The toml
log-levels were restored after another auto-rewrite (hand-written header
re-added).

### Wall update (14 Oct, later): the save-load freeze is a streaming queue
### that drains at a crawl

With the 0xBE fix in, the save-load path no longer crashes but the load
screen freezes (sessions 056/058/063). The watchdog finally caught it in the
act (session 063, sample 10:02:53): every task worker parked in
`NtWaitForSingleObjectEx ← sub_82465EC0 ← sub_823E91C0`, while the loader
thread spun in a yield loop. SDK patch 15 added two instruments:

- `NtYieldExecution_entry` now counts consecutive yields from the same
  return site (the yield wrapper's saved LR, recovered through the guest
  backchain) and, after 512, dumps the wait object once
  (`LogGuestSpinSample`, src/system/xmemory.cpp): frame args, counter fields,
  request records and the manager — all reads guarded.
- `NtCreateFile` failures log the guest caller's LR.

The decoded wait (guest `sub_823F4B30`, return site `0x823F4F64`):

```
while (check(obj) > obj->0x84) { yield ×1000; pump callback }
check(obj) = obj->0x3C ? 1 : obj->0x80
```

The object (0x40159EE8, stable across boots) is a **streaming queue**:
+0x00 ring buffer base (0x402D0010), +0x04 size 0xE1000, +0x08/+0x0C moving
cursor pair (it advances and wraps - the ring IS alive), +0x80 = pending
counter, +0x84 = limit (3), +0xA4 = per-iteration pump callback
(0x8247E780 → a throttled `vtbl+0x78(2)` call on a manager singleton). The
in-flight records carry game-asset strings - UTF-16 `"MediaName"`, `"FORD"` -
so this is the **asset/resource streaming queue**: the loader queues build
jobs and parks until fewer than 3 are outstanding. Observed pending: 4-7,
stuck for minutes at a time while individual items complete only occasionally
(7→5→4 over minutes). The same wait object is also visible in normal
operation; the load only stalls when the backlog stops draining.

Ruled out this round:

- **The relative-path bank opens (`AMB_Festival.fsb` → "no device") are
  benign.** They fail identically on hardware: the disc image (parsed with a
  new GDFX walker, `tools/gdfx_walk.py` - descriptor at LBA 16672, root at
  2,116,929, physical = logical + 16640 sectors; dirents are 4-byte-aligned
  {u32 sector, u32 size, u8 flags, u8 namelen, name} records) has NO loose
  `AMB_Festival.fsb` anywhere - the region ambience banks live only inside
  `media/tracks/colorado/bin.zip` (230k entries), which the game never opens
  through our FS. Working sessions (048-055) show zero such opens; frozen
  save-load sessions show them for each region bank in turn (Festival,
  then Red_Rock). The game falls back to the packaged bank; on HW this
  fallback works.
- The bare-filename open reaches `VirtualFileSystem::OpenFile` with a NULL
  root entry (proved by the `[no device]` log), so no RootDirectory handle is
  involved; `utf8_canonicalize_path` keeps bare names bare (same as Xenia).

**The decisive experiment**: SDK patch 15b adds an env-gated diagnostic
(`REX_UNSTICK_QUEUE=1`, src/system/watchdog.cpp `UnstickLoop`): watch the
queue object (fingerprint: size field 0xE1000 + sane counters), and once
pending > limit across two checks, raise the limit to 0x00FFFFFF so the
loader's wait exits. Result: the loader immediately proceeds (next region
bank opens 20 s later), the game runs ~1 minute further, then crashes in the
original worker chain (`sub_82D3CD48`, write of 0x701F0120 through an
unfilled record: `[[r5]] = 0x0B13030A` garbage). That is exactly what a
consumer racing ahead of unfilled records produces - i.e. the wait is
**correct game logic** and the real bug is upstream: the worker pool that
consumes the streaming queue runs at a tiny fraction of hardware speed.

Next steps for this wall:

1. Instrument the drain side: find what decrements `queue+0x80` (the
   completion path) and where its wakeup comes from; the workers are parked
   in `NtWaitForSingleObjectEx` on events that only fire occasionally.
2. Check whether the worker threads' waits use long timeouts in guest code
   (slow poll loop) versus a missed event signal (lost wakeup).
3. The unstick diagnostic remains in the build (env-gated, off by default);
   it is a diagnostic, not a fix - forcing the gate open crashes ~1 minute
   later via the race described above.
4. `tools/udf_walk.py` / `tools/gdfx_walk.py` / `tools/iso_walk.py` exist for
   any future disc-image archaeology (the original
   `Forza Horizon (USA)...iso` is a UDF-bridge GDFX image).


**Diagnostics note: the perf build is symbolized.** The project CMakeLists
adds `/DEBUG` to Release links, so `forzahorizon.pdb` (next to the perf exe)
carries every `__imp__sub_82XXXXXX` public — the crash handler's backtrace
names the exact guest functions and host offsets in *perf*, no debug build
needed. After relinking, verify with
`llvm-pdbutil dump -publics forzahorizon.pdb | grep -c __imp__sub_`.

Ruled out along the way:

- **The `B13EBABEBABEBABE:` symlink is NOT corruption.** It is the game
  formatting the XUID (16 hex digits) as the content mount name, and the
  runtime's placeholder XUID in `UserProfile` (src/system/xam/user_profile.cpp)
  is deliberately `0xB13EBABEBABEBABE`. The mount name is deterministic and
  consistent; every path under it resolves. Do not "fix" this name: the
  on-disk save tree (`C:\Users\<user>\Documents\forzahorizon\<xuid>\<title>\`)
  is keyed by it, and changing the XUID orphans existing saves.
- **The XMediaFacade unload+reload FATAL (0x88050388)** from session 004 is
  fixed (SDK patches 6 + the RegisterModule overwrite): sessions 005/006
  reload XMediaFacade *and* SpeechFacade cleanly
  (`identical module table … reusing it`).

### Saves live under Documents, not the game root

`user_data_root` defaults to `Documents\<app name>` (NOT `game_data_root`):
`C:\Users\<user>\Documents\forzahorizon\` contains
`<xuid>\<title>\<content-type>\<file>` packages, `Headers\`, `achievements\`
and `cache\shaders\`. The save content mount is the STFS-less HostPathDevice
over `<xuid>\<title>\<type>\<file_name>\`; the game writes
`ForzaProfile`, `PlayerDatabase`, `GameplayLog`, … directly into it.

### The perf toml rewrites itself

`out/build/win-amd64-perf/forzahorizon.toml` gets rewritten by the exe and a
`# Auto-generated`-headed file **loses its `[log.levels]` section** (seen
10:08, mid-run). The file now carries a hand-written header like the debug
one, which survives. If per-category levels vanish again, re-add:

```toml
[log.levels]
fs = "trace"
krnl = "trace"
sys = "trace"
gpu = "error"
```

### Earlier wall: race-load host asserts

With the scanner-hole tail drained (bulk-pinned vtable thunks, see below),
the game runs through the intros and past the controls screen to the first
race. The remaining walls are host-side asserts in the GPU plugin (see SDK
patch 5), not guest function holes — when the game freezes with a dialog,
read it: it names the plugin, file, line and expression.

With the fiber switch working, the game gets to the main menu and past it;
the remaining crashes are the usual scanner-hole FATALs
(`Call to invalid or unregistered function at guest address 0x…`) on guest
threads once the task system engages after the FMV. `tools/fix_holes.py`
automates the pin → codegen → build → run loop, or pin by hand in
`[entrypoint.functions]` (all addresses so far are in the `0x824xxxxx`
thunk clusters). Pin round log: 0x8249D410, 0x8247A5C8, 0x8249CA20,
0x824705E0, 0x8249D660, 0x824516D0, 0x831411E8, 0x8257D340 (round 6: loading
into the first race), 0x8257D4B0 (round 7: same cluster, one hop deeper),
0x82DB8B08 (round 8: ~2.5 min into interactive play, 3 s after the speech
facade registered — front-end engaging deeper), 0x82DBC730 (round 9: same
cluster, one hop further; hit after ~2 h of interactive play), 0x8249C440
(round 10: task-system cluster again, next to the pinned 0x8249C460),
0x82DBCE80 (round 11: the 0x82DBxxxx cluster again, same front-end phase),
0x8249CAA0 (round 12: task-system cluster, neighbor of the pinned
0x8249CA20 — the two clusters keep alternating through the front-end
engagement phase), 0x8257F910 (round 13: the race-load cluster reached
again further up during the front-end phase), 0x82DBD148 (round 14:
0x82DBxxxx cluster once more, same phase), 0x82DBCFC8 (round 15: fifth
hole in the same cluster), 0x8249CA70 (round 16: task-system cluster
again, neighbor of the pinned 0x8249CAA0), 0x8249D378 (round 17: same
cluster, neighbor of the pinned 0x8249D410), 0x82DBBFA0 (round 18: sixth
hole in the 0x82DBxxxx cluster), 0x82DBC520 (round 19: seventh hole in the
same cluster).

`tools/pin_unresolved.py` is a second lever: codegen's analysis phase
reports every direct branch from emitted code to a non-function as an
`UnresolvedCall`, so that tool runs codegen, pins all reported targets in
bulk, and repeats until validation is clean — draining whole thunk chains
without needing a runtime crash each. As of the 0x8257D4B0 pin,
**codegen validation is clean**: every remaining scanner miss (if any) is
only reachable via indirect calls (vtables/function pointers), which
validation cannot see — those still need the fix_holes runtime loop.

### Bulk-pinning vtable thunks via the decrypted basefile

The remaining scanner misses are vtable dispatch stubs, only reachable
indirectly. They can be found offline instead of one crash at a time:

1. `xextool -b tools/xexdump/default_base.bin "Forza Horizon/default.xex"`
   (xorloser's XexTool, e.g. the copy bundled with iso2god) dumps the
   decrypted, uncompressed basefile — the XEX is not compressed, so this is
   the plain image mapped at 0x82000000.
2. `tools/pin_thunks.py` scans it for dispatch stubs of any shape —
   straight-line code starting `lwz rX,0(r3)` (rX in r10/r11/r12 — compiler
   thunks use either register), containing an `lwz rX,slot(rX)` load, ending
   `mtctr rX; bctr`, with no control flow in between (variants interleave
   0-8 parameter-setup instructions) — subtracts what codegen already
   emits, and pins the rest.
3. `tools/filter_thunk_pins.py` drops pins whose linear predecessor does
   not end the previous code flow (unconditional branch / padding / data).
   The same byte signature occurs as the INLINE dispatch tail of real
   emitted functions (entered by fallthrough, e.g. `beq → tail`); pinning
   one of those splits the enclosing function and turns its internal
   branches into runtime `Unresolved branch` fatals. The rule validated
   perfectly against both control groups: all runtime-demanded thunks are
   preceded by a flow end, all known-breaking speculative pins are not.

This took the manifest from 52 hand-collected pins to 210 in one pass, with
zero unresolved-branch markers in the generated code. Future misses should
now be rare real function starts (not thunk tails) — pin those individually
as the runtime demands them.

### Third guest image: SpeechFacade_default.xex

Once the front-end engages, the game `XexLoadImage`s
`SpeechFacade_default.xex` (Kinect speech) at 0x89000000+ and calls into it
(`Execute(890A0468): function not in function table` → fatal at
0x890A00D8). Declared as a second `[[modules]]` entry (see the manifest;
note that in TOML a `[modules.functions]` table attaches to the most recent
`[[modules]]` element, so pins for a module must be listed after it).
Codegen needed one pin: 0x890E2FA0.

### SDK patch 4: thunk pool growth + sharing (function_dispatcher.cpp)

The caller module's fixed 64 KB thunk pool (16 K thunks) drains as title
cycles module loads, and `KernelModule::GetProcAddressByOrdinal` returned
null on exhaustion (the game then calls the null export). `AllocateThunk`
now grows the pool in 1 MB chunks (the guest-side shadow table is committed
with 32× headroom by `Memory::InitializeFunctionTable`, so growth is just a
limit bump via `Memory::ExtendThunkReserve`), and falls back to sharing an
existing thunk for the same host function (thunks are stateless trampolines).

### SDK / project version skew (important!)

The official prebuilt SDK binaries bundled in `rexglue/win-amd64` were built
from a **newer source state** than the `c94f5eb` checkout in
`../rexglue-sdk` (their `Window`/log-config APIs differ). The game must build
against ONE SDK consistently. The build is now pointed at the patched SDK:

```
cmake -S . -B out\build\win-amd64-debug -Drexglue_DIR="E:/.../rexglue-sdk/out/install/win-amd64/lib/cmake/rexglue"
```

After ANY SDK rebuild: `cmake --install` AND re-copy **all** DLLs from
`rexglue-sdk/out/install/win-amd64/bin/` into the build dir (the game's
post-build copy only runs when the exe relinks), and rebuild the exe (its
inline code must match the SDK headers). Mixing old DLLs with new headers
crashes/hangs before logging starts.

### Earlier walls (solved)

- **Two-image problem**: the game `XexLoadImage`s `XMediaFacade_default.xex`
  during early startup; declared as a `[[modules]]` entry in the manifest.
- **Thunk pool exhaustion**: see SDK patch 1 above.
- **Modal assert on empty resolves**: see SDK patch 2 above.
