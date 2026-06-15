/*
 * Rubble Runtime Standard Library
 * Implements the C-side stubs that Rubble's compiled IR calls into.
 * Compile alongside your .ll file:
 *   clang program.ll rubble_stdlib.c -o program -lm
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <unistd.h>

#ifdef _WIN32
  #include <winsock2.h>
  #include <ws2tcpip.h>
  #pragma comment(lib, "ws2_32.lib")
  typedef SOCKET rbl_sock_t;
#else
  #include <sys/socket.h>
  #include <netinet/in.h>
  #include <arpa/inet.h>
  #include <netdb.h>
  typedef int rbl_sock_t;
  #define INVALID_SOCKET (-1)
#endif

/* --------------------------------------------------------------------------
 * panel — user input
 * -------------------------------------------------------------------------- */

char *rubble_panel_prompt(const char *msg) {
    printf("%s", msg);
    fflush(stdout);
    return rubble_panel_grab();
}

char *rubble_panel_grab(void) {
    char buf[4096];
    if (!fgets(buf, sizeof(buf), stdin)) {
        return strdup("");
    }
    size_t len = strlen(buf);
    if (len > 0 && buf[len - 1] == '\n') buf[len - 1] = '\0';
    return strdup(buf);
}

/* --------------------------------------------------------------------------
 * machinery — OS / hardware
 * -------------------------------------------------------------------------- */

int64_t rubble_machinery_ram(void) {
#ifdef __linux__
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
#elif defined(__APPLE__)
    /* macOS: use sysctl */
    return 0;
#elif defined(_WIN32)
    MEMORYSTATUSEX ms;
    ms.dwLength = sizeof(ms);
    GlobalMemoryStatusEx(&ms);
    return (int64_t)ms.ullAvailPhys;
#else
    return 0;
#endif
}

/* --------------------------------------------------------------------------
 * cabinet — file system
 * -------------------------------------------------------------------------- */

/* Returns a file descriptor (as i64) for open/create operations.
 * Full directory listing requires a more complex crate return type;
 * we provide a simple stub here. */

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

void rubble_write(int64_t handle, const char *data) {
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
    /* Read entire file into a heap buffer */
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    rewind(f);
    char *buf = malloc(size + 1);
    if (!buf) return strdup("");
    fread(buf, 1, size, f);
    buf[size] = '\0';
    return buf;
}

/* --------------------------------------------------------------------------
 * cable — networking (TCP sockets)
 * -------------------------------------------------------------------------- */

/* Connection table — stores open sockets indexed by a handle int */
#define MAX_CONNECTIONS 64
static rbl_sock_t _conns[MAX_CONNECTIONS];
static int        _conns_init = 0;

static void _init_conns(void) {
    if (_conns_init) return;
    for (int i = 0; i < MAX_CONNECTIONS; i++) _conns[i] = INVALID_SOCKET;
    _conns_init = 1;
#ifdef _WIN32
    WSADATA wsa;
    WSAStartup(MAKEWORD(2,2), &wsa);
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
    struct addrinfo hints = {0}, *res = NULL;
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
