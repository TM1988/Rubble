"""
rubble — Rubble Compiler
Usage:
    rubble <file.rbl>               Compile to native binary (requires clang)
    rubble <file.rbl> --check       Type-check only
    rubble <file.rbl> --emit-ir     Keep the intermediate .ll file
    rubble <file.rbl> -o <name>     Set output binary name

If clang is not installed, emits a .ll (LLVM IR) file and tells you how to get clang.
"""

import sys
import os
import subprocess
import shutil
import argparse
import tempfile


def main():
    ap = argparse.ArgumentParser(
        prog="rubble",
        description="Rubble compiler",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example:\n  rubble main.rbl\n  rubble main.rbl -o myapp"
    )
    ap.add_argument("file",      help="Source .rbl file to compile")
    ap.add_argument("-o",        dest="output", default=None, help="Output binary name")
    ap.add_argument("--check",   action="store_true", help="Type-check only, no output")
    ap.add_argument("--emit-ir", action="store_true", help="Keep the .ll IR file instead of compiling to binary")
    args = ap.parse_args()

    src = args.file
    if not os.path.exists(src):
        _die(f"File not found: {src!r}")

    base     = os.path.splitext(src)[0]
    bin_out  = args.output or base + (".exe" if sys.platform == "win32" else "")
    ll_out   = base + ".ll"

    # ── Lex ──────────────────────────────────────────────────────────────
    with open(src, "r", encoding="utf-8") as f:
        source = f.read()

    from .lexer import Lexer, LexError
    try:
        tokens = Lexer(source, filename=src).tokenize()
    except LexError as e:
        _die(str(e))

    # ── Parse ─────────────────────────────────────────────────────────────
    from .parser import Parser, ParseError
    try:
        ast = Parser(tokens).parse()
    except ParseError as e:
        _die(str(e))

    # ── Type check ────────────────────────────────────────────────────────
    from .type_checker import TypeChecker, TypeError_
    tc = TypeChecker()
    try:
        tc.check(ast)
    except TypeError_ as e:
        _die(str(e))

    if args.check:
        print(f"OK  {src}")
        return

    # ── Codegen → LLVM IR ─────────────────────────────────────────────────
    from .codegen import CodeGen
    cg  = CodeGen(filename=src)
    ir  = _finalize_ir(cg, ast)

    if args.emit_ir:
        # User explicitly asked to keep the IR
        with open(ll_out, "w", encoding="utf-8") as f:
            f.write(ir)
        print(f"IR  →  {ll_out}")
        return

    # ── Try to compile to native binary via clang ─────────────────────────
    clang = shutil.which("clang") or _find_clang()
    if not clang:
        # No clang — fall back to IR and explain clearly
        with open(ll_out, "w", encoding="utf-8") as f:
            f.write(ir)
        print(f"")
        print(f"  Rubble compiled {src}  →  {ll_out}")
        print(f"")
        print(f"  To get a runnable binary, install clang:")
        print(f"    Windows : https://github.com/llvm/llvm-project/releases")
        print(f"              (download LLVM-x.x.x-win64.exe, tick 'Add to PATH')")
        print(f"    Then run:  rubble {src}")
        print(f"")
        return

    # Write IR to a temp file, compile, clean up
    stdlib_c = os.path.join(os.path.dirname(__file__), "..", "runtime", "rubble_stdlib.c")
    tmp_ll   = tempfile.NamedTemporaryFile(suffix=".ll", delete=False)
    try:
        tmp_ll.write(ir.encode("utf-8"))
        tmp_ll.close()

        extra_flags = [] if sys.platform == "win32" else ["-lm"]
        cmd = [clang, tmp_ll.name, "-o", bin_out] + extra_flags
        if os.path.exists(stdlib_c):
            cmd.insert(2, stdlib_c)

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stderr, file=sys.stderr)
            _die(f"clang failed to compile {src}")

        print(f"  →  {bin_out}")
    finally:
        os.unlink(tmp_ll.name)


# ── Helpers ───────────────────────────────────────────────────────────────

def _finalize_ir(cg, ast) -> str:
    ir = cg.generate(ast)

    # Inject crate struct types after the target triple
    crate_defs = cg._emit_crate_type_defs()
    if crate_defs:
        lines = ir.split("\n")
        for defn in reversed(crate_defs):
            lines.insert(3, defn)
        ir = "\n".join(lines)

    # Add sprintf declaration if used but not declared
    if "sprintf" in ir and "declare i32 @sprintf" not in ir:
        ir = ir.replace(
            "declare i32 @printf(i8*, ...)",
            "declare i32 @printf(i8*, ...)\ndeclare i32 @sprintf(i8*, i8*, ...)"
        )

    return _dedup_decls(ir)


def _dedup_decls(ir: str) -> str:
    seen = set()
    out  = []
    for line in ir.split("\n"):
        stripped = line.strip()
        if stripped.startswith("declare "):
            if stripped in seen:
                continue
            seen.add(stripped)
        out.append(line)
    return "\n".join(out)


def _find_clang() -> str | None:
    """Check known install locations for clang on Windows."""
    candidates = [
        r"C:\Program Files\LLVM\bin\clang.exe",
        r"C:\Program Files (x86)\LLVM\bin\clang.exe",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _die(msg: str):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
