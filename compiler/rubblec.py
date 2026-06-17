"""
rubble — Rubble language
Usage:
    rubble main.rbl              Run immediately (compile-and-run)
    rubble main.rbl -o app       Produce a persistent binary
    rubble main.rbl --check      Type-check only
    rubble main.rbl --emit-ir    Save the LLVM IR to a .ll file
    rubble main.rbl --fmt        Auto-format the source file in-place
    rubble main.rbl --fmt-check  Check formatting (exit 1 if not formatted)
    rubble --repl                Start interactive REPL
    rubble --get URL             Download and install a package from URL
    rubble --version             Show the Rubble version
"""

import sys
import os
import subprocess
import shutil
import argparse
import tempfile

VERSION = "0.2.0"

# Runtime C files bundled with the compiler
_RUNTIME_FILES = [
    "rubble_stdlib.c",
    "rubble_canvas.c",
    "rubble_math.c",
    "rubble_rand.c",
    "rubble_time.c",
    "rubble_json.c",
    "rubble_sound.c",
    "rubble_thread.c",
]


def main():
    # Fast path: rubble --version (before argparse so it works standalone)
    if len(sys.argv) == 2 and sys.argv[1] in ("--version", "-v"):
        print(f"Rubble {VERSION}")
        return

    ap = argparse.ArgumentParser(
        prog="rubble",
        description="Rubble language — runs .rbl files like a scripting language",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  rubble main.rbl\n"
            "  rubble main.rbl -o myapp\n"
            "  rubble main.rbl --fmt\n"
            "  rubble --repl\n"
            "  rubble --get https://example.com/pkg/utils.rbl\n"
            "  rubble --version"
        )
    )
    ap.add_argument("file",       nargs="?", default=None, help="Source .rbl file")
    ap.add_argument("-o",         dest="output", default=None,
                    help="Save a persistent binary with this name instead of run-and-delete")
    ap.add_argument("--check",    action="store_true", help="Type-check only, no output")
    ap.add_argument("--emit-ir",  action="store_true", help="Save LLVM IR (.ll) and exit")
    ap.add_argument("--version",  action="store_true", help="Show Rubble version and exit")
    ap.add_argument("--fmt",      action="store_true", help="Auto-format the source file in-place")
    ap.add_argument("--fmt-check",action="store_true", help="Check formatting without modifying (exit 1 if not formatted)")
    ap.add_argument("--repl",     action="store_true", help="Start interactive REPL")
    ap.add_argument("--get",      dest="get_pkg", default=None, metavar="URL",
                    help="Download and install a Rubble package from a URL")
    args = ap.parse_args()

    if args.version:
        print(f"Rubble {VERSION}")
        return

    # ── REPL ──────────────────────────────────────────────────────────────
    if args.repl:
        clang = shutil.which("clang") or _find_clang()
        if not clang:
            _die("clang not found — REPL requires clang to compile snippets")
        runtime_dir = os.path.join(os.path.dirname(__file__), "..", "runtime")
        from .repl import run_repl
        run_repl(clang, runtime_dir)
        return

    # ── Package install from URL ───────────────────────────────────────────
    if args.get_pkg:
        _install_package(args.get_pkg)
        return

    if args.file is None:
        ap.print_help()
        sys.exit(1)

    src = args.file
    if not os.path.exists(src):
        _die(f"File not found: {src!r}")

    # ── --fmt / --fmt-check ───────────────────────────────────────────────
    if args.fmt or args.fmt_check:
        with open(src, "r", encoding="utf-8") as f:
            original = f.read()
        from .fmt import format_source
        formatted = format_source(original)
        if args.fmt_check:
            if original == formatted:
                print(f"OK  {src}")
            else:
                print(f"NEEDS FORMAT  {src}", file=sys.stderr)
                sys.exit(1)
        else:
            with open(src, "w", encoding="utf-8") as f:
                f.write(formatted)
            print(f"fmt  {src}")
        return

    # ── Read source ───────────────────────────────────────────────────────
    with open(src, "r", encoding="utf-8") as f:
        source = f.read()
    source_lines = source.splitlines()

    # ── Lex ───────────────────────────────────────────────────────────────
    from .lexer import Lexer, LexError
    try:
        tokens = Lexer(source, filename=src).tokenize()
    except LexError as e:
        _die_with_source(str(e), e.line, source_lines, getattr(e, 'col', None))

    # ── Parse ─────────────────────────────────────────────────────────────
    from .parser import Parser, ParseError
    try:
        ast = Parser(tokens).parse()
    except ParseError as e:
        _die_with_source(str(e), e.tok.line, source_lines, e.tok.col)

    # ── Type check ────────────────────────────────────────────────────────
    from .type_checker import TypeChecker, TypeError_
    tc = TypeChecker()
    try:
        tc.check(ast)
    except TypeError_ as e:
        _die_with_source(str(e), e.loc.line, source_lines, e.loc.col)

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

    runtime_dir = os.path.join(os.path.dirname(__file__), "..", "runtime")

    if args.output:
        _compile(clang, ir, runtime_dir, args.output)
        print(f"  →  {args.output}")
    else:
        ext = ".exe" if sys.platform == "win32" else ""
        tmp_bin = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        tmp_bin.close()
        try:
            _compile(clang, ir, runtime_dir, tmp_bin.name)
            result = subprocess.run([tmp_bin.name], cwd=os.path.dirname(os.path.abspath(src)) or ".")
            sys.exit(result.returncode)
        finally:
            try:
                os.unlink(tmp_bin.name)
            except OSError:
                pass


# ── Compilation helper ────────────────────────────────────────────────────

