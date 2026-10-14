# forzahorizon - ReXGlue Recompiled Project
#
# SDK boilerplate lives in generated/rexglue.cmake.

cmake_minimum_required(VERSION 3.25)
project(forzahorizon LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include(generated/rexglue.cmake)

# Sources
set(FORZAHORIZON_SOURCES
    src/main.cpp
)

if(WIN32)
    add_executable(forzahorizon WIN32 ${FORZAHORIZON_SOURCES})
else()
    add_executable(forzahorizon ${FORZAHORIZON_SOURCES})
endif()

# Stage the Xenos GPU emulation plugin next to the exe. rexglue picks the
# per-configuration variant (rexgpu-xenosd.dll for Debug, rexgpu-xenos.dll
# for Release). Without this the game has no GPU emulation at all.
rexglue_setup_target(forzahorizon GPU_PLUGINS xenos)

# The SDK headers use clang builtins, so the generated recomp code cannot be
# compiled by plain MSVC cl. Silence the UCRT deprecation noise our own
# headers would otherwise produce under clang.
if(WIN32)
    target_compile_definitions(forzahorizon PRIVATE _CRT_SECURE_NO_WARNINGS)
    # MiniDumpWriteDump (crash dumps in src/main.cpp's unhandled-exception
    # filter) lives in dbghelp.
    target_link_libraries(forzahorizon PRIVATE dbghelp)
    # Symbolized crash backtraces in Release/perf: CMake passes /DEBUG only
    # for the Debug config, so a Release link produces no PDB and the
    # access-violation handler prints raw addresses. Emit one anyway - the
    # PDB carries the extern "C" __imp__sub_82XXXXXX publics (guest address
    # in the name), which dbghelp resolves in the crash backtrace.
    target_link_options(forzahorizon PRIVATE "$<$<CONFIG:Release>:-Wl,/DEBUG>")
endif()
