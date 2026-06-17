"""
Rubble Auto-Formatter — compiler/fmt.py

Formats a .rbl source file with consistent indentation and spacing.
Usage (internal):  from .fmt import format_source
CLI:               rubble fmt file.rbl        (formats in-place)
                   rubble fmt --check file.rbl (exit 1 if not formatted)
"""

import re
from typing import List


# ---------------------------------------------------------------------------
# Token-stream-free formatter
# We operate on lines rather than the full AST to keep the formatter
# independent of the compiler pipeline and robust to partially-broken files.
# Rules:
#   - 4-space indentation
#   - Space after keywords: if, elif, else, loop, for, match, case, recipe, etc.
#   - Spaces around binary operators: = == != < > <= >= + - * / % and or
#   - No space before comma/semicolon; exactly one space after comma
#   - Opening brace on same line as statement, with one space before {
#   - Closing brace on its own line
#   - Blank line between top-level declarations (recipe, blueprint)
#   - Strip trailing whitespace
#   - Single trailing newline
# ---------------------------------------------------------------------------

_KEYWORDS_SPACE = (
    "if", "elif", "else", "loop", "for", "in",
    "match", "case", "default", "recipe", "blueprint",
    "slot", "lock", "wire", "unwrap", "yield", "write",
    "wreck", "scrap", "gather", "and", "or", "not", "flip",
    "jam", "skip",
)

_TOP_LEVEL_DECLS = ("recipe", "blueprint")


def format_source(source: str) -> str:
    lines = source.splitlines()
    result: List[str] = []
    indent = 0
    prev_top_level = False

    for raw_line in lines:
        stripped = raw_line.strip()

        # Skip blank lines (we'll re-insert strategically)
        if not stripped:
            # Preserve at most one consecutive blank line
            if result and result[-1] != "":
                result.append("")
            continue

        # Comment lines — preserve as-is at current indent
        if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
            result.append(_indent(indent) + stripped)
            continue

        # Decrease indent before closing brace
        if stripped == "}" or stripped.startswith("} else") or stripped.startswith("} elif"):
            indent = max(0, indent - 1)

        # Blank line before top-level declarations
        is_top_decl = any(stripped.startswith(kw + " ") or stripped.startswith(kw + "(")
                          for kw in _TOP_LEVEL_DECLS)
        if is_top_decl and result and result[-1] != "" and indent == 0:
            result.append("")

        # Format the line content
        formatted = _format_line(stripped)
        result.append(_indent(indent) + formatted)

        # Increase indent after opening brace
        if stripped.endswith("{"):
            indent += 1

    # Ensure single trailing newline
    while result and result[-1] == "":
        result.pop()
    return "\n".join(result) + "\n"


def _indent(level: int) -> str:
    return "    " * level


def _format_line(line: str) -> str:
    """Apply spacing rules to a single stripped line."""
    # Normalise multiple spaces to single (but preserve string contents)
    line = _normalise_spaces_outside_strings(line)
    return line


def _normalise_spaces_outside_strings(line: str) -> str:
    """
    Walk the line char-by-char, tracking string context.
    Outside strings: normalise operator spacing and keyword spacing.
    Inside strings: leave everything alone.
    """
    # Collect tokens by splitting but preserving quoted strings
    segments = _split_preserving_strings(line)
    out_parts = []

    for i, seg in enumerate(segments):
        if seg.startswith('"') or seg.startswith("f\""):
            out_parts.append(seg)
            continue
        # Apply spacing rules to this non-string segment
        seg = _space_operators(seg)
        seg = _space_after_comma(seg)
        seg = _space_after_keyword(seg)
        seg = re.sub(r'  +', ' ', seg)  # collapse multiple spaces
        out_parts.append(seg)

    return "".join(out_parts).rstrip()


def _split_preserving_strings(line: str):
    """Split line into alternating non-string / string segments."""
    parts = []
    i = 0
    buf = []
    while i < len(line):
        # Interpolated string
        if i < len(line) - 1 and line[i] == 'f' and line[i+1] == '"':
            if buf:
                parts.append(''.join(buf))
                buf = []
            j = i + 2
            sbuf = ['f"']
            while j < len(line):
                c = line[j]
                if c == '\\' and j + 1 < len(line):
                    sbuf.append(c); sbuf.append(line[j+1]); j += 2; continue
                sbuf.append(c); j += 1
                if c == '"': break
            parts.append(''.join(sbuf))
            i = j
        elif line[i] == '"':
            if buf:
                parts.append(''.join(buf))
                buf = []
            j = i + 1
            sbuf = ['"']
            while j < len(line):
                c = line[j]
                if c == '\\' and j + 1 < len(line):
                    sbuf.append(c); sbuf.append(line[j+1]); j += 2; continue
                sbuf.append(c); j += 1
                if c == '"': break
            parts.append(''.join(sbuf))
            i = j
        else:
            buf.append(line[i])
            i += 1
    if buf:
        parts.append(''.join(buf))
    return parts


def _space_operators(s: str) -> str:
    """Ensure spaces around binary operators."""
    # Order matters: multi-char before single-char
    ops = ['==', '!=', '<=', '>=', '->', '=>', '<', '>', '=', '+', '-', '*', '/', '%']
    for op in ops:
        # Don't double-space already-spaced operators
        pattern = r'(?<![=!<>\-])' + re.escape(op) + r'(?!=)'
        if op in ('->', '=>', '==', '!=', '<=', '>='):
            pattern = re.escape(op)
        s = re.sub(r'\s*' + re.escape(op) + r'\s*', f' {op} ', s)
    # Clean up spaces around ( ) [ ] that shouldn't have them
    s = re.sub(r'\(\s+', '(', s)
    s = re.sub(r'\s+\)', ')', s)
    s = re.sub(r'\[\s+', '[', s)
    s = re.sub(r'\s+\]', ']', s)
    # Remove space before ( in calls
    s = re.sub(r'(\w)\s+\(', r'\1(', s)
    return s


def _space_after_comma(s: str) -> str:
    """Exactly one space after comma, none before."""
    s = re.sub(r'\s*,\s*', ', ', s)
    return s


def _space_after_keyword(s: str) -> str:
    """Ensure exactly one space after keywords that precede expressions."""
    for kw in _KEYWORDS_SPACE:
        s = re.sub(r'\b' + kw + r'\b\s+', kw + ' ', s)
        # if keyword is directly followed by ( with no space: add space for control flow
        if kw in ('if', 'elif', 'loop', 'for', 'match', 'case'):
            s = re.sub(r'\b' + kw + r'\b(?! )(?!\()', kw + ' ', s)
    return s
