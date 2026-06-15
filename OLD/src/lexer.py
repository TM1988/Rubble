"""
Rubble Lexer
Converts raw Rubble source text into a flat stream of tokens.
"""

import re
from dataclasses import dataclass
from typing import List, Optional


# ---------------------------------------------------------------------------
# Token types
# ---------------------------------------------------------------------------

TT = {
    # Literals
    "INT":        "INT",
    "DECIMAL":    "DECIMAL",
    "TEXT":       "TEXT",
    "TRUE":       "TRUE",
    "FALSE":      "FALSE",

    # Keywords
    "GATHER":     "GATHER",
    "RECIPE":     "RECIPE",
    "YIELD":      "YIELD",
    "LOOP":       "LOOP",
    "FOR":        "FOR",
    "IN":         "IN",
    "JAM":        "JAM",
    "WRECK":      "WRECK",
    "SLOT":       "SLOT",
    "LOCK":       "LOCK",
    "SMELT":      "SMELT",
    "SCRAP":      "SCRAP",
    "BLUEPRINT":  "BLUEPRINT",
    "BUILD":      "BUILD",
    "WIRE":       "WIRE",
    "UNWRAP":     "UNWRAP",
    "EMPTY":      "EMPTY",
    "FLIP":       "FLIP",
    "WRITE":      "WRITE",

    # Type names
    "UNIT":       "UNIT",
    "DECIMAL_T":  "DECIMAL_T",
    "TEXT_T":     "TEXT_T",
    "SWITCH":     "SWITCH",
    "CRATE":      "CRATE",

    # Control
    "IF":         "IF",
    "ELIF":       "ELIF",
    "ELSE":       "ELSE",

    # Identifiers & misc
    "IDENT":      "IDENT",
    "ARROW":      "ARROW",    # ->
    "ASSIGN":     "ASSIGN",   # =
    "EQ":         "EQ",       # ==
    "NEQ":        "NEQ",      # !=
    "LTE":        "LTE",      # <=
    "GTE":        "GTE",      # >=
    "LT":         "LT",       # <
    "GT":         "GT",       # >
    "PLUS":       "PLUS",
    "MINUS":      "MINUS",
    "STAR":       "STAR",
    "SLASH":      "SLASH",
    "PERCENT":    "PERCENT",
    "AND":        "AND",
    "OR":         "OR",
    "NOT":        "NOT",
    "DOT":        "DOT",
    "COMMA":      "COMMA",
    "COLON":      "COLON",
    "SEMICOLON":  "SEMICOLON",
    "LPAREN":     "LPAREN",
    "RPAREN":     "RPAREN",
    "LBRACE":     "LBRACE",
    "RBRACE":     "RBRACE",
    "LBRACKET":   "LBRACKET",
    "RBRACKET":   "RBRACKET",
    "EOF":        "EOF",
    "NEWLINE":    "NEWLINE",
}

# Keywords map: source text -> token type
KEYWORDS = {
    "gather":    TT["GATHER"],
    "recipe":    TT["RECIPE"],
    "yield":     TT["YIELD"],
    "loop":      TT["LOOP"],
    "for":       TT["FOR"],
    "in":        TT["IN"],
    "jam":       TT["JAM"],
    "wreck":     TT["WRECK"],
    "slot":      TT["SLOT"],
    "lock":      TT["LOCK"],
    "smelt":     TT["SMELT"],
    "scrap":     TT["SCRAP"],
    "blueprint": TT["BLUEPRINT"],
    "build":     TT["BUILD"],
    "wire":      TT["WIRE"],
    "unwrap":    TT["UNWRAP"],
    "empty":     TT["EMPTY"],
    "flip":      TT["FLIP"],
    "write":     TT["WRITE"],
    "true":      TT["TRUE"],
    "false":     TT["FALSE"],
    # Type names
    "unit":      TT["UNIT"],
    "decimal":   TT["DECIMAL_T"],
    "text":      TT["TEXT_T"],
    "switch":    TT["SWITCH"],
    "crate":     TT["CRATE"],
    # Control flow
    "if":        TT["IF"],
    "elif":      TT["ELIF"],
    "else":      TT["ELSE"],
    # Logic operators
    "and":       TT["AND"],
    "or":        TT["OR"],
    "not":       TT["NOT"],
}


@dataclass
class Token:
    type: str
    value: object
    line: int
    col: int

    def __repr__(self):
        return f"Token({self.type}, {self.value!r}, {self.line}:{self.col})"


# ---------------------------------------------------------------------------
# Lexer
# ---------------------------------------------------------------------------

class LexerError(Exception):
    def __init__(self, message, line, col):
        super().__init__(f"[Lexer Error] Line {line}, Col {col}: {message}")
        self.line = line
        self.col = col


