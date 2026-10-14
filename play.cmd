@echo off
rem Launch Forza Horizon (recompiled) with the arguments it needs.
rem Logs always land in <build dir>\logs\ (next to the exe), no matter where
rem this script is started from. Pass "debug" to force the slow debug build.
rem
rem --log_level info                         drop debug spam (perf)
rem --gpu_allow_invalid_fetch_constants      the game emits fetch constants
rem                                          Xenos calls "invalid"; hardware
rem                                          accepts them - silences per-frame
rem                                          warnings
setlocal
cd /d "%~dp0"
set "DIR=out\build\win-amd64-perf"
if /i "%~1"=="debug" set "DIR=out\build\win-amd64-debug"
cd /d "%DIR%"
forzahorizon.exe --game_data_root "..\..\..\Forza Horizon" --gpu_plugin xenos --log_level info --gpu_allow_invalid_fetch_constants=true %2 %3 %4 %5
