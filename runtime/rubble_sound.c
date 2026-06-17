/*
 * Rubble sound module — rubble_sound.c
 *
 * Rubble API:
 *   sound.load(path)         -> unit   (handle)
 *   sound.play(handle)
 *   sound.stop(handle)
 *
 * Windows: uses PlaySound / MCI for .wav files.
 * Linux: uses system("aplay ...") as a minimal fallback.
 * macOS: uses system("afplay ...") as a minimal fallback.
 */

#define _CRT_SECURE_NO_WARNINGS
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

#define MAX_SOUNDS 64

static char *_sound_paths[MAX_SOUNDS];
static int   _sound_init = 0;

static void _ensure_init(void) {
    if (_sound_init) return;
    _sound_init = 1;
    for (int i = 0; i < MAX_SOUNDS; i++) _sound_paths[i] = NULL;
}

int64_t rubble_sound_load(const char *path) {
    _ensure_init();
    for (int i = 0; i < MAX_SOUNDS; i++) {
        if (_sound_paths[i] == NULL) {
            _sound_paths[i] = strdup(path);
            return (int64_t)i;
        }
    }
    return -1;  /* No free slot */
}

void rubble_sound_play(int64_t handle) {
    if (handle < 0 || handle >= MAX_SOUNDS) return;
    const char *path = _sound_paths[handle];
    if (!path) return;

#ifdef _WIN32
    /* PlaySoundA plays asynchronously (SND_ASYNC) */
    #include <windows.h>
    #pragma comment(lib, "winmm.lib")
    PlaySoundA(path, NULL, SND_FILENAME | SND_ASYNC | SND_NODEFAULT);
#elif defined(__APPLE__)
    char cmd[4096];
    snprintf(cmd, sizeof(cmd), "afplay \"%s\" &", path);
    system(cmd);
#else
    char cmd[4096];
    snprintf(cmd, sizeof(cmd), "aplay \"%s\" &", path);
    system(cmd);
#endif
}

void rubble_sound_stop(int64_t handle) {
    (void)handle;
#ifdef _WIN32
    #include <windows.h>
    PlaySoundA(NULL, NULL, 0);  /* Stops currently playing async sound */
#endif
    /* Linux/macOS: killing background process is complex — no-op for now */
}
