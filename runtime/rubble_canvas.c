/*
 * Rubble Canvas Library — rubble_canvas.c
 * Provides a simple windowed drawing surface via Win32 GDI (Windows)
 * or X11 (Linux). This is the C backend for the `canvas` stdlib module.
 *
 * Rubble API:
 *   canvas.open(title: text, width: unit, height: unit) -> unit  (window handle)
 *   canvas.clear(win: unit, r: unit, g: unit, b: unit)
 *   canvas.rect(win: unit, x: unit, y: unit, w: unit, h: unit, r: unit, g: unit, b: unit)
 *   canvas.circle(win: unit, cx: unit, cy: unit, radius: unit, r: unit, g: unit, b: unit)
 *   canvas.line(win: unit, x1: unit, y1: unit, x2: unit, y2: unit, r: unit, g: unit, b: unit)
 *   canvas.text(win: unit, x: unit, y: unit, msg: text, r: unit, g: unit, b: unit)
 *   canvas.show(win: unit)          -- flush / present the frame
 *   canvas.poll(win: unit) -> unit  -- pump events, returns 0 if window closed
 *   canvas.close(win: unit)
 */

#define _CRT_SECURE_NO_WARNINGS
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

/* =========================================================================
 * WINDOWS IMPLEMENTATION (Win32 GDI double-buffer)
 * ========================================================================= */
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#define MAX_WINDOWS 16
#define KEY_TABLE_SIZE 256

typedef struct {
    HWND     hwnd;
    HDC      hdc_back;
    HBITMAP  hbmp;
    int      width;
    int      height;
    int      alive;
    int      fill_solid;             /* 1 = solid (default), 0 = outline */
    int      font_size;              /* current font height in points     */
    HFONT    hfont;                  /* current GDI font object           */
    /* Input state */
    int      keys[KEY_TABLE_SIZE];   /* 1 = currently held down           */
    int      keys_prev[KEY_TABLE_SIZE]; /* keys state of previous frame   */
    int      mouse_x;
    int      mouse_y;
    int      mouse_left;
    int      mouse_right;
    int      mouse_middle;
    int      mouse_scroll_delta;     /* accumulated scroll delta          */
    /* Frame timing */
    LARGE_INTEGER last_frame_time;
    LARGE_INTEGER timer_freq;
} RblWindow;

static RblWindow _wins[MAX_WINDOWS];
static int       _wins_init = 0;
static HINSTANCE _hinstance = NULL;
static const char *WNDCLASS_NAME = "RubbleCanvas";

/* Forward declaration */
static LRESULT CALLBACK _wnd_proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp);

static void _ensure_init(void) {
    if (_wins_init) return;
    _wins_init = 1;
    memset(_wins, 0, sizeof(_wins));
    _hinstance = GetModuleHandle(NULL);

    WNDCLASSEXA wc = {0};
    wc.cbSize        = sizeof(wc);
    wc.style         = CS_HREDRAW | CS_VREDRAW;
    wc.lpfnWndProc   = _wnd_proc;
    wc.hInstance     = _hinstance;
    wc.hCursor       = LoadCursor(NULL, IDC_ARROW);
    wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
    wc.lpszClassName = WNDCLASS_NAME;
    RegisterClassExA(&wc);
}

static LRESULT CALLBACK _wnd_proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    /* Find the window slot */
    RblWindow *w = NULL;
    for (int i = 0; i < MAX_WINDOWS; i++) {
        if (_wins[i].hwnd == hwnd) { w = &_wins[i]; break; }
    }

    if (msg == WM_DESTROY || msg == WM_CLOSE) {
        if (w) w->alive = 0;
        PostQuitMessage(0);
        return 0;
    }
    if (msg == WM_PAINT) {
        PAINTSTRUCT ps;
        HDC hdc = BeginPaint(hwnd, &ps);
        if (w && w->hdc_back) {
            BitBlt(hdc, 0, 0, w->width, w->height, w->hdc_back, 0, 0, SRCCOPY);
        }
        EndPaint(hwnd, &ps);
        return 0;
    }
    /* Keyboard */
    if (msg == WM_KEYDOWN && w) {
        if (wp < KEY_TABLE_SIZE) w->keys[(int)wp] = 1;
        return 0;
    }
    if (msg == WM_KEYUP && w) {
        if (wp < KEY_TABLE_SIZE) w->keys[(int)wp] = 0;
        return 0;
    }
    if (msg == WM_MOUSEWHEEL && w) {
        w->mouse_scroll_delta += GET_WHEEL_DELTA_WPARAM(wp) / WHEEL_DELTA;
        return 0;
    }
    /* Mouse movement */
    if (msg == WM_MOUSEMOVE && w) {
        w->mouse_x = (int)LOWORD(lp);
        w->mouse_y = (int)HIWORD(lp);
        return 0;
    }
    /* Mouse buttons */
    if (msg == WM_LBUTTONDOWN && w) { w->mouse_left   = 1; return 0; }
    if (msg == WM_LBUTTONUP   && w) { w->mouse_left   = 0; return 0; }
    if (msg == WM_RBUTTONDOWN && w) { w->mouse_right  = 1; return 0; }
    if (msg == WM_RBUTTONUP   && w) { w->mouse_right  = 0; return 0; }
    if (msg == WM_MBUTTONDOWN && w) { w->mouse_middle = 1; return 0; }
    if (msg == WM_MBUTTONUP   && w) { w->mouse_middle = 0; return 0; }

    return DefWindowProcA(hwnd, msg, wp, lp);
}

