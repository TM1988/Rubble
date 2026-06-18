# Rubble Language - Future Feature Ideas

This document contains potential new features and enhancements for the Rubble programming language that are not yet implemented.

---

## Type System Enhancements

### Integer Size Variants
Currently only `unit` (i64) exists. Add smaller integer types for memory-efficient operations:
- `i8` - 8-bit signed integer
- `i16` - 16-bit signed integer
- `i32` - 32-bit signed integer

### Unsigned Integers
Add unsigned integer types for systems programming:
- `u8` - 8-bit unsigned integer
- `u16` - 16-bit unsigned integer
- `u32` - 32-bit unsigned integer
- `u64` - 64-bit unsigned integer

### Enums
Add enum types for named constants:
```rubble
enum Color {
    Red,
    Green,
    Blue
}

slot c = Color.Red
```

### Option/Result Types
Add built-in sum types for error handling:
```rubble
slot result: option[unit] = some(42)
slot error: result[text, text] = ok("success")
```

### Generics
Add generic recipes and blueprints:
```rubble
recipe identity<T>(x: T) -> T {
    yield x
}

blueprint Container<T> {
    value: T
}
```

---

## Language Features

### Range Loops
Add range syntax for iteration:
```rubble
for i in 0..10 {
    write i
}
```

### Pattern Matching Enhancements
Add destructuring patterns in match:
```rubble
match point {
    case Vec2(x: 0, y: 0) => { write "origin" }
    case Vec2(x, y) => { write f"({x}, {y})" }
}
```

### Closures/Lambdas
Add anonymous functions:
```rubble
slot doubled = map(items, fn(x) { x * 2 })
```

### Decorators/Attributes
Add metadata for recipes/blueprints:
```rubble
@inline
recipe fast_add(a: unit, b: unit) -> unit {
    yield a + b
}

@extern("C")
recipe external_func() -> empty
```

### Const Expressions
Add compile-time constant evaluation:
```rubble
const MAX_SIZE = 1024
const PI = 3.14159
```

### Modules/Packages
Add proper module system with import/export:
```rubble
export recipe add(a: unit, b: unit) -> unit {
    yield a + b
}

import math
import mylib.utils
```

---

## Standard Library Additions

### Crypto Module
Hash functions and encryption:
```rubble
gather crypto
slot hash = crypto.sha256("data")
slot encrypted = crypto.aes_encrypt("data", "key")
```

### Compression Module
Gzip/zlib compression:
```rubble
gather compress
slot compressed = compress.gzip("data")
slot decompressed = compress.gunzip(compressed)
```

### Database Module
SQLite bindings for local data persistence:
```rubble
gather db
slot conn = db.open("database.sqlite")
db.execute(conn, "CREATE TABLE users (id INT, name TEXT)")
slot rows = db.query(conn, "SELECT * FROM users")
```

### HTTP Module
HTTP client/server for web APIs:
```rubble
gather http
slot response = http.get("https://api.example.com/data")
slot data = response.body()
```

### Websocket Module
Real-time bidirectional communication:
```rubble
gather ws
slot ws = ws.connect("ws://example.com/socket")
ws.send(ws, "hello")
slot msg = ws.receive(ws)
```

### Regex Module
Regular expression pattern matching:
```rubble
gather regex
slot matches = regex.find_all(r"\d+", "test 123 test 456")
```

### XML Module
XML parsing and generation:
```rubble
gather xml
slot doc = xml.parse("<root><item>test</item></root>")
slot text = xml.get_text(doc, "/root/item")
```

### CSV Module
CSV file parsing/writing:
```rubble
gather csv
slot rows = csv.parse("file.csv")
slot csv_text = csv.stringify(rows)
```

### Logging Module
Structured logging with levels:
```rubble
gather log
log.info("Application started")
log.error("Something went wrong")
log.debug("Debug info")
```

### Config Module
Configuration file parsing:
```rubble
gather config
slot cfg = config.load("config.toml")
slot value = config.get(cfg, "server.port")
```

### Process Module
Spawn and manage external processes:
```rubble
gather process
slot proc = process.spawn("ls", "-la")
slot output = process.wait(proc)
```

