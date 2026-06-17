/*
 * Rubble Runtime Standard Library — Windows/Linux/macOS compatible
 * Compile alongside your .ll file:
 *   clang program.ll rubble_stdlib.c -o program
 */

#ifdef _MSC_VER
  #ifndef _CRT_SECURE_NO_WARNINGS
    #define _CRT_SECURE_NO_WARNINGS
  #endif
  #ifndef _CRT_NONSTDC_NO_WARNINGS
    #define _CRT_NONSTDC_NO_WARNINGS
  #endif
#endif

#ifdef _WIN32
  #define WIN32_LEAN_AND_MEAN
  #define VC_EXTRA_LEAN
  #include <windows.h>
  #include <winsock2.h>
  #include <ws2tcpip.h>
  typedef SOCKET rbl_sock_t;
  #define RBL_SLEEP(ms) Sleep((DWORD)(ms))
  #pragma comment(lib, "ws2_32.lib")
#else
  #include <unistd.h>
  #include <sys/socket.h>
  #include <netinet/in.h>
  #include <arpa/inet.h>
  #include <netdb.h>
  typedef int rbl_sock_t;
  #define INVALID_SOCKET (-1)
  #define RBL_SLEEP(ms) usleep((unsigned int)((ms) * 1000))
#endif

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <ctype.h>
#include <time.h>
#include <dirent.h>

/* Forward declarations */
char *rubble_panel_grab(void);

/* =========================================================================
 * panel — user input
 * ========================================================================= */

char *rubble_panel_prompt(const char *msg) {
    printf("%s", msg);
    fflush(stdout);
    return rubble_panel_grab();
}

char *rubble_panel_grab(void) {
    char buf[4096];
    if (!fgets(buf, sizeof(buf), stdin)) return strdup("");
    size_t len = strlen(buf);
    if (len > 0 && buf[len - 1] == '\n') buf[len - 1] = '\0';
    return strdup(buf);
}

/* =========================================================================
 * machinery — OS / hardware
 * ========================================================================= */

void rubble_machinery_rest(int64_t ms) {
    RBL_SLEEP(ms);
}

int64_t rubble_machinery_ram(void) {
#ifdef _WIN32
    MEMORYSTATUSEX ms;
    ms.dwLength = sizeof(ms);
    GlobalMemoryStatusEx(&ms);
    return (int64_t)ms.ullAvailPhys;
#elif defined(__linux__)
    FILE *f = fopen("/proc/meminfo", "r");
    if (!f) return 0;
    char line[256];
    while (fgets(line, sizeof(line), f)) {
        if (strncmp(line, "MemAvailable:", 13) == 0) {
            fclose(f);
            long kb = 0;
            sscanf(line + 13, "%ld", &kb);
            return (int64_t)kb * 1024;
        }
    }
    fclose(f);
    return 0;
#else
    return 0;
#endif
}

/* Returns current Unix timestamp in seconds */
int64_t rubble_machinery_time(void) {
    return (int64_t)time(NULL);
}

/* Get environment variable; returns "" if not set */
char *rubble_machinery_env(const char *name) {
    const char *v = getenv(name);
    return strdup(v ? v : "");
}

/* Get command-line arguments as an array; count written to *out_count.
 * We cache argc/argv set by rubble_init_args (called from main shim). */
static int   _rbl_argc = 0;
static char **_rbl_argv = NULL;

void rubble_init_args(int argc, char **argv) {
    _rbl_argc = argc;
    _rbl_argv = argv;
}

char **rubble_machinery_args(int64_t *out_count) {
    *out_count = (int64_t)_rbl_argc;
    return _rbl_argv;
}

/* =========================================================================
 * cabinet — file system
 * ========================================================================= */

int64_t rubble_cabinet_open(const char *path) {
    FILE *f = fopen(path, "r+");
    if (!f) return -1;
    return (int64_t)(intptr_t)f;
}