int64_t rubble_canvas_open(const char *title, int64_t width, int64_t height) {
    _ensure_init();
    int slot = -1;
    for (int i = 0; i < MAX_WINDOWS; i++) {
        if (!_wins[i].alive) { slot = i; break; }
    }
    if (slot < 0) return -1;

    RECT r = {0, 0, (LONG)width, (LONG)height};
    AdjustWindowRect(&r, WS_OVERLAPPEDWINDOW, FALSE);

    HWND hwnd = CreateWindowExA(0, WNDCLASS_NAME, title,
        WS_OVERLAPPEDWINDOW | WS_VISIBLE,
        CW_USEDEFAULT, CW_USEDEFAULT,
        r.right - r.left, r.bottom - r.top,
        NULL, NULL, _hinstance, NULL);
    if (!hwnd) return -1;

    HDC hdc_screen = GetDC(hwnd);
    HDC hdc_back   = CreateCompatibleDC(hdc_screen);
    HBITMAP hbmp   = CreateCompatibleBitmap(hdc_screen, (int)width, (int)height);
    SelectObject(hdc_back, hbmp);
    ReleaseDC(hwnd, hdc_screen);

    _wins[slot].hwnd     = hwnd;
    _wins[slot].hdc_back = hdc_back;
    _wins[slot].hbmp     = hbmp;
    _wins[slot].width    = (int)width;
    _wins[slot].height   = (int)height;
    _wins[slot].alive    = 1;
    _wins[slot].fill_solid = 1;
    _wins[slot].font_size  = 0;
    _wins[slot].hfont      = NULL;
    _wins[slot].mouse_scroll_delta = 0;
    QueryPerformanceFrequency(&_wins[slot].timer_freq);
    QueryPerformanceCounter(&_wins[slot].last_frame_time);
    return (int64_t)slot;
}

static RblWindow *_get(int64_t handle) {
    if (handle < 0 || handle >= MAX_WINDOWS) return NULL;
    if (!_wins[handle].alive) return NULL;
    return &_wins[handle];
}

static COLORREF _rgb(int64_t r, int64_t g, int64_t b) {
    return RGB((BYTE)r, (BYTE)g, (BYTE)b);
}

void rubble_canvas_clear(int64_t handle, int64_t r, int64_t g, int64_t b) {
    RblWindow *w = _get(handle);
    if (!w) return;
    RECT rect = {0, 0, w->width, w->height};
    HBRUSH br = CreateSolidBrush(_rgb(r, g, b));
    FillRect(w->hdc_back, &rect, br);
    DeleteObject(br);
}

void rubble_canvas_rect(int64_t handle,
    int64_t x, int64_t y, int64_t ww, int64_t hh,
    int64_t r, int64_t g, int64_t b)
{
    RblWindow *w = _get(handle);
    if (!w) return;
    HBRUSH br   = w->fill_solid ? CreateSolidBrush(_rgb(r, g, b)) : (HBRUSH)GetStockObject(NULL_BRUSH);
    HPEN   pen  = CreatePen(PS_SOLID, 1, _rgb(r, g, b));
    HPEN   old_pen = SelectObject(w->hdc_back, pen);
    HBRUSH old_br  = SelectObject(w->hdc_back, br);
    Rectangle(w->hdc_back, (int)x, (int)y, (int)(x+ww), (int)(y+hh));
    SelectObject(w->hdc_back, old_pen);
    SelectObject(w->hdc_back, old_br);
    if (w->fill_solid) DeleteObject(br);
    DeleteObject(pen);
}

