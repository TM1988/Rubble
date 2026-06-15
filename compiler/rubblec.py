"""
rubblec — Rubble Compiler CLI
Usage:
    python -m compiler <file.rbl> [options]

Options:
    --emit-ir       Stop after emitting LLVM IR (.ll file)  [default]
    --emit-asm      Emit native assembly (.s) via llc
    --build         Compile to native binary via clang
    -o <output>     Output file name (default: same as input, different extension)
    --check         Type-check only, no codegen
"""

import sys
import os
import subprocess
import argparse


def main():
    ap = argparse.ArgumentParser(
        prog="rubblec",
        description="Rubble compiler — emits LLVM IR and optionally native binaries"
    )
    ap.add_argument("file", help="Source .rbl file")
    ap.add_argument("--emit-ir",  action="store_true", default=True,
                    help="Emit LLVM IR .ll file (default)")
    ap.add_argument("--emit-asm", action="store_true",
                    help="Emit native assembly via llc")
    ap.add_argument("--build",    action="store_true",
                    help="Compile to native binary via clang")
    ap.add_argument("--check",    action="store_true",
                    help="Type-check only, no output files")
    ap.add_argument("-o", dest="output", default=None,
                    help="Output file name")
    args = ap.parse_args()

    src_path = args.file
    if not os.path.exists(src_path):
        _die(f"File not found: {src_path!r}")

    with open(src_path, 'r', encoding='utf-8') as f:
        source = f.read()

    base = os.path.splitext(src_path)[0]

    # --- Lex ---
    from .lexer import Lexer, LexError
    try:
        tokens = Lexer(source, filename=src_path).tokenize()
    except LexError as e:
        _die(str(e))

    # --- Parse ---
    from .parser import Parser, ParseError
    try:
        ast = Parser(tokens).parse()
    except ParseError as e:
        _die(str(e))

    # --- Type check ---
    from .type_checker import TypeChecker, TypeError_
    tc = TypeChecker()
    try:
        tc.check(ast)
    except TypeError_ as e:
        _die(str(e))

    if args.check:
        print(f"[rubblec] Type check passed: {src_path}")
        return

    # --- Codegen ---
    from .codegen import CodeGen
    cg = CodeGen(filename=src_path)

    # Inject crate type defs before emitting
    ir = _finalize_ir(cg, ast)

    ll_path = args.output if (args.output and not args.emit_asm and not args.build) else base + ".ll"
    with open(ll_path, 'w', encoding='utf-8') as f:
        f.write(ir)
    print(f"[rubblec] IR  -> {ll_path}")

    if args.emit_asm:
        s_path = args.output if args.output else base + ".s"
        _run(["llc", "-filetype=asm", ll_path, "-o", s_path])
        print(f"[rubblec] ASM -> {s_path}")

    if args.build:
        stdlib_c = os.path.join(os.path.dirname(__file__), "..", "runtime", "rubble_stdlib.c")
        bin_path = args.output if args.output else base
        if not os.path.exists(stdlib_c):
            print(f"[rubblec] Warning: runtime/rubble_stdlib.c not found — linking without stdlib")
            _run(["clang", ll_path, "-o", bin_path, "-lm"])
        else:
            _run(["clang", ll_path, stdlib_c, "-o", bin_path, "-lm"])
        print(f"[rubblec] BIN -> {bin_path}")


def _finalize_ir(cg, ast) -> str:
    """Run codegen and inject crate struct types into the output."""
    ir = cg.generate(ast)
    crate_defs = cg._emit_crate_type_defs()
    if crate_defs:
        # Insert after the target triple line
        lines = ir.split('\n')
        insert_at = 3  # after target triple
        for defn in reversed(crate_defs):
            lines.insert(insert_at, defn)
        ir = '\n'.join(lines)
    # Also add sprintf declaration if needed
    if "sprintf" in ir and "declare i32 @sprintf" not in ir:
        ir = ir.replace(
            "declare i32 @printf(i8*, ...)",
            "declare i32 @printf(i8*, ...)\ndeclare i32 @sprintf(i8*, i8*, ...)"
        )
    # Add atoll / atof if needed (deduplicate inline decls)
    ir = _dedup_decls(ir)
    return ir


def _dedup_decls(ir: str) -> str:
    """Remove duplicate declare lines that codegen may emit inline."""
    seen = set()
    out = []
    for line in ir.split('\n'):
        stripped = line.strip()
        if stripped.startswith("declare "):
            if stripped in seen:
                continue
            seen.add(stripped)
        out.append(line)
    return '\n'.join(out)


def _run(cmd):
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        _die(f"Command not found: {cmd[0]!r} — is LLVM/clang installed?")
    except subprocess.CalledProcessError as e:
        _die(f"Command failed: {' '.join(cmd)}")


def _die(msg: str):
    print(f"[rubblec] Error: {msg}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
