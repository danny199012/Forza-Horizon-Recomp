@echo off
rem Smoke-test launch: headless boot with the patched runtime.
rem Logs land in <build dir>\logs\ like play.cmd.
cd /d "%~dp0..\out\build\win-amd64-perf"
forzahorizon.exe --game_data_root "..\..\..\Forza Horizon" --gpu_plugin xenos --headless --log_level info
