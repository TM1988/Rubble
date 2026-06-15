# Rubble Language Roadmap

Full audit of missing features compared to modern languages. Grouped by priority.

---

## 🔴 Core Language — Missing Basics

**Control flow**
- `else if` chaining works, but no `switch/match` statement (pattern matching on a value)
- No `continue` (skip to next loop iteration — we only have `jam` for break)
- No labeled breaks (break out of a specific outer loop)

**Types & expressions**
- No string interpolation — you have to write `"x = " + smelt(x, text)` instead of `"x = {x}"`
- No multi-return from recipes (have to use a blueprint as a workaround)
- No default parameter values in recipes
- No variadic recipes (`...args`)
- No `unit` size variants (i8, i16, i32 — only i64 right now)
- No unsigned integers

**Memory**
- No heap-allocated blueprints — `build` currently allocates on the stack, meaning blueprints can't escape a function or be stored in a crate

---

## 🟡 Standard Library — Obvious Gaps

**`machinery` (OS)**
- `machinery.rest(ms)` — **this is the "wait" command**, it already exists but takes milliseconds. Worth checking the docs are clear
- `machinery.time()` — get current Unix timestamp
- `machinery.args()` — get command-line arguments as `crate[text]`
- `machinery.env(name)` — get environment variable
- `machinery.exit(code)` — exit with a specific code (halt always uses 1)

**`text` built-ins**
- `t.split(sep)` — split string by separator → `crate[text]` (type checker has it, codegen doesn't)
- `t.replace(old, new)` — string replace
- `t.index(sub)` — find substring position
- `t.slice(start, end)` — substring
- `t.upper()` / `t.lower()` — (type checker has these, codegen doesn't)

**`crate` built-ins**
- `c.slice(start, end)` — sub-array
- `c.sort()` — sort in place
- `c.reverse()` — reverse in place
- `c.join(sep)` — join text crate into a single text

**`cabinet` (file system)**
- `cabinet.read(path)` — read entire file as text in one call
- `cabinet.write(path, data)` — write entire file in one call
- `cabinet.exists(path)` — check if file exists
- `cabinet.delete(path)` — delete a file
- `cabinet.list(path)` — exists but codegen returns null (not wired up yet)

**New modules**
- `rand` — random numbers (`rand.int(min, max)`, `rand.decimal()`, `rand.seed(n)`)
- `time` — date/time (`time.now()`, `time.format(ts, fmt)`)
- `thread` — basic threading (`thread.spawn(recipe)`, `thread.join()`)
- `json` — parse/emit JSON (needed for any web/config work)

---

## 🟢 Canvas — Missing for Games/OS

- `canvas.fill_mode(win, mode)` — solid vs outline shapes
- `canvas.key_just_pressed(win, key)` — pressed this frame only (vs held)
- `canvas.mouse_scroll(win)` — scroll wheel delta
- `canvas.set_title(win, text)` — change window title at runtime
- `canvas.resize(win, w, h)` — resize window
- `canvas.fullscreen(win)` — toggle fullscreen
- `canvas.image_load(path)` — load a PNG/BMP
- `canvas.image_draw(win, img, x, y)` — blit an image
- `canvas.font_size(win, size)` — change text size
- `canvas.delta_time()` — time since last frame (essential for games)
- Audio: `sound.load(path)`, `sound.play(handle)`, `sound.stop(handle)`

---

## 🔵 Tooling

- `rubble --version` — show language version
- Syntax highlighting definitions (VS Code extension, `.tmLanguage`)
- A package manager / `gather` from URL or registry
- `rubble fmt file.rbl` — auto-formatter
- Error messages with line/column + source snippet (right now errors show line:col but no source preview)
- REPL (`rubble --repl`)

---

## Priority Order

1. **`skip` (continue)** — trivial to add, very commonly needed
2. **Text built-ins in codegen** (split, replace, slice, upper, lower) — they're in the type checker but never emit IR
3. **`machinery.time()`, `machinery.args()`, `machinery.exit()`** — fills the most obvious OS gaps
4. **`rand` stdlib** — needed for almost any game
5. **Heap-allocated blueprints** — needed for data structures, OS work
6. **`cabinet` one-liners** (read, write, exists, delete)
7. **String interpolation**
8. **Canvas image loading + audio**
9. **`thread` stdlib**
10. **VS Code syntax highlighting**
