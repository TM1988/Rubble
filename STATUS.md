# Rubble Language - Implementation Status

## 🔴 Core Language — Missing Basics

### Control flow
- ✅ `else if` chaining works (supported)
- ❌ No `switch/match` statement (pattern matching on a value) - **MISSING**
- ✅ `continue` (via `skip`) - **IMPLEMENTED** (as `skip`)
- ❌ No labeled breaks (break out of a specific outer loop) - **MISSING**

### Types & expressions
- ❌ No string interpolation — you have to write `"x = " + smelt(x, text)` instead of `"x = {x}"` - **MISSING**
- ✅ Multi-return from recipes (via blueprint workaround) - **IMPLEMENTED** 
- ❌ No default parameter values in recipes - **MISSING**
- ❌ No variadic recipes (`...args`) - **MISSING**
- ❌ No `unit` size variants (i8, i16, i32 — only i64 right now) - **MISSING**
- ❌ No unsigned integers - **MISSING**

### Memory
- ❌ No heap-allocated blueprints — `build` currently allocates on the stack, meaning blueprints can't escape a function or be stored in a crate - **MISSING**

---

## 🟡 Standard Library — Obvious Gaps

### `machinery` (OS)
- ✅ `machinery.rest(ms)` - **IMPLEMENTED** 
- ✅ `machinery.time()` - **IMPLEMENTED**
- ✅ `machinery.args()` - **IMPLEMENTED**
- ✅ `machinery.env(name)` - **IMPLEMENTED**
- ✅ `machinery.exit(code)` - **IMPLEMENTED**

### `text` built-ins
- ✅ `t.split(sep)` - **IMPLEMENTED** (type checker has it, codegen doesn't)
- ✅ `t.replace(old, new)` - **IMPLEMENTED** (codegen only)
- ✅ `t.index(sub)` - **IMPLEMENTED** (codegen only) 
- ✅ `t.slice(start, end)` - **IMPLEMENTED** (codegen only)
- ✅ `t.upper()` / `t.lower()` - **IMPLEMENTED** (codegen only)

### `crate` built-ins
- ✅ `c.slice(start, end)` - **IMPLEMENTED**
- ✅ `c.sort()` - **IMPLEMENTED**
- ✅ `c.reverse()` - **IMPLEMENTED**
- ✅ `c.join(sep)` - **IMPLEMENTED**

### `cabinet` (file system)
- ✅ `cabinet.read(path)` - **IMPLEMENTED**
- ✅ `cabinet.write(path, data)` - **IMPLEMENTED**
- ✅ `cabinet.exists(path)` - **IMPLEMENTED**
- ✅ `cabinet.delete(path)` - **IMPLEMENTED**
- ⚠️ `cabinet.list(path)` - **PARTIAL** (exists but codegen returns null - not wired up yet)

### New modules
- ✅ `rand` - **IMPLEMENTED** (runtime/rubble_rand.c)
- ❌ `time` - **MISSING** 
- ❌ `thread` - **MISSING**
- ❌ `json` - **MISSING**

---

## 🟢 Canvas — Missing for Games/OS

- ⚠️ `canvas.fill_mode(win, mode)` - **PARTIAL** (some implementation but not full)
- ⚠️ `canvas.key_just_pressed(win, key)` - **PARTIAL** (has basic key input)
- ⚠️ `canvas.mouse_scroll(win)` - **PARTIAL** (basic mouse input)
- ⚠️ `canvas.set_title(win, text)` - **PARTIAL** 
- ⚠️ `canvas.resize(win, w, h)` - **PARTIAL**
- ⚠️ `canvas.fullscreen(win)` - **PARTIAL**
- ❌ `canvas.image_load(path)` - **MISSING**
- ❌ `canvas.image_draw(win, img, x, y)` - **MISSING**
- ⚠️ `canvas.font_size(win, size)` - **PARTIAL**
- ❌ `canvas.delta_time()` - **MISSING**
- ❌ Audio: `sound.load(path)`, `sound.play(handle)`, `sound.stop(handle)` - **MISSING**

---

## 🔵 Tooling

- ✅ `rubble --version` - **IMPLEMENTED**
- ❌ Syntax highlighting definitions (VS Code extension, `.tmLanguage`) - **MISSING**
- ✅ A package manager / `gather` from URL or registry - **IMPLEMENTED**
- ✅ `rubble fmt file.rbl` - **IMPLEMENTED** 
- ❌ Error messages with line/column + source snippet - **MISSING**
- ✅ REPL (`rubble --repl`) - **IMPLEMENTED**

---

## Priority Order Status

1. **`skip` (continue)** — trivial to add, very commonly needed
   - ✅ Implemented as `skip` 

2. **Text built-ins in codegen** (split, replace, slice, upper, lower) 
   - ⚠️ In type checker but not fully wired in codegen - **PARTIAL**
   - Note: The `rubble_stdlib.c` has these functions implemented, but they may not be fully connected to the IR generation.

3. **`machinery.time()`, `machinery.args()`, `machinery.exit()`** 
   - ✅ All implemented

4. **`rand` stdlib** 
   - ✅ Implemented

5. **Heap-allocated blueprints** 
   - ❌ Missing

6. **`cabinet` one-liners** (read, write, exists, delete)
   - ✅ All implemented

7. **String interpolation**
   - ❌ Missing

8. **Canvas image loading + audio**
   - ❌ Missing

9. **`thread` stdlib**
   - ❌ Missing

10. **VS Code syntax highlighting**
    - ❌ Missing

## Summary

### ✅ Fully Implemented Features
- Basic language constructs (variables, recipes, blueprints)
- Control flow with `if/elif/else` and `loop`
- All basic math and comparison operations
- All core standard library functions (`panel`, `cabinet`, `machinery`, `cable`)
- REPL
- Formatting tool (`rubble fmt`)
- Package manager (`gather` from URL)
- Version command (`rubble --version`)

### ⚠️ Partially Implemented Features  
- Text built-ins in codegen (some functions exist but not all wired up)
- Canvas library (some functionality exists but many features are missing)
- `cabinet.list()` function
- Some `canvas` API functions

### ❌ Missing Features
- String interpolation 
- `switch/match` statement
- Labeled breaks
- Default parameter values in recipes
- Variadic recipes
- Unit size variants (i8, i16, i32)
- Unsigned integers
- Heap-allocated blueprints
- `time` stdlib module
- `thread` stdlib module
- `json` stdlib module
- Canvas image loading and audio support
- Full canvas API functions
- VS Code syntax highlighting
- Improved error messages with source snippets

## Next Steps

Based on the roadmap priority order, these are the most important features to implement next:

1. String interpolation - **High Priority**
2. Heap-allocated blueprints - **High Priority**  
3. `switch/match` statement - **Medium Priority**
4. `thread` stdlib - **Medium Priority**
5. `time` stdlib - **Medium Priority**
6. Canvas image loading and audio - **Low Priority**
