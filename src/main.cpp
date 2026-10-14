// forzahorizon - ReXGlue Recompiled Project

#include "generated/default/forzahorizon_init.h"

#include "forzahorizon_app.h"

#if defined(_WIN32)
// WIN32_LEAN_AND_MEAN / NOMINMAX already come from the SDK's own compile
// definitions, so redefining them here would just warn.
#include <windows.h>
#include <dbghelp.h>

#include <cstdio>
#include <cstdlib>
#include <exception>
#include <new>

// rexruntime raises abort() when the guest hits something it cannot service
// (e.g. a call to an unregistered function address). The MSVC debug CRT turns
// that into a MODAL "Debug Error! abort() has been called" dialog, which
// blocks the process forever on an unattended run and hides the real cause.
// Route it to the log instead and take the process down, so a run always
// terminates and leaves a diagnosable log behind.
namespace {

// SEM_NOGPFAULTERRORBOX (set below) also silences Windows Error Reporting,
// so a NATIVE crash (access violation in the recompiled code, the runtime or
// a GPU plugin) would otherwise die with no trace at all. This filter writes
// a minidump + a text summary into the exe's logs/ directory before dying.
LONG WINAPI WriteCrashDump(EXCEPTION_POINTERS* info) {
  wchar_t exe_dir[MAX_PATH];
  wchar_t base[MAX_PATH];
  GetModuleFileNameW(nullptr, base, MAX_PATH);
  lstrcpyW(exe_dir, base);
  wchar_t* slash = wcsrchr(exe_dir, L'\\');
  if (slash) *slash = L'\0';
  wchar_t dump_path[MAX_PATH];
  wsprintfW(dump_path, L"%s\\logs\\crash_%lu.dmp", exe_dir, GetCurrentProcessId());

  HANDLE file = CreateFileW(dump_path, GENERIC_WRITE, 0, nullptr,
                            CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
  if (file != INVALID_HANDLE_VALUE) {
    MINIDUMP_EXCEPTION_INFORMATION mei{GetCurrentThreadId(), info, FALSE};
    MiniDumpWriteDump(GetCurrentProcess(), GetCurrentProcessId(), file,
                      MiniDumpWithDataSegs, info ? &mei : nullptr, nullptr,
                      nullptr);
    CloseHandle(file);
  }

  // Text summary: exception code + faulting address + the module and RVA it
  // landed in (the PDBs sit next to the exe, so module+offset resolves).
  HMODULE mod = nullptr;
  char mod_name[MAX_PATH] = "?";
  uintptr_t fault = reinterpret_cast<uintptr_t>(info->ExceptionRecord->ExceptionAddress);
  uintptr_t rva = fault;
  if (GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                             GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                         reinterpret_cast<LPCWSTR>(fault), &mod)) {
    char path[MAX_PATH];
    if (GetModuleFileNameA(mod, path, MAX_PATH)) {
      const char* name = strrchr(path, '\\');
      lstrcpynA(mod_name, name ? name + 1 : path, MAX_PATH);
      rva = fault - reinterpret_cast<uintptr_t>(mod);
    }
  }
  char summary_path[MAX_PATH];
  wsprintfA(summary_path, "%S\\logs\\crash_%lu.txt", exe_dir, GetCurrentProcessId());
  FILE* f = fopen(summary_path, "w");
  if (f) {
    fprintf(f,
            "exception_code=0x%08lX\nfaulting_address=0x%016zX\n"
            "module=%s\nrva=0x%zX\n",
            info->ExceptionRecord->ExceptionCode, fault, mod_name, rva);
    fclose(f);
  }
  return EXCEPTION_EXECUTE_HANDLER;
}

void InstallCrashHandlers() {
  // Keep OS-level fault dialogs suppressed.
  SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
  SetUnhandledExceptionFilter(WriteCrashDump);

  // Tell the CRT not to pop its abort dialog: _WRITE_ABORT_MSG goes to stderr,
  // _CALL_REPORTFAULT is the behaviour that raises the interactive box.
  _set_abort_behavior(_WRITE_ABORT_MSG, _CALL_REPORTFAULT);

  // CRT assert/error reports (debug heap checks, STL iterator assertions, ...)
  // also pop modal dialogs by default - route them to stderr instead.
  for (int kind : {_CRT_ASSERT, _CRT_ERROR, _CRT_WARN}) {
    _CrtSetReportMode(kind, _CRTDBG_MODE_DEBUG | _CRTDBG_MODE_FILE);
    _CrtSetReportFile(kind, _CRTDBG_FILE_STDERR);
  }

  // An uncaught C++ exception on any thread (host code called from guest, a
  // fiber, etc.) would otherwise terminate silently. Log what it was, then
  // take the process down via the same abort path.
  std::set_terminate([]() {
    if (std::current_exception()) {
      try {
        std::rethrow_exception(std::current_exception());
      } catch (const std::exception& e) {
        fprintf(stderr, "UNCAUGHT EXCEPTION: %s\n", e.what());
        fflush(stderr);
      } catch (...) {
        fprintf(stderr, "UNCAUGHT EXCEPTION: unknown (non-std) exception\n");
        fflush(stderr);
      }
    } else {
      fprintf(stderr, "std::terminate called without an active exception\n");
      fflush(stderr);
    }
    std::abort();
  });
}

// A class type, because __attribute__((init_priority)) only applies to
// file-scope objects of class type. Runs before any other static initialiser
// in the image, so the handlers are in place before the guest can fault.
__attribute__((init_priority(101))) struct CrashHandlerInstaller {
  CrashHandlerInstaller() { InstallCrashHandlers(); }
} g_crash_handler_installer;

}  // namespace
#endif

REX_DEFINE_APP(forzahorizon, ForzaHorizonApp::Create)