int64_t rubble_cabinet_create(const char *path) {
    FILE *f = fopen(path, "w");
    if (!f) return -1;
    return (int64_t)(intptr_t)f;
}

/* Read entire file into a heap-allocated string */
char *rubble_cabinet_read(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) return strdup("");
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    rewind(f);
    char *buf = (char *)malloc(size + 1);
    if (!buf) { fclose(f); return strdup(""); }
    fread(buf, 1, size, f);
    buf[size] = '\0';
    fclose(f);
    return buf;
}

/* Write entire string to file (overwrites) */
void rubble_cabinet_write(const char *path, const char *data) {
    FILE *f = fopen(path, "w");
    if (!f) return;
    fputs(data, f);
    fclose(f);
}

/* Check if file/directory exists */
int rubble_cabinet_exists(const char *path) {
#ifdef _WIN32
    return GetFileAttributesA(path) != INVALID_FILE_ATTRIBUTES ? 1 : 0;
#else
    struct stat st;
    return stat(path, &st) == 0 ? 1 : 0;
#endif
}

/* Delete a file */
void rubble_cabinet_delete(const char *path) {
    remove(path);
}

/* Legacy file-handle based API */
void rubble_file_write(int64_t handle, const char *data) {
    FILE *f = (FILE *)(intptr_t)handle;
    if (f) fputs(data, f);
}

void rubble_close(int64_t handle) {
    FILE *f = (FILE *)(intptr_t)handle;
    if (f) fclose(f);
}

char *rubble_read(int64_t handle) {
    FILE *f = (FILE *)(intptr_t)handle;
    if (!f) return strdup("");
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    rewind(f);
    char *buf = (char *)malloc(size + 1);
    if (!buf) return strdup("");
    fread(buf, 1, size, f);
    buf[size] = '\0';
    return buf;
}

/* =========================================================================
 * cabinet.list — directory listing
 *
 * The codegen calls rubble_cabinet_list_fill(path, crate_ptr) where
 * crate_ptr points to a { i64, i8** } struct (Crate_i8p).
 * ========================================================================= */

typedef struct { int64_t len; char **data; } RblCrateText;

void rubble_cabinet_list_fill(const char *path, RblCrateText *out) {
    out->len  = 0;
    out->data = NULL;

    size_t cap = 64;
    char **arr = (char **)malloc(cap * sizeof(char *));
    if (!arr) return;
    size_t count = 0;

#ifdef _WIN32
    char pattern[4096];
    snprintf(pattern, sizeof(pattern), "%s\\*", path);
    WIN32_FIND_DATAA fd;
    HANDLE h = FindFirstFileA(pattern, &fd);
    if (h == INVALID_HANDLE_VALUE) { free(arr); return; }
    do {
        if (strcmp(fd.cFileName, ".") == 0 || strcmp(fd.cFileName, "..") == 0) continue;
        if (count >= cap) { cap *= 2; arr = (char **)realloc(arr, cap * sizeof(char *)); }
        arr[count++] = strdup(fd.cFileName);
    } while (FindNextFileA(h, &fd));
    FindClose(h);
#else
    DIR *d = opendir(path);
    if (!d) { free(arr); return; }
    struct dirent *ent;
    while ((ent = readdir(d)) != NULL) {
        if (strcmp(ent->d_name, ".") == 0 || strcmp(ent->d_name, "..") == 0) continue;
        if (count >= cap) { cap *= 2; arr = (char **)realloc(arr, cap * sizeof(char *)); }
        arr[count++] = strdup(ent->d_name);
    }
    closedir(d);
#endif

    out->len  = (int64_t)count;
    out->data = arr;
}

/* =========================================================================
 * cable — networking (TCP sockets)
 * ========================================================================= */

#define MAX_CONNECTIONS 64
static rbl_sock_t _conns[MAX_CONNECTIONS];
static int        _conns_init = 0;

