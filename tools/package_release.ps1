<#
.SYNOPSIS
  Assembles a distributable release bundle for the Forza Horizon recomp.

.DESCRIPTION
  Produces release\<name>\ containing everything the game needs to run on
  another Windows PC:
    - forzahorizon.exe + cvar TOML (+ PDB optionally)
    - the runtime DLLs it imports (rexruntime, GPU plugin, facades, Tracy)
    - the game media tree ("Forza Horizon")
    - the launcher (RecompLauncher.exe + a bundle-adapted launcher.json)
    - a quickstart README.txt

  NO game content is included from anywhere but your local extracted dump;
  the bundle is for personal use (e.g. copying to another PC / Legion Go).

.PARAMETER Config
  Build config to package (default: win-amd64-perf).

.PARAMETER Output
  Output root directory (default: release). The bundle lands in
  <Output>\ForzaHorizonRecomp.

.PARAMETER IncludePdb
  Also copy the PDB (crash dumps resolve symbols with it; +18 MB).

.PARAMETER SkipMedia
  Reuse an existing "Forza Horizon" folder in the bundle (fast re-package
  after code changes).

.EXAMPLE
  powershell -File tools\package_release.ps1
  powershell -File tools\package_release.ps1 -SkipMedia   # after code tweaks
#>
param(
    [string]$Config = 'win-amd64-perf',
    [string]$Output = 'release',
    [switch]$IncludePdb,
    [switch]$SkipMedia
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$project = Split-Path $root -Parent
Set-Location $project

$buildDir = Join-Path $project "out\build\$Config"
$exe = Join-Path $buildDir 'forzahorizon.exe'
if (-not (Test-Path $exe)) {
    Write-Error "Game exe not found: $exe - run build.cmd -perf forzahorizon first"
}

$bundle = Join-Path $project "$Output\ForzaHorizonRecomp"
New-Item -ItemType Directory -Force -Path $bundle | Out-Null

Write-Host "== staging game binaries ($Config)" -ForegroundColor Cyan
$runtimeDlls = @(
    'rexruntime.dll',
    'rexgpu-xenos.dll',
    'TracyClient.dll',
    'forzahorizon_SpeechFacade_default.dll',
    'forzahorizon_XMediaFacade_default.dll'
)
Copy-Item $exe $bundle -Force
Copy-Item (Join-Path $buildDir 'forzahorizon.toml') $bundle -Force
foreach ($dll in $runtimeDlls) {
    $src = Join-Path $buildDir $dll
    if (-not (Test-Path $src)) { Write-Error "missing runtime DLL: $dll" }
    Copy-Item $src $bundle -Force
}
if ($IncludePdb) {
    Copy-Item (Join-Path $buildDir 'forzahorizon.pdb') $bundle -Force
}

Write-Host "== staging launcher" -ForegroundColor Cyan
$launcherExe = Join-Path $project 'launcher\publish\RecompLauncher.exe'
if (-not (Test-Path $launcherExe)) {
    Write-Warning 'launcher\publish\RecompLauncher.exe missing - run: cd launcher; powershell -File build.ps1'
} else {
    Copy-Item $launcherExe $bundle -Force
    Copy-Item (Join-Path $project 'launcher\banner.png') $bundle -Force
    # Bundle-adapted profile: paths are relative to launcher.json, which sits
    # next to the exe here.
    $json = Get-Content (Join-Path $project 'launcher\launcher.json') -Raw
    $json = $json -replace [regex]::Escape('../out/build/win-amd64-perf/forzahorizon.exe'), 'forzahorizon.exe'
    $json = $json -replace '"gameDataRoot": "\.\./Forza Horizon"', '"gameDataRoot": "Forza Horizon"'
    Set-Content (Join-Path $bundle 'launcher.json') $json -Encoding UTF8
}

Write-Host "== staging game media (robocopy, multithreaded)" -ForegroundColor Cyan
$mediaDst = Join-Path $bundle 'Forza Horizon'
if ($SkipMedia -and (Test-Path $mediaDst)) {
    Write-Host '   skipped (-SkipMedia), media already staged'
} else {
    robocopy (Join-Path $project 'Forza Horizon') $mediaDst /MIR /MT:16 /NFL /NDL /NJH /NP | Out-Null
    if ($LASTEXITCODE -ge 8) {
        Write-Error "robocopy failed with exit code $LASTEXITCODE"
    }
    Write-Host "   robocopy ok (exit ${LASTEXITCODE}: copied/extra/twin files)"
}

Write-Host "== writing quickstart" -ForegroundColor Cyan
@'
Forza Horizon - Xbox 360 recomp (ReXGlue) - personal-use bundle
================================================================

What you need on the target PC
  - Windows 10/11 x64
  - Microsoft Visual C++ 2015-2022 Redistributable (x64)
    https://aka.ms/vs/17/release/vc_redist.x64.exe
  - Recent GPU drivers (the Xenos plugin uses D3D12 by default;
    Vulkan can be selected in the launcher's Graphics tab)

How to run
  1. Double-click RecompLauncher.exe
     (resolution/scale/audio settings live there; the launcher writes
      forzahorizon.toml next to the game exe and stays in sync with the
      in-game F4 dialog)
  - or run forzahorizon.exe directly from a terminal:
      forzahorizon.exe --game_data_root "Forza Horizon" --gpu_plugin xenos

Notes
  - Saves go to Documents\forzahorizon\<xuid>\... automatically.
  - First load after a fresh copy can sit on the loading screen a while;
    give it a minute.
  - Known issues: HUD elements can flicker (minimap/speedometer),
    collision is unreliable, first save-load is slow. See the repo README.
  - The forzahorizon.pdb file (if present) is only for crash-dump
    symbolization; you can delete it.

Legal: this bundle is for personal use with a legally owned copy of the
game. It contains recompiled game code derived from your own dump - do not
redistribute it.
'@ | Set-Content (Join-Path $bundle 'README.txt') -Encoding UTF8

$size = (Get-ChildItem $bundle -Recurse -File | Measure-Object Length -Sum).Sum
Write-Host ''
Write-Host ('== done: {0}  ({1:N2} GB)' -f $bundle, ($size / 1GB)) -ForegroundColor Green
Write-Host '   zip or copy the folder to the target machine.'