void rubble_canvas_circle(int64_t handle,
    int64_t cx, int64_t cy, int64_t radius,
    int64_t r, int64_t g, int64_t b)
{
    RblWindow *w = _get(handle);
    if (!w) return;
    HBRUSH br   = w->fill_solid ? CreateSolidBrush(_rgb(r, g, b)) : (HBRUSH)GetStockObject(NULL_BRUSH);
    HPEN   pen  = CreatePen(PS_SOLID, 1, _rgb(r, g, b));
    HPEN   old_pen = SelectObject(w->hdc_back, pen);
    HBRUSH old_br  = SelectObject(w->hdc_back, br);
    Ellipse(w->hdc_back,
        (int)(cx - radius), (int)(cy - radius),
        (int)(cx + radius), (int)(cy + radius));
    SelectObject(w->hdc_back, old_pen);
    SelectObject(w->hdc_back, old_br);
    if (w->fill_solid) DeleteObject(br);
    DeleteObject(pen);
}

void rubble_canvas_line(int64_t handle,
    int64_t x1, int64_t y1, int64_t x2, int64_t y2,
    int64_t r, int64_t g, int64_t b)
{
    RblWindow *w = _get(handle);
    if (!w) return;
    HPEN pen     = CreatePen(PS_SOLID, 1, _rgb(r, g, b));
    HPEN old_pen = SelectObject(w->hdc_back, pen);
    MoveToEx(w->hdc_back, (int)x1, (int)y1, NULL);
    LineTo(w->hdc_back, (int)x2, (int)y2);
    SelectObject(w->hdc_back, old_pen);
    DeleteObject(pen);
}

void rubble_canvas_text(int64_t handle,
    int64_t x, int64_t y, const char *msg,
    int64_t r, int64_t g, int64_t b)
{
    RblWindow *w = _get(handle);
    if (!w) return;
    SetTextColor(w->hdc_back, _rgb(r, g, b));
    SetBkMode(w->hdc_back, TRANSPARENT);
    TextOutA(w->hdc_back, (int)x, (int)y, msg, (int)strlen(msg));
}

void rubble_canvas_show(int64_t handle) {
    RblWindow *w = _get(handle);
    if (!w) return;
    HDC hdc = GetDC(w->hwnd);
    BitBlt(hdc, 0, 0, w->width, w->height, w->hdc_back, 0, 0, SRCCOPY);
    ReleaseDC(w->hwnd, hdc);
}

/* poll is defined later (after _advance_frame_state) so it can call it */

void rubble_canvas_close(int64_t handle) {
    RblWindow *w = _get(handle);
    if (!w) return;
    DeleteDC(w->hdc_back);
    DeleteObject(w->hbmp);
    DestroyWindow(w->hwnd);
    w->alive = 0;
}

/* ── Input query functions ─────────────────────────────────────────────── */

/* Returns 1 if the key with the given Windows Virtual Key code is held down.
 * Common key codes:
 *   65-90  = A-Z,  48-57 = 0-9
 *   VK_LEFT=37, VK_RIGHT=39, VK_UP=38, VK_DOWN=40
 *   VK_SPACE=32, VK_RETURN=13, VK_ESCAPE=27, VK_SHIFT=16, VK_CONTROL=17
 */
int64_t rubble_canvas_key(int64_t handle, int64_t keycode) {
    RblWindow *w = _get(handle);
    if (!w) return 0;
    if (keycode < 0 || keycode >= KEY_TABLE_SIZE) return 0;
    return w->keys[(int)keycode] ? 1 : 0;
}

int64_t rubble_canvas_mouse_x(int64_t handle) {
    RblWindow *w = _get(handle);
    return w ? (int64_t)w->mouse_x : 0;
}

int64_t rubble_canvas_mouse_y(int64_t handle) {
    RblWindow *w = _get(handle);
    return w ? (int64_t)w->mouse_y : 0;
}

/* btn: 0 = left, 1 = right, 2 = middle */
int64_t rubble_canvas_mouse_btn(int64_t handle, int64_t btn) {
    RblWindow *w = _get(handle);
    if (!w) return 0;
    if (btn == 0) return w->mouse_left;
    if (btn == 1) return w->mouse_right;
    if (btn == 2) return w->mouse_middle;
    return 0;
}

/* ── New canvas functions ─────────────────────────────────────────────── */

