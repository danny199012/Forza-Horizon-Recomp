# Resolve perf-build VA -> generated source file:line via dbghelp (PDB line info).
param([string]$Exe = "out\build\win-amd64-perf\forzahorizon.exe", [string]$Dir = ".")
$src = @'
using System;
using System.Runtime.InteropServices;
public class SymTools {
  [DllImport("dbghelp.dll", SetLastError = true)]
  public static extern bool SymInitialize(IntPtr hProcess, string searchPath, bool invadeProcess);
  [DllImport("dbghelp.dll", SetLastError = true)]
  public static extern bool SymCleanup(IntPtr hProcess);
  [DllImport("dbghelp.dll", SetLastError = true)]
  public static extern ulong SymLoadModule64(IntPtr hProcess, IntPtr hFile, string imageName, string moduleName, ulong baseOfImage, uint imageSize);
  [DllImport("dbghelp.dll", SetLastError = true)]
  public static extern bool SymFromAddr(IntPtr hProcess, ulong addr, IntPtr displacement, IntPtr symbol);
  [DllImport("dbghelp.dll", SetLastError = true)]
  public static extern bool SymGetLineFromAddr64(IntPtr hProcess, ulong addr, IntPtr displacement, IntPtr line);
  [DllImport("dbghelp.dll", SetLastError = true)]
  public static extern uint SymSetOptions(uint options);
}
'@
Add-Type -TypeDefinition $src -Language CSharp

$dir = [System.IO.Path]::GetFullPath($Dir)
$exePath = [System.IO.Path]::GetFullPath((Join-Path $dir $Exe))
[void][SymTools]::SymSetOptions(0x12) # SYMOPT_UNDNAME(0x2) | SYMOPT_LOAD_LINES(0x10)
$hProcess = [System.Diagnostics.Process]::GetCurrentProcess().Handle
if (-not [SymTools]::SymInitialize($hProcess, $dir, $false)) { Write-Error "SymInitialize failed"; exit 1 }
$base = [SymTools]::SymLoadModule64($hProcess, [IntPtr]::Zero, $exePath, $null, 0x140000000, 0)
if ($base -eq 0) { Write-Error ("SymLoadModule64 failed: " + [Runtime.InteropServices.Marshal]::GetLastWin32Error()); exit 1 }

# SYMBOL_INFO ANSI x64: fixed part is 88 bytes, name follows inline.
$symBuf = [System.Runtime.InteropServices.Marshal]::AllocHGlobal(512)
function Resolve-VA([uint64]$va) {
  # write SizeOfStruct=88, MaxNameLen=256
  [System.Runtime.InteropServices.Marshal]::WriteInt32($symBuf, 0, 88)
  [System.Runtime.InteropServices.Marshal]::WriteInt32($symBuf, 84, 256)
  $disp = [System.Runtime.InteropServices.Marshal]::AllocHGlobal(8)
  $okSym = [SymTools]::SymFromAddr($hProcess, $va, $disp, $symBuf)
  $name = "?"
  if ($okSym) {
    $name = [System.Runtime.InteropServices.Marshal]::PtrToStringAnsi([IntPtr]($symBuf.ToInt64() + 88))
  }
  $okDisp = [System.Runtime.InteropServices.Marshal]::ReadInt32($disp)
  [System.Runtime.InteropServices.Marshal]::FreeHGlobal($disp)
  # IMAGEHLP_LINE64: SizeOfStruct(4) pad Key(8@8) LineNumber(4@16) pad FileName(8@24) Address(8@32) => 40 bytes
  $lineBuf = [System.Runtime.InteropServices.Marshal]::AllocHGlobal(64)
  [System.Runtime.InteropServices.Marshal]::WriteInt32($lineBuf, 0, 40)
  $okLine = [SymTools]::SymGetLineFromAddr64($hProcess, $va, $disp, $lineBuf)
  $loc = "??:?"
  if ($okLine) {
    $lineNo = [System.Runtime.InteropServices.Marshal]::ReadInt32($lineBuf, 16)
    $filePtr = [System.Runtime.InteropServices.Marshal]::ReadIntPtr($lineBuf, 24)
    $file = [System.Runtime.InteropServices.Marshal]::PtrToStringAnsi($filePtr)
    $loc = "{0}:{1}" -f $file, $lineNo
  }
  [System.Runtime.InteropServices.Marshal]::FreeHGlobal($lineBuf)
  "{0:X16} {1}+0x{2:X} -> {3}" -f $va, $name, $okDisp, $loc
}

Resolve-VA 0x143F0715F   # fault A: sub_82D3DB00+0x24f (save-load crashes 037/042/046)
Resolve-VA 0x14021F627   # fault B: sub_82D3CD48+0x207 (driving crashes 033/049)
Resolve-VA 0x143F070FF   # context before fault A
Resolve-VA 0x143F070DF
Resolve-VA 0x143F070BF
Resolve-VA 0x14021F607   # context before fault B
Resolve-VA 0x14021F5E7
Resolve-VA 0x14021F5C7
Resolve-VA 0x143F0717F   # context after fault A
Resolve-VA 0x14021F647   # context after fault B
[System.Runtime.InteropServices.Marshal]::FreeHGlobal($symBuf)
[void][SymTools]::SymCleanup($hProcess)

