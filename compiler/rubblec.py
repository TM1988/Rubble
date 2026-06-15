"""
rubble — Rubble language
Usage:
    rubble main.rbl              Run immediately (compile-and-run, no files left behind)
    rubble main.rbl -o app       Produce a persistent binary called 'app'
    rubble main.rbl --check      Type-check only
    rubble main.rbl --emit-ir    Save the LLVM IR to a .ll file instead of running
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
        description="Rubble language — runs .rbl files like a scripting language",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n  rubble main.rbl\n  rubble main.rbl -o myapp"
    )
    ap.add_argument("file",       help="Source .rbl file")
    ap.add_argument("-o",         dest="output", default=None,
                    help="Save a persistent binary with this name instead of run-and-delete")
    ap.add_argument("--check",    action="store_true", help="Type-check only, no output")
    ap.add_argument("--emit-ir",  action="store_true", help="Save LLVM IR (.ll) and exit")
    args = ap.parse_args()

    src = args.file
    if not os.path.exists(src):
        _die(f"File not found: {src!r}")

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
    cg = CodeGen(filename=src)
    ir = _finalize_ir(cg, ast)

    # ── --emit-ir: just save the .ll and stop ─────────────────────────────
    if args.emit_ir:
        ll_out = os.path.splitext(src)[0] + ".ll"
        with open(ll_out, "w", encoding="utf-8") as f:
            f.write(ir)
        print(f"IR  →  {ll_out}")
        return

    # ── Find clang ────────────────────────────────────────────────────────
    clang = shutil.which("clang") or _find_clang()
    if not clang:
        ll_out = os.path.splitext(src)[0] + ".ll"
        with open(ll_out, "w", encoding="utf-8") as f:
            f.write(ir)
        _die(
            f"clang not found — cannot compile to a runnable binary.\n"
            f"  Install LLVM from: https://github.com/llvm/llvm-project/releases\n"
            f"  (Windows: LLVM-x.x.x-win64.exe, tick 'Add to PATH')\n"
            f"  IR saved to: {ll_out}"
        )

    stdlib_c = os.path.join(os.path.dirname(__file__), "..", "runtime", "rubble_stdlib.c")

    if args.output:
        # ── Persistent binary: user asked for -o ──────────────────────────
        _compile(clang, ir, stdlib_c, args.output)
        print(f"  →  {args.output}")
    else:
        # ── Compile-and-run (JIT style) ───────────────────────────────────
        # Compile to a temp binary, run it, delete it. Feels just like Python.
        ext = ".exe" if sys.platform == "win32" else ""
        tmp_bin = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        tmp_bin.close()
        try:
            _compile(clang, ir, stdlib_c, tmp_bin.name)
            result = subprocess.run([tmp_bin.name])
            sys.exit(result.returncode)
        finally:
            try:
                os.unlink(tmp_bin.name)
            except OSError:
                pass


# ── Compilation helper ────────────────────────────────────────────────────

def _compile(clang: str, ir: str, stdlib_c: str, out: str):
    """Write IR to a temp .ll, invoke clang, clean up the .ll."""
    tmp_ll = tempfile.NamedTemporaryFile(suffix=".ll", delete=False, mode="w", encoding="utf-8")
    try:
        tmp_ll.write(ir)
        tmp_ll.close()

        extra = [] if sys.platform == "win32" else ["-lm"]
        cmd   = [clang, tmp_ll.name]
        if os.path.exists(stdlib_c):
            cmd.append(stdlib_c)
        canvas_c = os.path.join(os.path.dirname(stdlib_c), "rubble_canvas.c")
        if os.path.exists(canvas_c):
            cmd.append(canvas_c)
        # On Windows, canvas needs GDI and user32
        if sys.platform == "win32":
            cmd += ["-lgdi32", "-luser32"]
        cmd += ["-o", out] + extra

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            # Show clang errors but strip the noisy target-triple warning
            stderr = "\n".join(
                l for l in result.stderr.splitlines()
                if "overriding the module target triple" not in l
                and "warning generated" not in l
            )
            if stderr:
                print(stderr, file=sys.stderr)
            _die(f"Compilation failed")
    finally:
        try:
            os.unlink(tmp_ll.name)
        except OSError:
            pass


# ── IR post-processing ────────────────────────────────────────────────────

def _finalize_ir(cg, ast) -> str:
    ir = cg.generate(ast)

    crate_defs = cg._emit_crate_type_defs()
    if crate_defs:
        lines = ir.split("\n")
        for defn in reversed(crate_defs):
            lines.insert(3, defn)
        ir = "\n".join(lines)

    if "sprintf" in ir and "declare i32 @sprintf" not in ir:
        ir = ir.replace(
            "declare i32 @printf(i8*, ...)",
            "declare i32 @printf(i8*, ...)\ndeclare i32 @sprintf(i8*, i8*, ...)"
        )

    return _dedup_decls(ir)


def _dedup_decls(ir: str) -> str:
    seen, out = set(), []
    for line in ir.split("\n"):
        s = line.strip()
        if s.startswith("declare "):
            if s in seen:
                continue
            seen.add(s)
        out.append(line)
    return "\n".join(out)


def _find_clang():
    """Fallback: check known install locations even if not on PATH."""
    candidates = [
        r"C:\Program Files\LLVM\bin\clang.exe",
        r"C:\Program Files (x86)\LLVM\bin\clang.exe",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def _die(msg: str):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