static void _init_conns(void) {
    if (_conns_init) return;
    for (int i = 0; i < MAX_CONNECTIONS; i++) _conns[i] = INVALID_SOCKET;
    _conns_init = 1;
#ifdef _WIN32
    WSADATA wsa;
    WSAStartup(MAKEWORD(2, 2), &wsa);
#endif
}

static int64_t _store_conn(rbl_sock_t s) {
    for (int i = 0; i < MAX_CONNECTIONS; i++) {
        if (_conns[i] == INVALID_SOCKET) {
            _conns[i] = s;
            return (int64_t)i;
        }
    }
    return -1;
}

int64_t rubble_cable_connect(const char *host, int64_t port) {
    _init_conns();
    struct addrinfo hints, *res = NULL;
    memset(&hints, 0, sizeof(hints));
    hints.ai_family   = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    char port_str[16];
    snprintf(port_str, sizeof(port_str), "%lld", (long long)port);
    if (getaddrinfo(host, port_str, &hints, &res) != 0) return -1;
    rbl_sock_t s = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
    if (s == INVALID_SOCKET) { freeaddrinfo(res); return -1; }
    if (connect(s, res->ai_addr, (int)res->ai_addrlen) != 0) {
#ifdef _WIN32
        closesocket(s);
#else
        close(s);
#endif
        freeaddrinfo(res);
        return -1;
    }
    freeaddrinfo(res);
    return _store_conn(s);
}

char *rubble_line_read(int64_t handle) {
    if (handle < 0 || handle >= MAX_CONNECTIONS) return strdup("");
    rbl_sock_t s = _conns[handle];
    if (s == INVALID_SOCKET) return strdup("");
    char buf[8192];
    int n = recv(s, buf, sizeof(buf) - 1, 0);
    if (n <= 0) return strdup("");
    buf[n] = '\0';
    return strdup(buf);
}

int rubble_status(int64_t handle) {
    if (handle < 0 || handle >= MAX_CONNECTIONS) return 0;
    return _conns[handle] != INVALID_SOCKET ? 1 : 0;
}

/* =========================================================================
 * text built-ins
 * ========================================================================= */

char *rubble_text_upper(const char *s) {
    char *r = strdup(s);
    if (!r) return strdup("");
    for (char *p = r; *p; p++) *p = (char)toupper((unsigned char)*p);
    return r;
}

char *rubble_text_lower(const char *s) {
    char *r = strdup(s);
    if (!r) return strdup("");
    for (char *p = r; *p; p++) *p = (char)tolower((unsigned char)*p);
    return r;
}

char *rubble_text_trim(const char *s) {
    while (isspace((unsigned char)*s)) s++;
    size_t len = strlen(s);
    while (len > 0 && isspace((unsigned char)s[len - 1])) len--;
    char *r = (char *)malloc(len + 1);
    if (!r) return strdup("");
    memcpy(r, s, len);
    r[len] = '\0';
    return r;
}

char *rubble_text_replace(const char *s, const char *old_sub, const char *new_sub) {
    size_t s_len   = strlen(s);
    size_t old_len = strlen(old_sub);
    size_t new_len = strlen(new_sub);
    if (old_len == 0) return strdup(s);

    /* Count occurrences */
    size_t count = 0;
    const char *p = s;
    while ((p = strstr(p, old_sub)) != NULL) { count++; p += old_len; }

    size_t result_len = s_len + count * (new_len - old_len);
    char *result = (char *)malloc(result_len + 1);
    if (!result) return strdup(s);

    char *dst = result;
    p = s;
    const char *match;
    while ((match = strstr(p, old_sub)) != NULL) {
        size_t before = match - p;
        memcpy(dst, p, before);
        dst += before;
        memcpy(dst, new_sub, new_len);
        dst += new_len;
        p = match + old_len;
    }
    strcpy(dst, p);
    return result;
}