def _compile(clang: str, ir: str, runtime_dir: str, out: str):
    """Write IR to a temp .ll, invoke clang with all runtime C files, clean up."""
    tmp_ll = tempfile.NamedTemporaryFile(suffix=".ll", delete=False, mode="w", encoding="utf-8")
    try:
        tmp_ll.write(ir)
        tmp_ll.close()

        cmd = [clang, tmp_ll.name]

        for fname in _RUNTIME_FILES:
            fpath = os.path.join(runtime_dir, fname)
            if os.path.exists(fpath):
                cmd.append(fpath)

        extra = [] if sys.platform == "win32" else ["-lm", "-lpthread"]
        if sys.platform == "win32":
            cmd += ["-lgdi32", "-luser32", "-lwinmm"]

        cmd += ["-o", out] + extra

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            stderr = "\n".join(
                l for l in result.stderr.splitlines()
                if "overriding the module target triple" not in l
                and "warning generated" not in l
            )
            if stderr:
                print(stderr, file=sys.stderr)
            _die("Compilation failed")
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

    # Inject sprintf / strncmp declarations if used but not declared
    if "sprintf" in ir and "declare i32 @sprintf" not in ir:
        ir = ir.replace(
            "declare i32 @printf(i8*, ...)",
            "declare i32 @printf(i8*, ...)\ndeclare i32 @sprintf(i8*, i8*, ...)"
        )
    if "strncmp" in ir and "declare i32 @strncmp" not in ir:
        ir = ir.replace(
            "declare i32 @strcmp(i8*, i8*)",
            "declare i32 @strcmp(i8*, i8*)\ndeclare i32 @strncmp(i8*, i8*, i64)"
        )
    # Cabinet list helper
    if "rubble_cabinet_list_fill" in ir and "declare void @rubble_cabinet_list_fill" not in ir:
        ir = ir.replace(
            "declare void @rubble_cabinet_delete(i8*)",
            "declare void @rubble_cabinet_delete(i8*)\ndeclare void @rubble_cabinet_list_fill(i8*, i8*)"
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


# ── Error formatting ──────────────────────────────────────────────────────

def _die_with_source(msg: str, line: int, source_lines: list, col: int = None):
    """Print error with a source code snippet and exit."""
    print(msg, file=sys.stderr)
    if line and 1 <= line <= len(source_lines):
        print(f"\n   {line} │ {source_lines[line - 1]}", file=sys.stderr)
        # Show caret pointer if column is available
        if col is not None and col >= 0:
            # Calculate padding for the caret
            line_content = source_lines[line - 1]
            # Handle tabs by converting to spaces for caret positioning
            line_content_tabs = line_content[:col].expandtabs(4)
            caret_pos = len(line_content_tabs)
            print(f"      │ {' ' * caret_pos}^", file=sys.stderr)
        # Show context lines (2 before and after if available)
        context_start = max(1, line - 2)
        context_end = min(len(source_lines), line + 2)
        for ctx_line in range(context_start, context_end + 1):
            if ctx_line != line:
                print(f"   {ctx_line} │ {source_lines[ctx_line - 1]}", file=sys.stderr)
        print("", file=sys.stderr)
    sys.exit(1)


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


# ── Package manager ───────────────────────────────────────────────────────

_PKG_DIR_NAME = "packages"   # relative to the current working directory


def _install_package(url: str):
    """Download a .rbl file (or a directory manifest) from a URL and save it
    into the local packages/ folder so it can be reached with `gather`."""
    import urllib.request
    import urllib.error
    import json as _json

    pkg_dir = os.path.join(os.getcwd(), _PKG_DIR_NAME)
    os.makedirs(pkg_dir, exist_ok=True)

    print(f"  fetching  {url}")

    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()
    except urllib.error.URLError as e:
        _die(f"Could not fetch {url!r}: {e}")
        return

    # Determine filename from URL
    path_part = url.split("?")[0]          # strip query string
    filename  = os.path.basename(path_part) or "package.rbl"

    # If the URL returned JSON, treat it as a package manifest listing files
    if "json" in content_type or filename.endswith(".json"):
        try:
            manifest = _json.loads(raw.decode("utf-8"))
        except Exception as e:
            _die(f"Invalid manifest JSON: {e}")
            return
        files = manifest.get("files", [])
        if not files:
            _die("Manifest has no 'files' list")
            return
        # Each entry is either a URL string or {"name": "...", "url": "..."}
        base_url = url.rsplit("/", 1)[0]
        for entry in files:
            if isinstance(entry, str):
                file_url  = entry if entry.startswith("http") else f"{base_url}/{entry}"
                file_name = os.path.basename(entry)
            else:
                file_url  = entry.get("url", "")
                file_name = entry.get("name", os.path.basename(file_url))
            _download_file(file_url, os.path.join(pkg_dir, file_name))
        pkg_name = manifest.get("name", filename.replace(".json", ""))
        print(f"  installed {pkg_name!r}  →  {pkg_dir}/")
    else:
        # Single .rbl file — save directly
        dest = os.path.join(pkg_dir, filename)
        with open(dest, "wb") as f:
            f.write(raw)
        print(f"  installed {filename!r}  →  {dest}")

    # Remind the user how to use it
    module_name = os.path.splitext(filename)[0] if not filename.endswith(".json") else \
                  _json.loads(raw.decode("utf-8")).get("name", "package")
    print(f"\n  Use it with:  gather {module_name}")


def _download_file(url: str, dest: str):
    import urllib.request
    import urllib.error
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = resp.read()
        with open(dest, "wb") as f:
            f.write(data)
        print(f"    ↓  {os.path.basename(dest)}")
    except urllib.error.URLError as e:
        print(f"    ✗  {os.path.basename(dest)} — {e}", file=sys.stderr)


def _die(msg: str):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
