"""
Rubble Compiler — Lexer
Converts raw .rbl source into a token stream with full source locations.
"""

from dataclasses import dataclass
from typing import List, Optional

# ---------------------------------------------------------------------------
# Token kinds
# ---------------------------------------------------------------------------


class K:
    # Literals
    INT = "INT"
    DECIMAL = "DECIMAL"
    TEXT = "TEXT"
    TRUE = "TRUE"
    FALSE = "FALSE"

    # Keywords
    GATHER = "GATHER"
    RECIPE = "RECIPE"
    YIELD = "YIELD"
    LOOP = "LOOP"
    FOR = "FOR"
    IN = "IN"
    JAM = "JAM"
    SKIP = "SKIP"  # continue
    DOTDOTDOT = "DOTDOTDOT"  # ... variadic
    WRECK = "WRECK"
    SLOT = "SLOT"
    LOCK = "LOCK"
    SMELT = "SMELT"
    SCRAP = "SCRAP"
    BLUEPRINT = "BLUEPRINT"
    BUILD = "BUILD"
    WIRE = "WIRE"
    UNWRAP = "UNWRAP"
    EMPTY = "EMPTY"
    FLIP = "FLIP"
    WRITE = "WRITE"
    MATCH = "MATCH"  # switch/match statement
    CASE = "CASE"  # case arm in match
    DEFAULT = "DEFAULT"  # default arm in match
    SWITCH = "SWITCH"  # switch statement keyword

    # Types
    UNIT = "UNIT"
    I8 = "I8"
    I16 = "I16"
    I32 = "I32"
    U8 = "U8"
    U16 = "U16"
    U32 = "U32"
    U64 = "U64"
    DECIMAL_T = "DECIMAL_T"
    TEXT_T = "TEXT_T"
    SWITCH = "SWITCH"
    CRATE = "CRATE"

    # Control
    IF = "IF"
    ELIF = "ELIF"
    ELSE = "ELSE"
    FN = "FN"
    ENUM = "ENUM"
    CONST = "CONST"
    MODULE = "MODULE"
    TYPE = "TYPE"
    MAP = "MAP"
    SET = "SET"

    # Logic
    AND = "AND"
    OR = "OR"
    NOT = "NOT"

    # Identifiers / misc
    IDENT = "IDENT"
    ARROW = "ARROW"  # ->
    FAT_ARROW = "FAT_ARROW"  # =>  (used in match arms)
    ASSIGN = "ASSIGN"  # =
    EQ = "EQ"  # ==
    NEQ = "NEQ"  # !=
    LTE = "LTE"  # <=
    GTE = "GTE"  # >=
    LT = "LT"  # <
    GT = "GT"  # >
    PLUS = "PLUS"
    MINUS = "MINUS"
    STAR = "STAR"
    SLASH = "SLASH"
    PERCENT = "PERCENT"
    DOT = "DOT"
    DOTDOT = "DOTDOT"  # .. for range expressions
    AT = "AT"  # @ for decorators
    QUESTION = "QUESTION"  # ? for nullable types
    DOTQUESTION = "DOTQUESTION"  # ?. for optional chaining
    QUESTIONQUESTION = "QUESTIONQUESTION"  # ?? for null coalescing
    COMMA = "COMMA"
    COLON = "COLON"
    SEMICOLON = "SEMICOLON"
    LPAREN = "LPAREN"
    RPAREN = "RPAREN"
    LBRACE = "LBRACE"
    RBRACE = "RBRACE"
    LBRACKET = "LBRACKET"
    RBRACKET = "RBRACKET"
    # String interpolation — f"..." tokens
    ITEXT_START = "ITEXT_START"  # opening f"
    ITEXT_END = "ITEXT_END"  # closing "
    ITEXT_CHUNK = "ITEXT_CHUNK"  # literal text segment between { }
    ITEXT_EXPR_START = "ITEXT_EXPR_START"  # {
    ITEXT_EXPR_END = "ITEXT_EXPR_END"  # }
    EOF = "EOF"


KEYWORDS = {
    "gather": K.GATHER,
    "recipe": K.RECIPE,
    "yield": K.YIELD,
    "loop": K.LOOP,
    "for": K.FOR,
    "in": K.IN,
    "jam": K.JAM,
    "skip": K.SKIP,
    "wreck": K.WRECK,
    "slot": K.SLOT,
    "lock": K.LOCK,
    "smelt": K.SMELT,
    "scrap": K.SCRAP,
    "blueprint": K.BLUEPRINT,
    "build": K.BUILD,
    "wire": K.WIRE,
    "unwrap": K.UNWRAP,
    "empty": K.EMPTY,
    "flip": K.FLIP,
    "write": K.WRITE,
    "match": K.MATCH,
    "case": K.CASE,
    "default": K.DEFAULT,
    "true": K.TRUE,
    "false": K.FALSE,
    "unit": K.UNIT,
    "i8": K.I8,
    "i16": K.I16,
    "i32": K.I32,
    "u8": K.U8,
    "u16": K.U16,
    "u32": K.U32,
    "u64": K.U64,
    "decimal": K.DECIMAL_T,
    "text": K.TEXT_T,
    "switch": K.SWITCH,
    "crate": K.CRATE,
    "if": K.IF,
    "elif": K.ELIF,
    "else": K.ELSE,
    "fn": K.FN,
    "enum": K.ENUM,
    "const": K.CONST,
    "module": K.MODULE,
    "type": K.TYPE,
    "map": K.MAP,
    "set": K.SET,
    "and": K.AND,
    "or": K.OR,
    "not": K.NOT,
}


