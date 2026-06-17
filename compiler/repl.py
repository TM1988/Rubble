"""
Rubble REPL — compiler/repl.py

A read-eval-print loop that compiles and runs each statement interactively.
Usage:  rubble --repl

Each line (or block) is compiled to a fresh IR snippet, combined with
accumulated declarations, compiled to a temp binary, and run.

Multi-line input: a trailing '{' opens a block; keep reading until
the matching '}' is at indentation 0.
"""

import sys
import os
import subprocess
import tempfile
import shutil
import re

VERSION = "0.2.0"
_BANNER = f"""\
Rubble {VERSION} REPL  (Ctrl-C or 'exit' to quit)
Type Rubble code. Multi-line blocks end on a closing '}}' at column 0.
"""

# Accumulated context across REPL entries (declarations that persist)
_PREAMBLE_LINES = []   # list of source lines that form the persistent context


def run_repl(clang: str, runtime_dir: str):
    print(_BANNER)

    # Lines accumulated so far that must be re-compiled each time
    context_lines = []

    while True:
        try:
            line = _read_line(">>> ")
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not line.strip():
            continue
        if line.strip() in ("exit", "quit", "halt"):
            print("Bye.")
            break

        # Collect multi-line blocks
        block = _collect_block(line)

        # Append to context
        new_lines = context_lines + block

        # Wrap in a write so values are printed when the expression is bare
        source = _build_source(new_lines)

        # Compile and run
        ok = _compile_and_run(source, clang, runtime_dir)
        if ok:
            # Only persist gather, recipe, blueprint, slot/lock declarations
            for bl in block:
                s = bl.strip()
                if (s.startswith("gather ")
                        or s.startswith("recipe ")
                        or s.startswith("blueprint ")
                        or s.startswith("slot ")
                        or s.startswith("lock slot ")):
                    context_lines.append(bl)


def _read_line(prompt: str) -> str:
    sys.stdout.write(prompt)
    sys.stdout.flush()
    return sys.stdin.readline()


def _collect_block(first_line: str) -> list:
    """If first_line opens a block, keep reading until the block is closed."""
    lines = [first_line]
    depth = first_line.count("{") - first_line.count("}")
    if depth <= 0:
        return lines
    while True:
        try:
            line = _read_line("... ")
        except (EOFError, KeyboardInterrupt):
            break
        lines.append(line)
        depth += line.count("{") - line.count("}")
        if depth <= 0:
            break
    return lines


def _build_source(lines: list) -> str:
    """Join lines into a complete source snippet."""
    return "".join(lines)


def _compile_and_run(source: str, clang: str, runtime_dir: str) -> bool:
    """Compile source to a temp binary and run it. Returns True on success."""
    from .lexer import Lexer, LexError
    from .parser import Parser, ParseError
    from .type_checker import TypeChecker, TypeError_
    from .codegen import CodeGen
    from .rubblec import _finalize_ir, _compile

    # ── Lex ──
    try:
        tokens = Lexer(source, filename="<repl>").tokenize()
    except LexError as e:
        print(f"  lex error: {e}", file=sys.stderr)
        return False

    # ── Parse ──
    try:
        ast = Parser(tokens).parse()
    except ParseError as e:
        print(f"  parse error: {e}", file=sys.stderr)
        return False

    # ── Type check ──
    try:
        TypeChecker().check(ast)
    except TypeError_ as e:
        print(f"  type error: {e}", file=sys.stderr)
        return False

    # ── Codegen ──
    cg = CodeGen(filename="<repl>")
    ir = _finalize_ir(cg, ast)

    # ── Compile ──
    ext = ".exe" if sys.platform == "win32" else ""
    tmp_bin = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    tmp_bin.close()
    try:
        try:
            _compile(clang, ir, runtime_dir, tmp_bin.name)
        except SystemExit:
            return False
        result = subprocess.run([tmp_bin.name], timeout=10)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("  (timed out after 10s)", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  run error: {e}", file=sys.stderr)
        return False
    finally:
        try:
            os.unlink(tmp_bin.name)
        except OSError:
            pass
