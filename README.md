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