/* slice(s, start, end) — returns heap-allocated substring [start, end) */
char *rubble_text_slice(const char *s, int64_t start, int64_t end) {
    int64_t len = (int64_t)strlen(s);
    if (start < 0) start = 0;
    if (end > len) end = len;
    if (start >= end) return strdup("");
    size_t sz = (size_t)(end - start);
    char *r = (char *)malloc(sz + 1);
    if (!r) return strdup("");
    memcpy(r, s + start, sz);
    r[sz] = '\0';
    return r;
}

/* index(s, sub) — returns byte position of first occurrence, or -1 */
int64_t rubble_text_index(const char *s, const char *sub) {
    const char *p = strstr(s, sub);
    return p ? (int64_t)(p - s) : (int64_t)-1;
}

/* split(s, sep) — returns array of heap-allocated strings; writes count */
char **rubble_text_split(const char *s, const char *sep, int64_t *out_count) {
    size_t sep_len = strlen(sep);
    size_t cap = 16;
    char **arr = (char **)malloc(cap * sizeof(char *));
    if (!arr) { *out_count = 0; return NULL; }
    size_t count = 0;

    if (sep_len == 0) {
        /* Split on every character */
        for (size_t i = 0; s[i]; i++) {
            if (count >= cap) { cap *= 2; arr = (char **)realloc(arr, cap * sizeof(char *)); }
            char tmp[2] = { s[i], '\0' };
            arr[count++] = strdup(tmp);
        }
    } else {
        const char *p = s;
        const char *match;
        while ((match = strstr(p, sep)) != NULL) {
            if (count >= cap) { cap *= 2; arr = (char **)realloc(arr, cap * sizeof(char *)); }
            size_t part_len = match - p;
            char *part = (char *)malloc(part_len + 1);
            memcpy(part, p, part_len);
            part[part_len] = '\0';
            arr[count++] = part;
            p = match + sep_len;
        }
        /* Tail */
        if (count >= cap) { cap += 1; arr = (char **)realloc(arr, cap * sizeof(char *)); }
        arr[count++] = strdup(p);
    }

    *out_count = (int64_t)count;
    return arr;
}

/* =========================================================================
 * crate helpers
 * ========================================================================= */

/* Sort an array of i64 in place using insertion sort (simple, no stdlib dependency) */
void rubble_crate_sort_i64(void *data, int64_t len) {
    int64_t *arr = (int64_t *)data;
    for (int64_t i = 1; i < len; i++) {
        int64_t key = arr[i];
        int64_t j = i - 1;
        while (j >= 0 && arr[j] > key) {
            arr[j + 1] = arr[j];
            j--;
        }
        arr[j + 1] = key;
    }
}

/* Reverse an array of elements of elem_size bytes in place */
void rubble_crate_reverse(void *data, int64_t len, int64_t elem_size) {
    char *arr = (char *)data;
    char *tmp = (char *)malloc((size_t)elem_size);
    if (!tmp) return;
    int64_t left = 0, right = len - 1;
    while (left < right) {
        memcpy(tmp,                    arr + left * elem_size,  elem_size);
        memcpy(arr + left * elem_size, arr + right * elem_size, elem_size);
        memcpy(arr + right * elem_size, tmp,                    elem_size);
        left++;  right--;
    }
    free(tmp);
}

/* Join an array of C strings with a separator */
char *rubble_crate_join(char **arr, int64_t len, const char *sep) {
    if (len == 0) return strdup("");
    size_t sep_len = strlen(sep);
    size_t total = 0;
    for (int64_t i = 0; i < len; i++) total += strlen(arr[i]);
    total += (size_t)(len > 0 ? (len - 1) * sep_len : 0) + 1;
    char *result = (char *)malloc(total);
    if (!result) return strdup("");
    result[0] = '\0';
    for (int64_t i = 0; i < len; i++) {
        strcat(result, arr[i]);
        if (i < len - 1) strcat(result, sep);
    }
    return result;
}