/* key_just_pressed — true only on the first frame the key went down */
int rubble_canvas_key_just_pressed(int64_t handle, int64_t keycode) {
    RblWindow *w = _get(handle);
    if (!w) return 0;
    if (keycode < 0 || keycode >= KEY_TABLE_SIZE) return 0;
    return (w->keys[(int)keycode] && !w->keys_prev[(int)keycode]) ? 1 : 0;
}

/* Call once per frame (after poll) to advance key_just_pressed state */
static void _advance_frame_state(RblWindow *w) {
    memcpy(w->keys_prev, w->keys, sizeof(w->keys));
    w->mouse_scroll_delta = 0;
}

/* mouse_scroll — wheel delta since last poll */
int64_t rubble_canvas_mouse_scroll(int64_t handle) {
    RblWindow *w = _get(handle);
    return w ? (int64_t)w->mouse_scroll_delta : 0;
}

/* fill_mode — mode 1 = solid, mode 0 = outline */
void rubble_canvas_fill_mode(int64_t handle, int64_t mode) {
    RblWindow *w = _get(handle);
    if (w) w->fill_solid = (mode != 0) ? 1 : 0;
}

/* set_title */
void rubble_canvas_set_title(int64_t handle, const char *title) {
    RblWindow *w = _get(handle);
    if (w) SetWindowTextA(w->hwnd, title);
}

/* resize */
void rubble_canvas_resize(int64_t handle, int64_t new_w, int64_t new_h) {
    RblWindow *w = _get(handle);
    if (!w) return;
    /* Recreate backbuffer */
    DeleteDC(w->hdc_back);
    DeleteObject(w->hbmp);
    HDC hdc_screen = GetDC(w->hwnd);
    w->hdc_back = CreateCompatibleDC(hdc_screen);
    w->hbmp     = CreateCompatibleBitmap(hdc_screen, (int)new_w, (int)new_h);
    SelectObject(w->hdc_back, w->hbmp);
    ReleaseDC(w->hwnd, hdc_screen);
    w->width  = (int)new_w;
    w->height = (int)new_h;
    RECT r = {0, 0, (LONG)new_w, (LONG)new_h};
    AdjustWindowRect(&r, WS_OVERLAPPEDWINDOW, FALSE);
    SetWindowPos(w->hwnd, NULL, 0, 0,
        r.right - r.left, r.bottom - r.top,
        SWP_NOMOVE | SWP_NOZORDER);
}

/* fullscreen toggle */
void rubble_canvas_fullscreen(int64_t handle) {
    RblWindow *w = _get(handle);
    if (!w) return;
    static int _fs = 0;
    _fs = !_fs;
    if (_fs) {
        SetWindowLongA(w->hwnd, GWL_STYLE, WS_POPUP | WS_VISIBLE);
        ShowWindow(w->hwnd, SW_SHOWMAXIMIZED);
    } else {
        SetWindowLongA(w->hwnd, GWL_STYLE, WS_OVERLAPPEDWINDOW | WS_VISIBLE);
        ShowWindow(w->hwnd, SW_RESTORE);
    }
}

/* delta_time — seconds since last call */
double rubble_canvas_delta_time(int64_t handle) {
    RblWindow *w = _get(handle);
    if (!w) return 0.0;
    LARGE_INTEGER now;
    QueryPerformanceCounter(&now);
    double dt = (double)(now.QuadPart - w->last_frame_time.QuadPart)
                / (double)w->timer_freq.QuadPart;
    w->last_frame_time = now;
    /* Clamp to avoid spiral-of-death on first frame / pause */
    if (dt > 0.25) dt = 0.25;
    return dt;
}

/* font_size — change text rendering size */
void rubble_canvas_font_size(int64_t handle, int64_t size) {
    RblWindow *w = _get(handle);
    if (!w) return;
    if (w->hfont) { DeleteObject(w->hfont); w->hfont = NULL; }
    w->font_size = (int)size;
    if (size > 0) {
        w->hfont = CreateFontA(
            (int)size, 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE,
            ANSI_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
            DEFAULT_QUALITY, DEFAULT_PITCH | FF_SWISS, "Arial");
        if (w->hfont) SelectObject(w->hdc_back, w->hfont);
    }
}

