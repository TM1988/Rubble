# Rubble

A statically-typed, physically-themed systems programming language that compiles directly to **LLVM IR** and native binaries. Designed for OS development, games, and bare-metal work.

**File extension:** `.rbl` / `.rubble`

---

## Architecture

```
.rbl source
    └─► Lexer → Token stream
    └─► Parser → AST
    └─► Type Checker → Annotated AST (type inference)
    └─► Code Generator → LLVM IR (.ll)
    └─► clang/llc → Native binary
```

---

## Requirements

- Python 3.8+ (for the compiler frontend)
- LLVM / clang (for compiling IR to native binaries)

---

## Usage

```bash
# Emit LLVM IR only
python -m compiler <file.rbl>

# Type-check only (no output)
python -m compiler <file.rbl> --check

# Emit native assembly
python -m compiler <file.rbl> --emit-asm

# Compile to native binary (requires clang)
python -m compiler <file.rbl> --build -o my_program

# Custom output name
python -m compiler <file.rbl> -o output.ll
```

---

## Language Reference

### Types

| Rubble   | LLVM IR   | Meaning                        |
|----------|-----------|--------------------------------|
| `unit`   | `i64`     | 64-bit integer                 |
| `decimal`| `double`  | 64-bit float                   |
| `text`   | `i8*`     | Null-terminated string pointer |
| `switch` | `i1`      | Boolean (true / false)         |
| `crate`  | struct    | Array (length + data pointer)  |
| `empty`  | `void`    | Null / no value                |

### Variables

```rubble
slot count = 10           // mutable, type inferred as unit
lock slot PI = 3.14159    // immutable constant
```

### Output

```rubble
write "Hello, World!"
write count               // unit, decimal, switch all supported
```

### Type Casting — `smelt`

```rubble
slot n   = smelt("42", unit)      // text -> unit
slot s   = smelt(3.14, text)      // decimal -> text
slot b   = smelt(1, switch)       // unit -> switch
```

### Control Flow

```rubble
if score >= 90 { write "A" }
elif score >= 75 { write "B" }
else { write "F" }

loop count > 0 {
    count = count - 1
    if count == 5 { jam }       // jam = break
}

for item in items { write item }
```

### Recipes (Functions)

Explicit parameter and return types required.

```rubble
recipe add(a: unit, b: unit) -> unit {
    yield a + b
}
```

### Blueprints (Structs)

```rubble
blueprint Vec2 {
    x: decimal,
    y: decimal
}

slot v = build Vec2(x: 1.0, y: 2.0)
write v.x
```

### Wires & Unwrap (Pointers)

```rubble
slot speed = 42
slot ref = wire speed        // raw pointer to speed
unwrap ref = 99              // write through pointer
```

### Memory

```rubble
scrap myvar         // free variable from memory
wreck "Fatal!"      // panic — calls exit(1)
```

---

## Standard Libraries

Declared as external C functions — implemented in `runtime/rubble_stdlib.c`.

### `panel` — User Input
```rubble
gather panel
slot name = panel.prompt("Enter name: ")
slot line = panel.grab()
```

### `cabinet` — File System
```rubble
gather cabinet
slot f = cabinet.create("out.txt")
f.write("hello")
f.close()
slot files = cabinet.list(".")
```

### `machinery` — OS / Hardware
```rubble
gather machinery
slot mem = machinery.ram()
machinery.rest(1000)     // sleep 1 second (ms)
machinery.halt()         // exit
```

### `cable` — Networking
```rubble
gather cable
slot conn = cable.connect("example.com", 80)
slot data = conn.read()
```

---

## Math Library

```rubble
gather math

slot pi  = math.pi()              // 3.141593
slot e   = math.e()               // 2.718282

math.sqrt(x)      math.cbrt(x)     math.pow(base, exp)
math.abs(x)       math.floor(x)    math.ceil(x)    math.round(x)
math.sin(x)       math.cos(x)      math.tan(x)
math.asin(x)      math.acos(x)     math.atan(x)    math.atan2(y, x)
math.log(x)       math.log2(x)     math.log10(x)   math.exp(x)
math.min(a, b)    math.max(a, b)
math.clamp(val, lo, hi)
math.lerp(a, b, t)
```

---

## Canvas Library (UI / Graphics)

```rubble
gather canvas

slot win = canvas.open("My Window", 800, 600)

// Drawing
canvas.clear(win, r, g, b)
canvas.rect(win, x, y, w, h, r, g, b)
canvas.circle(win, cx, cy, radius, r, g, b)
canvas.line(win, x1, y1, x2, y2, r, g, b)
canvas.text(win, x, y, "Hello", r, g, b)
canvas.show(win)           // flush frame to screen

// Event loop
slot alive = canvas.poll(win)
loop alive > 0 {
    alive = canvas.poll(win)
}
canvas.close(win)

// Keyboard input (Windows Virtual Key codes)
canvas.key(win, 37)        // Left arrow held?  returns unit (1/0)
canvas.key(win, 39)        // Right arrow
canvas.key(win, 38)        // Up arrow
canvas.key(win, 40)        // Down arrow
canvas.key(win, 27)        // Escape
canvas.key(win, 32)        // Space

// Mouse input
canvas.mouse_x(win)        // cursor X position
canvas.mouse_y(win)        // cursor Y position
canvas.mouse_btn(win, 0)   // left button (1/0)
canvas.mouse_btn(win, 1)   // right button
canvas.mouse_btn(win, 2)   // middle button
```

---

## Building a Native Binary

```bash
# 1. Compile to IR
python -m compiler examples/hello_world.rbl

# 2. Link with stdlib and compile to binary (Linux/macOS)
clang examples/hello_world.ll runtime/rubble_stdlib.c -o hello -lm

# 3. Run
./hello
```

---

## Examples

| File | Covers |
|------|--------|
| `examples/hello_world.rbl` | Basic output |
| `examples/recipes_blueprints.rbl` | Functions, structs, recursion |
| `examples/browser_demo.rbl` | Stdlib, recipes, gather, loop |
| `examples/canvas_demo.rbl` | Canvas window, drawing primitives |
| `examples/canvas_shapes.rbl` | Canvas showcase — circles, rects, lines, text |
| `examples/canvas_input.rbl` | Interactive — arrow key ball movement |

## Tests

| File | Covers |
|------|--------|
| `tests/test_all.rbl` | All core language features |
| `tests/test_crate.rbl` | Crate (array) operations |
| `tests/test_math.rbl` | Math stdlib |

---

## Project Structure

```
compiler/
  lexer.py          Tokenizer
  parser.py         Recursive-descent parser
  ast_nodes.py      AST node types
  type_checker.py   Type inference and checking
  codegen.py        LLVM IR code generator
  rubblec.py        CLI entry point

runtime/
  rubble_stdlib.c   C implementations of panel, cabinet, machinery, cable

examples/           Sample .rbl programs
OLD/                Original tree-walk interpreter (archived)
```