@dataclass
class Token:
    kind: str
    value: object
    line: int
    col: int

    def __repr__(self):
        return f"Token({self.kind}, {self.value!r}, {self.line}:{self.col})"


# ---------------------------------------------------------------------------
# Lexer
# ---------------------------------------------------------------------------


class LexError(Exception):
    def __init__(self, msg, line, col):
        super().__init__(f"[Lex Error] {line}:{col}: {msg}")
        self.line = line
        self.col = col


class Lexer:
    def __init__(self, source: str, filename: str = "<input>"):
        # Strip UTF-8 BOM if present (written by some editors/tools on Windows)
        if source.startswith("\ufeff"):
            source = source[1:]
        self.src = source
        self.filename = filename
        self.pos = 0
        self.line = 1
        self.col = 1

    def _cur(self) -> Optional[str]:
        return self.src[self.pos] if self.pos < len(self.src) else None

    def _peek(self, n=1) -> Optional[str]:
        i = self.pos + n
        return self.src[i] if i < len(self.src) else None

    def _adv(self) -> str:
        ch = self.src[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _skip(self):
        """Skip whitespace and comments."""
        while self.pos < len(self.src):
            ch = self._cur()
            if ch in " \t\r\n":
                self._adv()
            elif ch == "/" and self._peek() == "/":
                while self.pos < len(self.src) and self._cur() != "\n":
                    self._adv()
            elif ch == "/" and self._peek() == "*":
                self._adv()
                self._adv()
                while self.pos < len(self.src):
                    if self._cur() == "*" and self._peek() == "/":
                        self._adv()
                        self._adv()
                        break
                    self._adv()
            else:
                break

    def _string(self) -> Token:
        line, col = self.line, self.col
        self._adv()  # opening "
        buf = []
        while self.pos < len(self.src):
            ch = self._cur()
            if ch == "\\":
                self._adv()
                esc = self._adv()
                buf.append(
                    {
                        "n": "\n",
                        "t": "\t",
                        "r": "\r",
                        '"': '"',
                        "\\": "\\",
                        "0": "\0",
                    }.get(esc, esc)
                )
            elif ch == '"':
                self._adv()
                return Token(K.TEXT, "".join(buf), line, col)
            else:
                buf.append(self._adv())
        raise LexError("Unterminated string literal", line, col)

    def _interp_string(self, tokens: list, line: int, col: int):
        """Lex an interpolated string f"..." and emit synthetic tokens.

        Emits:
          ITEXT_START
          (ITEXT_CHUNK text)*  or  (ITEXT_EXPR_START <expr tokens> ITEXT_EXPR_END)*
          ITEXT_END
        """
        self._adv()  # skip the opening "
        tokens.append(Token(K.ITEXT_START, None, line, col))

        buf = []
        while self.pos < len(self.src):
            ch = self._cur()
            if ch == '"':
                self._adv()
                # flush remaining text chunk
                if buf:
                    tokens.append(Token(K.ITEXT_CHUNK, "".join(buf), line, col))
                    buf = []
                tokens.append(Token(K.ITEXT_END, None, self.line, self.col))
                return
            elif ch == "\\":
                self._adv()
                esc = self._adv()
                buf.append(
                    {
                        "n": "\n",
                        "t": "\t",
                        "r": "\r",
                        '"': '"',
                        "\\": "\\",
                        "0": "\0",
                    }.get(esc, esc)
                )
            elif ch == "{":
                # flush text so far
                if buf:
                    tokens.append(Token(K.ITEXT_CHUNK, "".join(buf), line, col))
                    buf = []
                self._adv()  # skip {
                tokens.append(Token(K.ITEXT_EXPR_START, "{", self.line, self.col))
                # Lex the inner expression until matching }
                depth = 1
                while self.pos < len(self.src) and depth > 0:
                    self._skip()
                    if self._cur() == "}":
                        depth -= 1
                        if depth == 0:
                            self._adv()
                            tokens.append(
                                Token(K.ITEXT_EXPR_END, "}", self.line, self.col)
                            )
                            break
                        self._adv()
                        tokens.append(Token(K.RBRACE, "}", self.line, self.col))
                    elif self._cur() == "{":
                        depth += 1
                        self._adv()
                        tokens.append(Token(K.LBRACE, "{", self.line, self.col))
                    elif self._cur() == '"':
                        tokens.append(self._string())
                    elif self._cur() and self._cur().isdigit():
                        tokens.append(self._number())
                    elif self._cur() and (self._cur().isalpha() or self._cur() == "_"):
                        tokens.append(self._ident())
                    else:
                        tokens.extend(self._single_token())
            else:
                buf.append(self._adv())

        raise LexError("Unterminated interpolated string", line, col)

    def _number(self) -> Token:
        line, col = self.line, self.col
        buf = []
        dot = False
        while self.pos < len(self.src) and (
            self._cur().isdigit() or (self._cur() == "." and not dot and self._peek() and self._peek().isdigit())
        ):
            if self._cur() == ".":
                dot = True
            buf.append(self._adv())
        raw = "".join(buf)
        if dot:
            return Token(K.DECIMAL, float(raw), line, col)
        return Token(K.INT, int(raw), line, col)

    def _ident(self) -> Token:
        line, col = self.line, self.col
        buf = []
        while self.pos < len(self.src) and (
            self._cur().isalnum() or self._cur() == "_"
        ):
            buf.append(self._adv())
        word = "".join(buf)
        kind = KEYWORDS.get(word, K.IDENT)
        return Token(kind, word, line, col)

    def _single_token(self) -> list:
        """Lex one or two-char operator, return list of tokens (1 item usually)."""
        line, col = self.line, self.col
        ch = self._cur()
        two = ch + (self._peek() or "")

        if two == "->":
            self._adv()
            self._adv()
            return [Token(K.ARROW, "->", line, col)]
        if two == "=>":
            self._adv()
            self._adv()
            return [Token(K.FAT_ARROW, "=>", line, col)]
        if two == "?.":  # Optional chaining
            self._adv()
            self._adv()
            return [Token(K.DOTQUESTION, "?.", line, col)]
        if two == "??":  # Null coalescing
            self._adv()
            self._adv()
            return [Token(K.QUESTIONQUESTION, "??", line, col)]
        if two == "==":
            self._adv()
            self._adv()
            return [Token(K.EQ, "==", line, col)]
        if two == "!=":
            self._adv()
            self._adv()
            return [Token(K.NEQ, "!=", line, col)]
        if two == "<=":
            self._adv()
            self._adv()
            return [Token(K.LTE, "<=", line, col)]
        if two == ">=":
            self._adv()
            self._adv()
            return [Token(K.GTE, ">=", line, col)]
        if two == "..":
            self._adv()
            self._adv()
            return [Token(K.DOTDOT, "..", line, col)]

        three = two + (self._peek(2) or "")
        if three == "...":
            self._adv()
            self._adv()
            self._adv()
            return [Token(K.DOTDOTDOT, "...", line, col)]

        single = {
            "=": K.ASSIGN,
            "<": K.LT,
            ">": K.GT,
            "+": K.PLUS,
            "-": K.MINUS,
            "*": K.STAR,
            "/": K.SLASH,
            "%": K.PERCENT,
            ".": K.DOT,
            "@": K.AT,
            "|": K.OR,
            "&": K.AND,
            "?": K.QUESTION,
            ",": K.COMMA,
            ":": K.COLON,
            ";": K.SEMICOLON,
            "(": K.LPAREN,
            ")": K.RPAREN,
            "{": K.LBRACE,
            "}": K.RBRACE,
            "[": K.LBRACKET,
            "]": K.RBRACKET,
        }
        if ch in single:
            self._adv()
            return [Token(single[ch], ch, line, col)]

        raise LexError(f"Unexpected character: {ch!r}", line, col)

    def tokenize(self) -> List[Token]:
        tokens = []
        while True:
            self._skip()
            if self.pos >= len(self.src):
                break
            line, col = self.line, self.col
            ch = self._cur()

            # Interpolated string: f"..."
            if ch == "f" and self._peek() == '"':
                self._adv()  # skip 'f'
                self._interp_string(tokens, line, col)
                continue

            if ch == '"':
                tokens.append(self._string())
                continue
            # Check for .. (range) before checking for numbers
            if ch == "." and self._peek() == ".":
                self._adv()
                self._adv()
                tokens.append(Token(K.DOTDOT, "..", line, col))
                continue
            # Check for numbers (but not if it's a dot that could be part of ..)
            if ch.isdigit() or (ch == "." and self._peek() and self._peek().isdigit() and self._peek(1) != "."):
                tokens.append(self._number())
                continue
            if ch.isalpha() or ch == "_":
                tokens.append(self._ident())
                continue

            tokens.extend(self._single_token())

        tokens.append(Token(K.EOF, None, self.line, self.col))
        return tokens
