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
    INT        = "INT"
    DECIMAL    = "DECIMAL"
    TEXT       = "TEXT"
    TRUE       = "TRUE"
    FALSE      = "FALSE"

    # Keywords
    GATHER     = "GATHER"
    RECIPE     = "RECIPE"
    YIELD      = "YIELD"
    LOOP       = "LOOP"
    FOR        = "FOR"
    IN         = "IN"
    JAM        = "JAM"
    WRECK      = "WRECK"
    SLOT       = "SLOT"
    LOCK       = "LOCK"
    SMELT      = "SMELT"
    SCRAP      = "SCRAP"
    BLUEPRINT  = "BLUEPRINT"
    BUILD      = "BUILD"
    WIRE       = "WIRE"
    UNWRAP     = "UNWRAP"
    EMPTY      = "EMPTY"
    FLIP       = "FLIP"
    WRITE      = "WRITE"

    # Types
    UNIT       = "UNIT"
    DECIMAL_T  = "DECIMAL_T"
    TEXT_T     = "TEXT_T"
    SWITCH     = "SWITCH"
    CRATE      = "CRATE"

    # Control
    IF         = "IF"
    ELIF       = "ELIF"
    ELSE       = "ELSE"

    # Logic
    AND        = "AND"
    OR         = "OR"
    NOT        = "NOT"

    # Identifiers / misc
    IDENT      = "IDENT"
    ARROW      = "ARROW"      # ->
    ASSIGN     = "ASSIGN"     # =
    EQ         = "EQ"         # ==
    NEQ        = "NEQ"        # !=
    LTE        = "LTE"        # <=
    GTE        = "GTE"        # >=
    LT         = "LT"         # <
    GT         = "GT"         # >
    PLUS       = "PLUS"
    MINUS      = "MINUS"
    STAR       = "STAR"
    SLASH      = "SLASH"
    PERCENT    = "PERCENT"
    DOT        = "DOT"
    COMMA      = "COMMA"
    COLON      = "COLON"
    SEMICOLON  = "SEMICOLON"
    LPAREN     = "LPAREN"
    RPAREN     = "RPAREN"
    LBRACE     = "LBRACE"
    RBRACE     = "RBRACE"
    LBRACKET   = "LBRACKET"
    RBRACKET   = "RBRACKET"
    EOF        = "EOF"


KEYWORDS = {
    "gather":    K.GATHER,
    "recipe":    K.RECIPE,
    "yield":     K.YIELD,
    "loop":      K.LOOP,
    "for":       K.FOR,
    "in":        K.IN,
    "jam":       K.JAM,
    "wreck":     K.WRECK,
    "slot":      K.SLOT,
    "lock":      K.LOCK,
    "smelt":     K.SMELT,
    "scrap":     K.SCRAP,
    "blueprint": K.BLUEPRINT,
    "build":     K.BUILD,
    "wire":      K.WIRE,
    "unwrap":    K.UNWRAP,
    "empty":     K.EMPTY,
    "flip":      K.FLIP,
    "write":     K.WRITE,
    "true":      K.TRUE,
    "false":     K.FALSE,
    "unit":      K.UNIT,
    "decimal":   K.DECIMAL_T,
    "text":      K.TEXT_T,
    "switch":    K.SWITCH,
    "crate":     K.CRATE,
    "if":        K.IF,
    "elif":      K.ELIF,
    "else":      K.ELSE,
    "and":       K.AND,
    "or":        K.OR,
    "not":       K.NOT,
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
        if ch == '\n':
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _skip(self):
        """Skip whitespace and comments."""
        while self.pos < len(self.src):
            ch = self._cur()
            if ch in ' \t\r\n':
                self._adv()
            elif ch == '/' and self._peek() == '/':
                while self.pos < len(self.src) and self._cur() != '\n':
                    self._adv()
            elif ch == '/' and self._peek() == '*':
                self._adv(); self._adv()
                while self.pos < len(self.src):
                    if self._cur() == '*' and self._peek() == '/':
                        self._adv(); self._adv()
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
            if ch == '\\':
                self._adv()
                esc = self._adv()
                buf.append({'n':'\n','t':'\t','r':'\r','"':'"','\\':'\\','0':'\0'}.get(esc, esc))
            elif ch == '"':
                self._adv()
                return Token(K.TEXT, ''.join(buf), line, col)
            else:
                buf.append(self._adv())
        raise LexError("Unterminated string literal", line, col)

    def _number(self) -> Token:
        line, col = self.line, self.col
        buf = []
        dot = False
        while self.pos < len(self.src) and (self._cur().isdigit() or (self._cur() == '.' and not dot)):
            if self._cur() == '.':
                dot = True
            buf.append(self._adv())
        raw = ''.join(buf)
        if dot:
            return Token(K.DECIMAL, float(raw), line, col)
        return Token(K.INT, int(raw), line, col)

    def _ident(self) -> Token:
        line, col = self.line, self.col
        buf = []
        while self.pos < len(self.src) and (self._cur().isalnum() or self._cur() == '_'):
            buf.append(self._adv())
        word = ''.join(buf)
        kind = KEYWORDS.get(word, K.IDENT)
        return Token(kind, word, line, col)

    def tokenize(self) -> List[Token]:
        tokens = []
        while True:
            self._skip()
            if self.pos >= len(self.src):
                break
            line, col = self.line, self.col
            ch = self._cur()

            if ch == '"':
                tokens.append(self._string())
                continue
            if ch.isdigit() or (ch == '.' and self._peek() and self._peek().isdigit()):
                tokens.append(self._number())
                continue
            if ch.isalpha() or ch == '_':
                tokens.append(self._ident())
                continue

            # Two-char operators
            two = ch + (self._peek() or '')
            if two == '->': tokens.append(Token(K.ARROW,  '->', line, col)); self._adv(); self._adv(); continue
            if two == '==': tokens.append(Token(K.EQ,     '==', line, col)); self._adv(); self._adv(); continue
            if two == '!=': tokens.append(Token(K.NEQ,    '!=', line, col)); self._adv(); self._adv(); continue
            if two == '<=': tokens.append(Token(K.LTE,    '<=', line, col)); self._adv(); self._adv(); continue
            if two == '>=': tokens.append(Token(K.GTE,    '>=', line, col)); self._adv(); self._adv(); continue

            # Single-char
            single = {
                '=': K.ASSIGN, '<': K.LT, '>': K.GT,
                '+': K.PLUS,   '-': K.MINUS, '*': K.STAR,
                '/': K.SLASH,  '%': K.PERCENT, '.': K.DOT,
                ',': K.COMMA,  ':': K.COLON, ';': K.SEMICOLON,
                '(': K.LPAREN, ')': K.RPAREN,
                '{': K.LBRACE, '}': K.RBRACE,
                '[': K.LBRACKET, ']': K.RBRACKET,
            }
            if ch in single:
                tokens.append(Token(single[ch], ch, line, col))
                self._adv()
                continue

            raise LexError(f"Unexpected character: {ch!r}", line, col)

        tokens.append(Token(K.EOF, None, self.line, self.col))
        return tokens