class Lexer:
    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens: List[Token] = []

    def error(self, msg):
        raise LexerError(msg, self.line, self.col)

    def current(self) -> Optional[str]:
        if self.pos < len(self.source):
            return self.source[self.pos]
        return None

    def peek(self, offset=1) -> Optional[str]:
        idx = self.pos + offset
        if idx < len(self.source):
            return self.source[idx]
        return None

    def advance(self) -> str:
        ch = self.source[self.pos]
        self.pos += 1
        if ch == '\n':
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def skip_whitespace_and_comments(self):
        while self.pos < len(self.source):
            ch = self.current()
            # Skip spaces / tabs
            if ch in (' ', '\t', '\r'):
                self.advance()
            # Skip newlines (treated as whitespace — Rubble is brace-delimited)
            elif ch == '\n':
                self.advance()
            # Line comment: // ...
            elif ch == '/' and self.peek() == '/':
                while self.pos < len(self.source) and self.current() != '\n':
                    self.advance()
            # Block comment: /* ... */
            elif ch == '/' and self.peek() == '*':
                self.advance(); self.advance()  # consume /*
                while self.pos < len(self.source):
                    if self.current() == '*' and self.peek() == '/':
                        self.advance(); self.advance()
                        break
                    self.advance()
            else:
                break

    def read_string(self) -> Token:
        line, col = self.line, self.col
        self.advance()  # consume opening "
        buf = []
        while self.pos < len(self.source):
            ch = self.current()
            if ch == '\\':
                self.advance()
                esc = self.advance()
                escape_map = {'n': '\n', 't': '\t', 'r': '\r', '"': '"', '\\': '\\'}
                buf.append(escape_map.get(esc, esc))
            elif ch == '"':
                self.advance()  # consume closing "
                break
            else:
                buf.append(self.advance())
        else:
            self.error("Unterminated string literal")
        return Token(TT["TEXT"], ''.join(buf), line, col)

    def read_number(self) -> Token:
        line, col = self.line, self.col
        buf = []
        is_decimal = False
        while self.pos < len(self.source) and (self.current().isdigit() or self.current() == '.'):
            if self.current() == '.':
                if is_decimal:
                    break  # second dot — stop
                is_decimal = True
            buf.append(self.advance())
        raw = ''.join(buf)
        if is_decimal:
            return Token(TT["DECIMAL"], float(raw), line, col)
        return Token(TT["INT"], int(raw), line, col)

    def read_ident_or_keyword(self) -> Token:
        line, col = self.line, self.col
        buf = []
        while self.pos < len(self.source) and (self.current().isalnum() or self.current() == '_'):
            buf.append(self.advance())
        word = ''.join(buf)
        tt = KEYWORDS.get(word, TT["IDENT"])
        return Token(tt, word, line, col)

    def tokenize(self) -> List[Token]:
        while True:
            self.skip_whitespace_and_comments()
            if self.pos >= len(self.source):
                break

            line, col = self.line, self.col
            ch = self.current()

            # String literal
            if ch == '"':
                self.tokens.append(self.read_string())
                continue

            # Number
            if ch.isdigit() or (ch == '.' and self.peek() and self.peek().isdigit()):
                self.tokens.append(self.read_number())
                continue

            # Identifier / keyword
            if ch.isalpha() or ch == '_':
                self.tokens.append(self.read_ident_or_keyword())
                continue

            # Two-character operators
            two = ch + (self.peek() or '')
            if two == '->':
                self.tokens.append(Token(TT["ARROW"], '->', line, col))
                self.advance(); self.advance()
                continue
            if two == '==':
                self.tokens.append(Token(TT["EQ"], '==', line, col))
                self.advance(); self.advance()
                continue
            if two == '!=':
                self.tokens.append(Token(TT["NEQ"], '!=', line, col))
                self.advance(); self.advance()
                continue
            if two == '<=':
                self.tokens.append(Token(TT["LTE"], '<=', line, col))
                self.advance(); self.advance()
                continue
            if two == '>=':
                self.tokens.append(Token(TT["GTE"], '>=', line, col))
                self.advance(); self.advance()
                continue

            # Single-character operators & punctuation
            single_map = {
                '=': TT["ASSIGN"],
                '<': TT["LT"],
                '>': TT["GT"],
                '+': TT["PLUS"],
                '-': TT["MINUS"],
                '*': TT["STAR"],
                '/': TT["SLASH"],
                '%': TT["PERCENT"],
                '.': TT["DOT"],
                ',': TT["COMMA"],
                ':': TT["COLON"],
                ';': TT["SEMICOLON"],
                '(': TT["LPAREN"],
                ')': TT["RPAREN"],
                '{': TT["LBRACE"],
                '}': TT["RBRACE"],
                '[': TT["LBRACKET"],
                ']': TT["RBRACKET"],
            }
            if ch in single_map:
                self.tokens.append(Token(single_map[ch], ch, line, col))
                self.advance()
                continue

            self.error(f"Unexpected character: {ch!r}")

        self.tokens.append(Token(TT["EOF"], None, self.line, self.col))
        return self.tokens
