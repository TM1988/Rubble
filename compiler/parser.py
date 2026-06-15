"""
Rubble Compiler — Recursive-Descent Parser
Produces a typed AST from a token stream.
"""

from typing import List, Optional, Tuple
from .lexer import Token, K
from .ast_nodes import *


class ParseError(Exception):
    def __init__(self, msg, tok: Token):
        super().__init__(f"[Parse Error] {tok.line}:{tok.col}: {msg} (got {tok.kind} {tok.value!r})")
        self.tok = tok


class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _cur(self) -> Token:
        return self.tokens[self.pos]

    def _peek(self, n=1) -> Token:
        i = self.pos + n
        return self.tokens[min(i, len(self.tokens)-1)]

    def _adv(self) -> Token:
        t = self.tokens[self.pos]
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        return t

    def _check(self, *kinds) -> bool:
        return self._cur().kind in kinds

    def _match(self, *kinds) -> Optional[Token]:
        if self._cur().kind in kinds:
            return self._adv()
        return None

    def _expect(self, kind: str, msg: str = "") -> Token:
        if self._cur().kind == kind:
            return self._adv()
        raise ParseError(msg or f"Expected {kind}", self._cur())

    def _loc(self) -> Loc:
        t = self._cur()
        return Loc(t.line, t.col)

    def _err(self, msg: str):
        raise ParseError(msg, self._cur())

    # ------------------------------------------------------------------
    # Entry
    # ------------------------------------------------------------------

    def parse(self) -> Program:
        stmts = []
        while not self._check(K.EOF):
            stmts.append(self._stmt())
        return Program(stmts)

    # ------------------------------------------------------------------
    # Statements
    # ------------------------------------------------------------------

    def _stmt(self) -> Node:
        k = self._cur().kind
        if k == K.GATHER:    return self._gather()
        if k == K.RECIPE:    return self._recipe()
        if k == K.BLUEPRINT: return self._blueprint()
        if k in (K.SLOT, K.LOCK): return self._slot()
        if k == K.WRITE:     return self._write()
        if k == K.YIELD:     return self._yield()
        if k == K.JAM:
            loc = self._loc(); self._adv(); self._match(K.SEMICOLON)
            return JamStmt(loc)
        if k == K.WRECK:     return self._wreck()
        if k == K.SCRAP:     return self._scrap()
        if k == K.LOOP:      return self._loop()
        if k == K.FOR:       return self._foreach()
        if k == K.IF:        return self._if()
        return self._assign_or_expr()

    def _gather(self) -> GatherStmt:
        loc = self._loc()
        self._adv()
        tok = self._cur()
        if tok.kind in (K.TEXT, K.IDENT):
            name = self._adv().value
        else:
            self._err("Expected module name after 'gather'")
        self._match(K.SEMICOLON)
        return GatherStmt(str(name), loc)

    def _recipe(self) -> RecipeDecl:
        loc = self._loc()
        self._adv()
        name = self._expect(K.IDENT, "Expected recipe name").value
        self._expect(K.LPAREN)
        params = []
        while not self._check(K.RPAREN):
            pname = self._expect(K.IDENT, "Expected parameter name").value
            self._expect(K.COLON)
            ptype = self._type()
            params.append(Param(pname, ptype))
            if not self._match(K.COMMA):
                break
        self._expect(K.RPAREN)
        # Return type is optional — default to empty (void)
        if self._match(K.ARROW):
            ret = self._type()
        else:
            ret = TypeNode("empty")
        body = self._block()
        return RecipeDecl(name, params, ret, body, loc)

    def _blueprint(self) -> BlueprintDecl:
        loc = self._loc()
        self._adv()
        name = self._expect(K.IDENT, "Expected blueprint name").value
        self._expect(K.LBRACE)
        fields = []
        while not self._check(K.RBRACE):
            fname = self._expect(K.IDENT, "Expected field name").value
            self._expect(K.COLON)
            ftype = self._type()
            fields.append(Param(fname, ftype))
            self._match(K.COMMA)
            self._match(K.SEMICOLON)
        self._expect(K.RBRACE)
        return BlueprintDecl(name, fields, loc)

    def _slot(self) -> SlotDecl:
        loc = self._loc()
        is_lock = bool(self._match(K.LOCK))
        self._expect(K.SLOT)
        name = self._expect(K.IDENT, "Expected variable name").value
        self._expect(K.ASSIGN)
        val = self._expr()
        self._match(K.SEMICOLON)
        return SlotDecl(name, val, is_lock, loc)

    def _write(self) -> WriteStmt:
        loc = self._loc(); self._adv()
        # Support both   write expr   and   write(expr)
        paren = bool(self._match(K.LPAREN))
        val = self._expr()
        if paren: self._expect(K.RPAREN)
        self._match(K.SEMICOLON)
        return WriteStmt(val, loc)

    def _yield(self) -> YieldStmt:
        loc = self._loc(); self._adv()
        val = self._expr()
        self._match(K.SEMICOLON)
        return YieldStmt(val, loc)

    def _wreck(self) -> WreckStmt:
        loc = self._loc(); self._adv()
        paren = bool(self._match(K.LPAREN))
        msg = self._expr()
        if paren: self._expect(K.RPAREN)
        self._match(K.SEMICOLON)
        return WreckStmt(msg, loc)

    def _scrap(self) -> ScrapStmt:
        loc = self._loc(); self._adv()
        name = self._expect(K.IDENT, "Expected variable name after 'scrap'").value
        self._match(K.SEMICOLON)
        return ScrapStmt(name, loc)

    def _loop(self) -> LoopStmt:
        loc = self._loc(); self._adv()
        cond = self._expr()
        body = self._block()
        return LoopStmt(cond, body, loc)

    def _foreach(self) -> ForEachStmt:
        loc = self._loc(); self._adv()
        var = self._expect(K.IDENT, "Expected loop variable").value
        self._expect(K.IN)
        it = self._expr()
        body = self._block()
        return ForEachStmt(var, it, body, loc)

    def _if(self) -> IfStmt:
        loc = self._loc(); self._adv()
        cond = self._expr()
        then = self._block()
        elifs = []
        else_ = None
        while self._check(K.ELIF):
            self._adv()
            ec = self._expr()
            eb = self._block()
            elifs.append((ec, eb))
        if self._match(K.ELSE):
            else_ = self._block()
        return IfStmt(cond, then, elifs, else_, loc)

    def _assign_or_expr(self) -> Node:
        loc = self._loc()
        expr = self._expr()
        if self._match(K.ASSIGN):
            rhs = self._expr()
            self._match(K.SEMICOLON)
            return AssignStmt(expr, rhs, loc)
        self._match(K.SEMICOLON)
        return ExprStmt(expr, loc)

    # ------------------------------------------------------------------
    # Block
    # ------------------------------------------------------------------

    def _block(self) -> List[Node]:
        self._expect(K.LBRACE)
        stmts = []
        while not self._check(K.RBRACE) and not self._check(K.EOF):
            stmts.append(self._stmt())
        self._expect(K.RBRACE)
        return stmts

    # ------------------------------------------------------------------
    # Type parsing
    # ------------------------------------------------------------------

    def _type(self) -> TypeNode:
        TYPE_MAP = {
            K.UNIT:      "unit",
            K.DECIMAL_T: "decimal",
            K.TEXT_T:    "text",
            K.SWITCH:    "switch",
            K.CRATE:     "crate",
            K.EMPTY:     "empty",
        }
        tok = self._cur()
        if tok.kind == K.WIRE:
            self._adv()
            self._expect(K.LT)
            inner = self._type()
            self._expect(K.GT)
            return TypeNode("wire", inner)
        if tok.kind in TYPE_MAP:
            self._adv()
            name = TYPE_MAP[tok.kind]
            if name == "crate" and self._match(K.LBRACKET):
                inner = self._type()
                self._expect(K.RBRACKET)
                return TypeNode("crate", inner)
            return TypeNode(name)
        if tok.kind == K.IDENT:
            self._adv()
            return TypeNode(tok.value)
        self._err("Expected a type name")

    # ------------------------------------------------------------------
    # Expressions — precedence climbing
    # ------------------------------------------------------------------

    def _expr(self) -> Node:
        return self._or()

    def _or(self) -> Node:
        left = self._and()
        while self._check(K.OR):
            loc = self._loc(); op = self._adv().value
            left = BinOp(left, op, self._and(), loc)
        return left

    def _and(self) -> Node:
        left = self._eq()
        while self._check(K.AND):
            loc = self._loc(); op = self._adv().value
            left = BinOp(left, op, self._eq(), loc)
        return left

    def _eq(self) -> Node:
        left = self._cmp()
        while self._check(K.EQ, K.NEQ):
            loc = self._loc(); op = self._adv().value
            left = BinOp(left, op, self._cmp(), loc)
        return left

    def _cmp(self) -> Node:
        left = self._add()
        while self._check(K.LT, K.GT, K.LTE, K.GTE):
            loc = self._loc(); op = self._adv().value
            left = BinOp(left, op, self._add(), loc)
        return left

    def _add(self) -> Node:
        left = self._mul()
        while self._check(K.PLUS, K.MINUS):
            loc = self._loc(); op = self._adv().value
            left = BinOp(left, op, self._mul(), loc)
        return left

    def _mul(self) -> Node:
        left = self._unary()
        while self._check(K.STAR, K.SLASH, K.PERCENT):
            loc = self._loc(); op = self._adv().value
            left = BinOp(left, op, self._unary(), loc)
        return left

    def _unary(self) -> Node:
        loc = self._loc()
        if self._check(K.MINUS):
            self._adv(); return UnaryOp("-", self._unary(), loc)
        if self._check(K.FLIP) or self._check(K.NOT):
            self._adv(); return UnaryOp("flip", self._unary(), loc)
        return self._postfix()

    def _postfix(self) -> Node:
        expr = self._primary()
        while True:
            if self._check(K.DOT):
                loc = self._loc(); self._adv()
                # Accept any token as field/method name after dot
                tok = self._cur()
                if tok.kind == K.EOF:
                    self._err("Expected field or method name after '.'")
                field = str(tok.value); self._adv()
                if self._check(K.LPAREN):
                    self._adv()
                    args = self._arglist()
                    self._expect(K.RPAREN)
                    expr = CallExpr(FieldExpr(expr, field, loc), args, loc)
                else:
                    expr = FieldExpr(expr, field, loc)
            elif self._check(K.LBRACKET):
                loc = self._loc(); self._adv()
                idx = self._expr()
                self._expect(K.RBRACKET)
                expr = IndexExpr(expr, idx, loc)
            else:
                break
        return expr

    def _primary(self) -> Node:
        loc = self._loc()
        tok = self._cur()

        if tok.kind == K.INT:     self._adv(); return IntLit(tok.value, loc)
        if tok.kind == K.DECIMAL: self._adv(); return DecimalLit(tok.value, loc)
        if tok.kind == K.TEXT:    self._adv(); return TextLit(tok.value, loc)
        if tok.kind == K.TRUE:    self._adv(); return SwitchLit(True, loc)
        if tok.kind == K.FALSE:   self._adv(); return SwitchLit(False, loc)
        if tok.kind == K.EMPTY:   self._adv(); return EmptyLit(loc)

        if tok.kind == K.LBRACKET:
            self._adv()
            elems = []
            while not self._check(K.RBRACKET):
                elems.append(self._expr())
                if not self._match(K.COMMA): break
            self._expect(K.RBRACKET)
            return CrateLit(elems, loc)

        if tok.kind == K.LPAREN:
            self._adv()
            e = self._expr()
            self._expect(K.RPAREN)
            return e

        if tok.kind == K.SMELT:
            self._adv()
            self._expect(K.LPAREN)
            val = self._expr()
            self._expect(K.COMMA)
            t = self._type()
            self._expect(K.RPAREN)
            return SmeltExpr(val, t, loc)

        if tok.kind == K.BUILD:
            self._adv()
            name = self._expect(K.IDENT, "Expected blueprint name after 'build'").value
            self._expect(K.LPAREN)
            kwargs = []
            while not self._check(K.RPAREN):
                fn = self._expect(K.IDENT, "Expected field name").value
                self._expect(K.COLON)
                fv = self._expr()
                kwargs.append((fn, fv))
                if not self._match(K.COMMA): break
            self._expect(K.RPAREN)
            return BuildExpr(name, kwargs, loc)

        if tok.kind == K.WIRE:
            self._adv()
            name = self._expect(K.IDENT, "Expected variable name after 'wire'").value
            return WireExpr(name, loc)

        if tok.kind == K.UNWRAP:
            self._adv()
            target = self._primary()
            return UnwrapExpr(target, loc)

        if tok.kind == K.IDENT:
            self._adv()
            if self._check(K.LPAREN):
                self._adv()
                args = self._arglist()
                self._expect(K.RPAREN)
                return CallExpr(Ident(tok.value, loc), args, loc)
            return Ident(tok.value, loc)

        self._err(f"Unexpected token in expression")

    def _arglist(self) -> List[Node]:
        args = []
        while not self._check(K.RPAREN) and not self._check(K.EOF):
            args.append(self._expr())
            if not self._match(K.COMMA): break
        return args