### Signal Module
Unix signal handling for servers:
```rubble
gather signal
signal.handle("SIGINT", fn() { write "Caught interrupt" })
```

### Filesystem Watcher
Monitor directory changes:
```rubble
gather fs
slot watcher = fs.watch(".")
loop {
    slot event = fs.next_event(watcher)
    write f"File changed: {event.path}"
}
```

---

## Canvas/Graphics Enhancements

### Sprite/Animation System
Frame-based animation support:
```rubble
gather canvas
slot sprite = canvas.sprite_load("player.png")
canvas.sprite_set_frame(sprite, 0)
canvas.sprite_draw(win, sprite, x, y)
```

### Collision Detection
AABB and circle collision helpers:
```rubble
gather canvas
slot collides = canvas.collides_rect(x1, y1, w1, h1, x2, y2, w2, h2)
slot circle_hit = canvas.collides_circle(cx1, cy1, r1, cx2, cy2, r2)
```

### Tilemap System
2D tile-based rendering:
```rubble
gather canvas
slot tilemap = canvas.tilemap_load("map.png", 32, 32)
canvas.tilemap_draw(win, tilemap, camera_x, camera_y)
```

### Particle System
Particle effects for games:
```rubble
gather canvas
slot emitter = canvas.particle_emitter(x, y)
canvas.particle_emit(emitter, 100)
canvas.particle_update(emitter, delta_time)
canvas.particle_draw(win, emitter)
```

### Camera System
Viewport/scrolling for larger worlds:
```rubble
gather canvas
slot camera = canvas.camera_create(x, y, width, height)
canvas.camera_follow(camera, target)
canvas.camera_apply(win, camera)
```

### Font Rendering
Custom font loading:
```rubble
gather canvas
slot font = canvas.font_load("font.ttf", 16)
canvas.text_font(win, font)
canvas.text_draw(win, x, y, "Hello")
```

### Shader Support
Custom GLSL shaders for advanced effects:
```rubble
gather canvas
slot shader = canvas.shader_load("vertex.glsl", "fragment.glsl")
canvas.shader_bind(win, shader)
```

### 3D Basics
Simple 3D rendering:
```rubble
gather canvas3d
slot mesh = canvas3d.mesh_cube()
canvas3d.draw(win, mesh, x, y, z)
```

### Input Gamepad Support
Controller input handling:
```rubble
gather canvas
slot gamepad = canvas.gamepad_open(0)
slot pressed = canvas.gamepad_button(gamepad, 0)  // A button
```

---

## Concurrency Enhancements

### Channels
Message passing between threads:
```rubble
gather channel
slot ch = channel.create()
channel.send(ch, "message")
slot msg = channel.receive(ch)
```

### Mutex/Locks
Explicit synchronization primitives:
```rubble
gather sync
slot mutex = sync.mutex_create()
sync.mutex_lock(mutex)
// critical section
sync.mutex_unlock(mutex)
```

### Atomic Operations
Lock-free atomic types:
```rubble
gather atomic
slot counter = atomic.create(0)
atomic.add(counter, 1)
slot value = atomic.load(counter)
```

### Thread Pools
Worker thread pool for parallel tasks:
```rubble
gather pool
slot pool = pool.create(4)
pool.submit(pool, my_task)
pool.wait(pool)
```

### Async/Await
Asynchronous programming model:
```rubble
async recipe fetch_data() -> text {
    slot data = await http.get("https://api.example.com")
    yield data.body()
}
```

---

## Tooling Improvements

### Debugger
Step-through debugging with breakpoints:
```bash
rubble debug program.rbl
```

### Profiler
Performance profiling and hot-spot detection:
```bash
rubble profile program.rbl
```

### Package Registry
Central package repository:
```bash
rubble install json
rubble search http
```

### Dependency Manager
Versioned dependencies with lock files:
```rubble
# rubble.lock
json = "^1.2.0"
http = "^2.0.0"
```

### Documentation Generator
Auto-generate docs from source:
```bash
rubble docs --output docs/
```