/* Override canvas_poll to also advance frame state */
/* (Redefine — the original is before this block, so we shadow with a wrapper) */
/* We patch poll to call _advance_frame_state */
int64_t rubble_canvas_poll(int64_t handle) {
    RblWindow *w = _get(handle);
    if (!w) return 0;
    _advance_frame_state(w);
    MSG msg;
    while (PeekMessage(&msg, NULL, 0, 0, PM_REMOVE)) {
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }
    return w->alive ? 1 : 0;
}

/* ── Image loading (BMP only via LoadImage; PNG requires 3rd-party lib) ── */

#define MAX_IMAGES 256
typedef struct { HBITMAP hbmp; int width; int height; } RblImage;
static RblImage _images[MAX_IMAGES];
static int _images_init = 0;

static void _ensure_images_init(void) {
    if (_images_init) return;
    _images_init = 1;
    memset(_images, 0, sizeof(_images));
}

int64_t rubble_canvas_image_load(const char *path) {
    _ensure_images_init();
    for (int i = 0; i < MAX_IMAGES; i++) {
        if (!_images[i].hbmp) {
            HBITMAP hbmp = (HBITMAP)LoadImageA(NULL, path, IMAGE_BITMAP,
                                               0, 0, LR_LOADFROMFILE);
            if (!hbmp) return -1;
            BITMAP bm;
            GetObject(hbmp, sizeof(bm), &bm);
            _images[i].hbmp   = hbmp;
            _images[i].width  = bm.bmWidth;
            _images[i].height = bm.bmHeight;
            return (int64_t)i;
        }
    }
    return -1;
}

void rubble_canvas_image_draw(int64_t win_handle, int64_t img_handle,
                               int64_t x, int64_t y) {
    RblWindow *w = _get(win_handle);
    if (!w || img_handle < 0 || img_handle >= MAX_IMAGES) return;
    RblImage *img = &_images[img_handle];
    if (!img->hbmp) return;
    HDC hdc_mem = CreateCompatibleDC(w->hdc_back);
    HBITMAP old  = SelectObject(hdc_mem, img->hbmp);
    BitBlt(w->hdc_back, (int)x, (int)y, img->width, img->height,
           hdc_mem, 0, 0, SRCCOPY);
    SelectObject(hdc_mem, old);
    DeleteDC(hdc_mem);
}

/* =========================================================================
 * LINUX / macOS STUBS — canvas not yet implemented on non-Windows
 * ========================================================================= */
#else

int64_t rubble_canvas_open(const char *title, int64_t w, int64_t h) {
    fprintf(stderr, "[canvas] Non-Windows backend not yet implemented\n");
    return -1;
}
void    rubble_canvas_clear(int64_t h, int64_t r, int64_t g, int64_t b) {}
void    rubble_canvas_rect(int64_t h, int64_t x, int64_t y, int64_t w, int64_t hh, int64_t r, int64_t g, int64_t b) {}
void    rubble_canvas_circle(int64_t h, int64_t cx, int64_t cy, int64_t rad, int64_t r, int64_t g, int64_t b) {}
void    rubble_canvas_line(int64_t h, int64_t x1, int64_t y1, int64_t x2, int64_t y2, int64_t r, int64_t g, int64_t b) {}
void    rubble_canvas_text(int64_t h, int64_t x, int64_t y, const char *msg, int64_t r, int64_t g, int64_t b) {}
void    rubble_canvas_show(int64_t h) {}
int64_t rubble_canvas_poll(int64_t h) { return 0; }
void    rubble_canvas_close(int64_t h) {}
int64_t rubble_canvas_key(int64_t h, int64_t k) { return 0; }
int     rubble_canvas_key_just_pressed(int64_t h, int64_t k) { return 0; }
int64_t rubble_canvas_mouse_x(int64_t h) { return 0; }
int64_t rubble_canvas_mouse_y(int64_t h) { return 0; }
int64_t rubble_canvas_mouse_btn(int64_t h, int64_t b) { return 0; }
int64_t rubble_canvas_mouse_scroll(int64_t h) { return 0; }
void    rubble_canvas_fill_mode(int64_t h, int64_t m) {}
void    rubble_canvas_set_title(int64_t h, const char *t) {}
void    rubble_canvas_resize(int64_t h, int64_t w, int64_t hh) {}
void    rubble_canvas_fullscreen(int64_t h) {}
double  rubble_canvas_delta_time(int64_t h) { return 0.016; }
int64_t rubble_canvas_image_load(const char *path) { return -1; }
void    rubble_canvas_image_draw(int64_t w, int64_t img, int64_t x, int64_t y) {}
void    rubble_canvas_font_size(int64_t h, int64_t sz) {}

#endif
