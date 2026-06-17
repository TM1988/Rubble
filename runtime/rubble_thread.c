/*
 * Rubble thread module — rubble_thread.c
 *
 * Rubble API:
 *   thread.spawn(recipe) -> unit   (handle)
 *   thread.join(handle)
 *
 * The recipe passed to spawn must have signature:  recipe name() { ... }
 * (no arguments, no return value — matches a void (*)(void) C function pointer).
 *
 * Windows: Win32 CreateThread
 * POSIX:   pthreads
 */

#define _CRT_SECURE_NO_WARNINGS
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define MAX_THREADS 64

#ifdef _WIN32
  #define WIN32_LEAN_AND_MEAN
  #include <windows.h>
  typedef HANDLE rbl_thread_t;
  #define RBL_THREAD_INVALID NULL
#else
  #include <pthread.h>
  typedef pthread_t rbl_thread_t;
  #define RBL_THREAD_INVALID (pthread_t)0
#endif

static rbl_thread_t _threads[MAX_THREADS];
static int          _threads_init = 0;

static void _ensure_init(void) {
    if (_threads_init) return;
    _threads_init = 1;
    memset(_threads, 0, sizeof(_threads));
}

typedef void (*rbl_fn_t)(void);

#ifdef _WIN32
static DWORD WINAPI _thread_trampoline(LPVOID param) {
    rbl_fn_t fn = (rbl_fn_t)param;
    fn();
    return 0;
}
#else
static void *_thread_trampoline(void *param) {
    rbl_fn_t fn = (rbl_fn_t)param;
    fn();
    return NULL;
}
#endif

int64_t rubble_thread_spawn(void *fn_ptr) {
    _ensure_init();
    for (int i = 0; i < MAX_THREADS; i++) {
#ifdef _WIN32
        if (_threads[i] == RBL_THREAD_INVALID) {
            HANDLE h = CreateThread(NULL, 0, _thread_trampoline, fn_ptr, 0, NULL);
            if (!h) return -1;
            _threads[i] = h;
            return (int64_t)i;
        }
#else
        if (_threads[i] == (pthread_t)0) {
            pthread_t t;
            if (pthread_create(&t, NULL, _thread_trampoline, fn_ptr) != 0) return -1;
            _threads[i] = t;
            return (int64_t)i;
        }
#endif
    }
    return -1;
}

void rubble_thread_join(int64_t handle) {
    if (handle < 0 || handle >= MAX_THREADS) return;
#ifdef _WIN32
    if (_threads[handle]) {
        WaitForSingleObject(_threads[handle], INFINITE);
        CloseHandle(_threads[handle]);
        _threads[handle] = NULL;
    }
#else
    if (_threads[handle] != (pthread_t)0) {
        pthread_join(_threads[handle], NULL);
        _threads[handle] = (pthread_t)0;
    }
#endif
}