### Benchmarking Tool
Performance benchmarking framework:
```rubble
bench test_sort() {
    bench_start()
    // code to benchmark
    bench_end()
}
```

### Fuzzer
Property-based testing:
```bash
rubble fuzz program.rbl
```

### Linter
Static analysis for code quality:
```bash
rubble lint program.rbl
```

### Build System
Multi-file project building:
```rubble
# rubble.build
src = ["main.rbl", "utils.rbl"]
output = "myapp"
deps = ["json", "http"]
```

### Hot Reload
Reload code during development:
```bash
rubble watch program.rbl
```

---

## Runtime/Platform

### Garbage Collector
Optional GC for automatic memory management:
```rubble
// rubble.gc
#gc enable
#gc threshold 100MB
```

### Reference Counting
Smart pointer semantics:
```rubble
slot ptr = arc.new(data)
slot cloned = arc.clone(ptr)
arc.drop(ptr)
```

### Foreign Function Interface (FFI)
Call C libraries directly:
```rubble
extern "C" strlen(s: text) -> unit
slot len = strlen("hello")
```

### WebAssembly Target
Compile to WASM for browser:
```bash
rubble build --target wasm program.rbl
```

### Embedded Targets
ARM/AVR for microcontrollers:
```bash
rubble build --target arm program.rbl
```

### Android/iOS Support
Mobile platform runtimes:
```bash
rubble build --target android program.rbl
```

### BSD Support
Additional Unix-like OS support:
- FreeBSD
- OpenBSD
- NetBSD

---

## Developer Experience

### Language Server Protocol (LSP)
IDE integration:
- Autocomplete
- Go-to-definition
- Find references
- Hover documentation
- Code actions

### Testing Framework
Built-in unit testing:
```rubble
test test_add() {
    slot result = add(2, 3)
    assert(result == 5)
}
```

### Benchmark Framework
Performance testing:
```rubble
bench bench_sort() {
    bench_start()
    sort(items)
    bench_end()
}
```

### REPL Enhancements
- Command history
- Tab completion
- Multiline editing
- Color output

### Error Recovery
Continue parsing after errors to show multiple issues:
```rubble
// Show all errors at once instead of stopping at first
```

### Warning System
Lint warnings for potential issues:
```rubble
// Warning: unused variable 'x'
// Warning: unreachable code
```

### Code Coverage
Test coverage reporting:
```bash
rubble test --coverage program.rbl
```

---

## Metaprogramming

### Macros
Compile-time code generation:
```rubble
macro debug(expr) {
    write f"DEBUG: {expr} = {#expr}"
}

debug(x + y)  // expands to: write "DEBUG: x + y = 5"
```

### Compile-Time Function Execution (CTFE)
Run functions at compile time:
```rubble
const fn factorial(n: unit) -> unit {
    if n <= 1 { yield 1 }
    yield n * factorial(n - 1)
}

const FACT_5 = factorial(5)  // computed at compile time
```

### Reflection
Inspect types at runtime:
```rubble
slot type_info = typeof(my_var)
slot fields = type_info.fields()
slot methods = type_info.methods()
```

### Code Generation Attributes
Auto-generate implementations:
```rubble
@derive(Debug, Clone, Eq)
blueprint Person {
    name: text,
    age: unit
}
```

---

## High Priority Recommendations

Given Rubble's focus on systems programming and games, these features are recommended for priority implementation:

1. **Integer size variants + unsigned integers** - Critical for systems programming
2. **Range loops** - Common pattern, improves ergonomics
3. **Closures/lambdas** - Essential for functional-style programming
4. **HTTP module** - Modern applications need web APIs
5. **Database module (SQLite)** - Data persistence is fundamental
6. **LSP** - Dramatically improves developer experience
7. **Testing framework** - Essential for language adoption
8. **Debugger** - Critical for systems programming

---

## Implementation Notes

- The Rubble language is impressively complete with most roadmap features already implemented
- These suggestions focus on expanding capabilities for real-world use cases
- Priority should be given to features that align with Rubble's goals: systems programming, game development, and OS work
- Consider incremental implementation - start with high-impact, low-complexity features
