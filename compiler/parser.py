"""
Rubble Compiler — Recursive-Descent Parser
Produces a typed AST from a token stream.
"""

from typing import List, Optional, Tuple

from .ast_nodes import *
from .lexer import K, Token


class ParseError(Exception):
    def __init__(self, msg, tok: Token):
        super().__init__(
            f"[Parse Error] {tok.line}:{tok.col}: {msg} (got {tok.kind} {tok.value!r})"
        )
        self.tok = tok


class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0
        self.errors: List[str] = []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _cur(self) -> Token:
        return self.tokens[self.pos]

    def _peek(self, n=1) -> Token:
        i = self.pos + n
        return self.tokens[min(i, len(self.tokens) - 1)]

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
        error_msg = msg or f"Expected {kind}"
        self.errors.append(f"[Parse Error] {self._cur().line}:{self._cur().col}: {error_msg} (got {self._cur().kind} {self._cur().value!r})")
        # Try to recover by advancing to the next token
        self._adv()
        return self._cur()

    def _loc(self) -> Loc:
        t = self._cur()
        return Loc(t.line, t.col)

    def _err(self, msg: str):
        self.errors.append(f"[Parse Error] {self._cur().line}:{self._cur().col}: {msg}")
        # Try to recover by advancing to the next token
        self._adv()

    # ------------------------------------------------------------------
    # Entry
    # ------------------------------------------------------------------

    def parse(self) -> Program:
        stmts = []
        while not self._check(K.EOF):
            try:
                stmts.append(self._stmt())
            except Exception as e:
                # Catch any unexpected errors and add them to the error list
                self.errors.append(str(e))
                self._adv()
        # Print all errors at the end
        for error in self.errors:
            print(error)
        return Program(stmts)

    # ------------------------------------------------------------------
    # Statements
    # ------------------------------------------------------------------

    def _stmt(self) -> Node:
        k = self._cur().kind
        # Handle decorators before recipes/blueprints
        if k == K.AT:
            decorators = self._decorators()
            k = self._cur().kind
            if k == K.RECIPE:
                return self._recipe(decorators)
            elif k == K.BLUEPRINT:
                return self._blueprint(decorators)
            else:
                self._err("Decorators can only be applied to recipes or blueprints")
        if k == K.GATHER:
            return self._gather()
        if k == K.RECIPE:
            return self._recipe()
        if k == K.BLUEPRINT:
            return self._blueprint()
        if k == K.ENUM:
            return self._enum()
        if k == K.CONST:
            return self._const()
        if k == K.TYPE:
            return self._type_alias()
        if k == K.MODULE:
            return self._module()
        if k in (K.SLOT, K.LOCK):
            return self._slot()
        if k == K.WRITE:
            return self._write()
        if k == K.YIELD:
            return self._yield()
        if k == K.JAM:
            loc = self._loc()
            self._adv()
            # Optional label: jam outer
            label = None
            if self._check(K.IDENT):
                label = self._adv().value
            self._match(K.SEMICOLON)
            return JamStmt(loc, label=label)
        if k == K.SKIP:
            loc = self._loc()
            self._adv()
            label = None
            if self._check(K.IDENT):
                label = self._adv().value
            self._match(K.SEMICOLON)
            return SkipStmt(loc, label=label)
        if k == K.WRECK:
            return self._wreck()
        if k == K.SCRAP:
            return self._scrap()
        if k == K.LOOP:
            return self._loop()
        if k == K.FOR:
            return self._foreach()
        if k == K.IF:
            return self._if()
        if k == K.MATCH:
            return self._match_stmt()
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

    def _recipe(self, decorators: List[Decorator] = None) -> RecipeDecl:
        if decorators is None:
            decorators = self._decorators()
        loc = self._loc()
        self._adv()
        name = self._expect(K.IDENT, "Expected recipe name").value
        self._expect(K.LPAREN)
        params = []
        while not self._check(K.RPAREN):
            # Variadic: ...args: crate[T]
            if self._check(K.DOTDOTDOT):
                self._adv()
                pname = self._expect(K.IDENT, "Expected variadic parameter name").value
                self._expect(K.COLON)
                ptype = self._type()
                params.append(Param(pname, ptype, self._loc(), variadic=True))
                break  # variadic must be last
            pname = self._expect(K.IDENT, "Expected parameter name").value
            self._expect(K.COLON)
            ptype = self._type()
            # Optional default value
            default = None
            if self._match(K.ASSIGN):
                default = self._expr()
            params.append(Param(pname, ptype, self._loc(), default=default))
            if not self._match(K.COMMA):
                break
        self._expect(K.RPAREN)
        # Return type — single or multi: -> (type, type, ...)
        ret = TypeNode("empty")
        return_types = None
        if self._match(K.ARROW):
            if self._check(K.LPAREN):
                # Multi-return: -> (unit, text, ...)
                self._adv()
                return_types = []
                while not self._check(K.RPAREN):
                    return_types.append(self._type())
                    if not self._match(K.COMMA):
                        break
                self._expect(K.RPAREN)
                ret = TypeNode("empty")  # overridden at codegen
            else:
                ret = self._type()
        body = self._block()
        return RecipeDecl(name, params, ret, body, loc, return_types=return_types, decorators=decorators)

    def _decorators(self) -> List[Decorator]:
        """Parse zero or more decorators: @inline @export"""
        decorators = []
        while self._match(K.AT):
            loc = self._loc()
            name = self._expect(K.IDENT, "Expected decorator name").value
            args = []
            if self._match(K.LPAREN):
                while not self._check(K.RPAREN):
                    args.append(self._expr())
                    if not self._match(K.COMMA):
                        break
                self._expect(K.RPAREN)
            from .ast_nodes import Decorator
            decorators.append(Decorator(name, args, loc))
        return decorators

    def _blueprint(self, decorators: List[Decorator] = None) -> BlueprintDecl:
        if decorators is None:
            decorators = self._decorators()
        loc = self._loc()
        self._adv()
        name = self._expect(K.IDENT, "Expected blueprint name").value
        self._expect(K.LBRACE)
        fields = []
        methods = []
        while not self._check(K.RBRACE):
            # Check if this is a method: fn method_name(params) -> return_type { ... }
            if self._check(K.FN):
                method_decorators = self._decorators()
                self._expect(K.FN)
                # Method name: blueprint_name.method_name or just method_name
                method_name = self._expect(K.IDENT, "Expected method name").value
                self._expect(K.LPAREN)
                params = []
                while not self._check(K.RPAREN):
                    pname = self._expect(K.IDENT, "Expected parameter name").value
                    self._expect(K.COLON)
                    ptype = self._type()
                    default = None
                    if self._match(K.ASSIGN):
                        default = self._expr()
                    params.append(Param(pname, ptype, self._loc(), default=default))
                    if not self._match(K.COMMA):
                        break
                self._expect(K.RPAREN)
                ret = TypeNode("unit")
                if self._match(K.ARROW):
                    ret = self._type()
                body = self._block()
                from .ast_nodes import MethodDecl
                methods.append(MethodDecl(name, method_name, params, ret, body, self._loc(), decorators=method_decorators))
            else:
                fname = self._expect(K.IDENT, "Expected field name").value
                self._expect(K.COLON)
                ftype = self._type()
                fields.append(Param(fname, ftype, self._loc()))
                self._match(K.COMMA)
                self._match(K.SEMICOLON)
        self._expect(K.RBRACE)
        return BlueprintDecl(name, fields, loc, decorators=decorators, methods=methods)

    def _enum(self) -> EnumDecl:
        loc = self._loc()
        self._adv()
        name = self._expect(K.IDENT, "Expected enum name").value
        self._expect(K.LBRACE)
        variants = []
        while not self._check(K.RBRACE):
            variant = self._expect(K.IDENT, "Expected variant name").value
            variants.append(variant)
            if not self._match(K.COMMA):
                break
        self._expect(K.RBRACE)
        from .ast_nodes import EnumDecl
        return EnumDecl(name, variants, loc)

    def _const(self) -> ConstDecl:
        loc = self._loc()
        self._adv()
        name = self._expect(K.IDENT, "Expected constant name").value
        self._expect(K.ASSIGN)
        value = self._expr()
        self._match(K.SEMICOLON)
        from .ast_nodes import ConstDecl
        return ConstDecl(name, value, loc)

    def _type_alias(self) -> TypeAliasDecl:
        loc = self._loc()
        self._adv()
        name = self._expect(K.IDENT, "Expected type alias name").value
        self._expect(K.ASSIGN)
        target_type = self._type()
        self._match(K.SEMICOLON)
        from .ast_nodes import TypeAliasDecl
        return TypeAliasDecl(name, target_type, loc)

    def _module(self) -> ModuleDecl:
        loc = self._loc()
        self._adv()
        name = self._expect(K.IDENT, "Expected module name").value
        self._expect(K.LBRACE)
        body = []
        while not self._check(K.RBRACE):
            body.append(self._stmt())
        self._expect(K.RBRACE)
        from .ast_nodes import ModuleDecl
        return ModuleDecl(name, body, loc)

    def _slot(self) -> SlotDecl:
        loc = self._loc()
        is_lock = bool(self._match(K.LOCK))
        self._expect(K.SLOT)
        name = self._expect(K.IDENT, "Expected variable name").value
        # Optional type annotation: slot name: type = value
        type_node = None
        if self._match(K.COLON):
            type_node = self._type()
        self._expect(K.ASSIGN)
        val = self._expr()
        self._match(K.SEMICOLON)
        return SlotDecl(name, val, is_lock, loc, type_node)

    def _write(self) -> WriteStmt:
        loc = self._loc()
        self._adv()
        # Support both   write expr   and   write(expr)
        paren = bool(self._match(K.LPAREN))
        val = self._expr()
        if paren:
            self._expect(K.RPAREN)
        self._match(K.SEMICOLON)
        return WriteStmt(val, loc)

    def _yield(self) -> YieldStmt:
        loc = self._loc()
        self._adv()
        val = self._expr()
        # Multi-return: yield a, b  — wrap in a CrateLit for codegen to unpack
        if self._check(K.COMMA):
            parts = [val]
            while self._match(K.COMMA):
                parts.append(self._expr())
            self._match(K.SEMICOLON)
            return YieldStmt(CrateLit(parts, loc), loc)
        self._match(K.SEMICOLON)
        return YieldStmt(val, loc)

    def _wreck(self) -> WreckStmt:
        loc = self._loc()
        self._adv()
        paren = bool(self._match(K.LPAREN))
        msg = self._expr()
        if paren:
            self._expect(K.RPAREN)
        self._match(K.SEMICOLON)
        return WreckStmt(msg, loc)

    def _scrap(self) -> ScrapStmt:
        loc = self._loc()
        self._adv()
        name = self._expect(K.IDENT, "Expected variable name after 'scrap'").value
        self._match(K.SEMICOLON)
        return ScrapStmt(name, loc)

    def _loop(self) -> LoopStmt:
        loc = self._loc()
        self._adv()
        # Optional label before condition: loop outer: condition { ... }
        label = None
        if self._check(K.IDENT) and self._peek().kind == K.COLON:
            label = self._adv().value
            self._adv()  # consume ':'
        cond = self._expr()
        body = self._block()
        return LoopStmt(cond, body, loc, label=label)

    def _foreach(self) -> ForEachStmt:
        loc = self._loc()
        self._adv()
        # Optional label: for outer: item in crate { ... }
        label = None
        if self._check(K.IDENT) and self._peek(1).kind == K.COLON:
            label = self._adv().value
            self._adv()  # consume ':'
        var = self._expect(K.IDENT, "Expected loop variable").value
        self._expect(K.IN)
        it = self._expr()
        # Check if this is a range expression (start..end)
        if isinstance(it, BinOp) and it.op == "..":
            # Convert range expression to RangeExpr
            from .ast_nodes import RangeExpr
            it = RangeExpr(it.left, it.right, it.loc)
        body = self._block()
        return ForEachStmt(var, it, body, loc, label=label)

    def _if(self) -> IfStmt:
        loc = self._loc()
        self._adv()
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

    def _match_stmt(self) -> MatchStmt:
        """match <expr> { case <expr> => { ... } ... default => { ... } }"""
        loc = self._loc()
        self._adv()
        value = self._expr()
        self._expect(K.LBRACE)
        arms = []
        default_block = None
        while not self._check(K.RBRACE) and not self._check(K.EOF):
            if self._check(K.DEFAULT):
                self._adv()
                self._expect(K.FAT_ARROW, "Expected '=>' after 'default'")
                default_block = self._block()
            elif self._check(K.CASE):
                self._adv()
                pat = self._pattern()
                self._expect(K.FAT_ARROW, "Expected '=>' after case pattern")
                body = self._block()
                arms.append((pat, body))
            else:
                self._err("Expected 'case' or 'default' in match block")
        self._expect(K.RBRACE)
        return MatchStmt(value, arms, default_block, loc)

    def _pattern(self) -> Node:
        """Parse a pattern: can be a destructuring pattern or a simple expression"""
        loc = self._loc()
        # Check if this is a tuple pattern: (a, b, ...)
        if self._check(K.LPAREN):
            self._adv()
            patterns = []
            while not self._check(K.RPAREN):
                patterns.append(self._pattern())
                if not self._match(K.COMMA):
                    break
            self._expect(K.RPAREN)
            if len(patterns) > 1:
                from .ast_nodes import TuplePattern
                return TuplePattern(patterns, loc)
            else:
                # Single pattern in parentheses is just the pattern itself
                return patterns[0] if patterns else T_EMPTY
        # Check if this is a destructuring pattern: TypeName(field, field2) or TypeName(field: value, field2: value)
        if self._check(K.IDENT) and self._peek() and self._peek().kind == K.LPAREN:
            type_name = self._adv().value
            self._expect(K.LPAREN)
            bindings = []
            while not self._check(K.RPAREN):
                field_name = self._expect(K.IDENT, "Expected field name").value
                # Check if there's a default value: field: value
                if self._match(K.COLON):
                    default_value = self._expr()
                    bindings.append((field_name, default_value))
                else:
                    bindings.append((field_name, None))
                if not self._match(K.COMMA):
                    break
            self._expect(K.RPAREN)
            from .ast_nodes import DestructPattern
            return DestructPattern(type_name, bindings, loc)
        # Otherwise, parse as a regular expression
        return self._expr()

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
            K.UNIT: "unit",
            K.I8: "i8",
            K.I16: "i16",
            K.I32: "i32",
            K.U8: "u8",
            K.U16: "u16",
            K.U32: "u32",
            K.U64: "u64",
            K.DECIMAL_T: "decimal",
            K.TEXT_T: "text",
            K.SWITCH: "switch",
            K.CRATE: "crate",
            K.EMPTY: "empty",
        }
        tok = self._cur()
        # Check for tuple type: (type1, type2, ...)
        if tok.kind == K.LPAREN:
            self._adv()
            types = []
            while not self._check(K.RPAREN):
                types.append(self._type())
                if not self._match(K.COMMA):
                    break
            self._expect(K.RPAREN)
            if len(types) > 1:
                from .ast_nodes import TupleType
                return TupleType(types, self._loc())
            else:
                # Single type in parentheses is just the type itself
                return types[0] if types else T_EMPTY
        if tok.kind == K.WIRE:
            self._adv()
            self._expect(K.LT)
            inner = self._type()
            self._expect(K.GT)
            return TypeNode("wire", inner)
        if tok.kind == K.MAP:
            self._adv()
            self._expect(K.LT)
            key_type = self._type()
            self._expect(K.COMMA)
            value_type = self._type()
            self._expect(K.GT)
            from .ast_nodes import MapType
            return MapType(key_type, value_type, self._loc())
        if tok.kind == K.SET:
            self._adv()
            self._expect(K.LT)
            element_type = self._type()
            self._expect(K.GT)
            from .ast_nodes import SetType
            return SetType(element_type, self._loc())
        if tok.kind in TYPE_MAP:
            self._adv()
            name = TYPE_MAP[tok.kind]
            if name == "crate" and self._match(K.LBRACKET):
                inner = self._type()
                self._expect(K.RBRACKET)
                return TypeNode("crate", inner)
            # Check for array type: type[]
            if self._match(K.LBRACKET):
                self._expect(K.RBRACKET)
                from .ast_nodes import ArrayType
                return ArrayType(TypeNode(name), self._loc())
            # Check for union type: type | type
            if self._match(K.OR):
                types = [TypeNode(name)]
                while True:
                    next_type = self._type()
                    types.append(next_type)
                    if not self._match(K.OR):
                        break
                from .ast_nodes import UnionType
                return UnionType(types, self._loc())
            # Check for intersection type: type & type
            if self._match(K.AND):
                types = [TypeNode(name)]
                while True:
                    next_type = self._type()
                    types.append(next_type)
                    if not self._match(K.AND):
                        break
                from .ast_nodes import IntersectionType
                return IntersectionType(types, self._loc())
            # Check for nullable type: type?
            if self._match(K.QUESTION):
                from .ast_nodes import NullableType
                return NullableType(TypeNode(name), self._loc())
            return TypeNode(name)
        if tok.kind == K.IDENT:
            ident_value = tok.value
            self._adv()
            # Check for array type: type[]
            if self._match(K.LBRACKET):
                self._expect(K.RBRACKET)
                from .ast_nodes import ArrayType
                return ArrayType(TypeNode(ident_value), self._loc())
            # Check for union type: type | type
            if self._match(K.OR):
                types = [TypeNode(ident_value)]
                while True:
                    next_type = self._type()
                    types.append(next_type)
                    if not self._match(K.OR):
                        break
                from .ast_nodes import UnionType
                return UnionType(types, self._loc())
            # Check for intersection type: type & type
            if self._match(K.AND):
                types = [TypeNode(ident_value)]
                while True:
                    next_type = self._type()
                    types.append(next_type)
                    if not self._match(K.AND):
                        break
                from .ast_nodes import IntersectionType
                return IntersectionType(types, self._loc())
            # Check for nullable type: type?
            if self._match(K.QUESTION):
                from .ast_nodes import NullableType
                return NullableType(TypeNode(ident_value), self._loc())
            return TypeNode(ident_value)
        self._err("Expected a type name")

    # ------------------------------------------------------------------
    # Expressions — precedence climbing
    # ------------------------------------------------------------------

    def _expr(self) -> Node:
        return self._null_coalesce()

    def _null_coalesce(self) -> Node:
        expr = self._or()
        if self._match(K.QUESTIONQUESTION):
            right = self._or()
            from .ast_nodes import NullCoalesceExpr
            expr = NullCoalesceExpr(expr, right, self._loc())
        return expr

    def _or(self) -> Node:
        left = self._and()
        while self._check(K.OR):
            loc = self._loc()
            op = self._adv().value
            left = BinOp(left, op, self._and(), loc)
        return left

    def _and(self) -> Node:
        left = self._eq()
        while self._check(K.AND):
            loc = self._loc()
            op = self._adv().value
            left = BinOp(left, op, self._eq(), loc)
        return left

    def _eq(self) -> Node:
        left = self._cmp()
        while self._check(K.EQ, K.NEQ):
            loc = self._loc()
            op = self._adv().value
            left = BinOp(left, op, self._cmp(), loc)
        return left

    def _cmp(self) -> Node:
        left = self._add()
        while self._check(K.LT, K.GT, K.LTE, K.GTE):
            loc = self._loc()
            op = self._adv().value
            left = BinOp(left, op, self._add(), loc)
        return left

    def _add(self) -> Node:
        left = self._mul()
        while self._check(K.PLUS, K.MINUS):
            loc = self._loc()
            op = self._adv().value
            left = BinOp(left, op, self._mul(), loc)
        # Check for .. (range) operator
        while self._check(K.DOTDOT):
            loc = self._loc()
            self._adv()  # consume ..
            right = self._mul()
            left = BinOp(left, "..", right, loc)
        return left

    def _mul(self) -> Node:
        left = self._unary()
        while self._check(K.STAR, K.SLASH, K.PERCENT):
            loc = self._loc()
            op = self._adv().value
            left = BinOp(left, op, self._unary(), loc)
        return left

    def _unary(self) -> Node:
        loc = self._loc()
        if self._check(K.MINUS):
            self._adv()
            return UnaryOp("-", self._unary(), loc)
        if self._check(K.FLIP) or self._check(K.NOT):
            self._adv()
            return UnaryOp("flip", self._unary(), loc)
        return self._postfix()

    def _postfix(self) -> Node:
        expr = self._primary()
        while True:
            if self._check(K.DOT):
                loc = self._loc()
                self._adv()
                # Accept any token as field/method name after dot
                tok = self._cur()
                if tok.kind == K.EOF:
                    self._err("Expected field or method name after '.'")
                field = str(tok.value)
                self._adv()
                if self._check(K.LPAREN):
                    self._adv()
                    args = self._arglist()
                    self._expect(K.RPAREN)
                    expr = CallExpr(FieldExpr(expr, field, loc), args, loc)
                else:
                    expr = FieldExpr(expr, field, loc)
            elif self._check(K.DOTQUESTION):
                # Optional chaining: obj?.field
                loc = self._loc()
                self._adv()
                tok = self._cur()
                if tok.kind == K.EOF:
                    self._err("Expected field or method name after '?.")
                field = str(tok.value)
                self._adv()
                from .ast_nodes import OptionalChainExpr
                expr = OptionalChainExpr(expr, field, loc)
            elif self._check(K.LBRACKET):
                loc = self._loc()
                self._adv()
                idx = self._expr()
                self._expect(K.RBRACKET)
                expr = IndexExpr(expr, idx, loc)
            else:
                break
        return expr

    def _primary(self) -> Node:
        loc = self._loc()
        tok = self._cur()

        if tok.kind == K.DOTDOTDOT:
            self._adv()
            value = self._primary()
            from .ast_nodes import SpreadExpr
            return SpreadExpr(value, loc)

        if tok.kind == K.FN:
            self._adv()
            self._expect(K.LPAREN)
            params = []
            while not self._check(K.RPAREN):
                pname = self._expect(K.IDENT, "Expected parameter name").value
                self._expect(K.COLON)
                ptype = self._type()
                default = None
                if self._match(K.ASSIGN):
                    default = self._expr()
                params.append(Param(pname, ptype, self._loc(), default=default))
                if not self._match(K.COMMA):
                    break
            self._expect(K.RPAREN)
            body = self._block()
            from .ast_nodes import LambdaExpr
            return LambdaExpr(params, body, loc)

        if tok.kind == K.INT:
            self._adv()
            return IntLit(tok.value, loc)
        if tok.kind == K.DECIMAL:
            self._adv()
            return DecimalLit(tok.value, loc)
        if tok.kind == K.TEXT:
            self._adv()
            return TextLit(tok.value, loc)
        if tok.kind == K.TRUE:
            self._adv()
            return SwitchLit(True, loc)
        if tok.kind == K.FALSE:
            self._adv()
            return SwitchLit(False, loc)
        if tok.kind == K.EMPTY:
            self._adv()
            return EmptyLit(loc)

        # Interpolated string — the lexer already tokenised the parts;
        # we just need to gather them into an InterpTextLit
        if tok.kind == K.ITEXT_START:
            return self._interp_text(loc)

        if tok.kind == K.LBRACKET:
            self._adv()
            elems = []
            while not self._check(K.RBRACKET):
                elems.append(self._expr())
                if not self._match(K.COMMA):
                    break
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
                if not self._match(K.COMMA):
                    break
            self._expect(K.RPAREN)
            return BuildExpr(name, kwargs, loc)

        if tok.kind == K.LBRACE:
            # Record literal: {x: 10, y: 20}
            self._adv()
            fields = {}
            while not self._check(K.RBRACE):
                field_name = self._expect(K.IDENT, "Expected field name").value
                self._expect(K.COLON)
                field_value = self._expr()
                fields[field_name] = field_value
                if not self._match(K.COMMA):
                    break
            self._expect(K.RBRACE)
            from .ast_nodes import RecordLit
            return RecordLit(fields, loc)

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

    def _interp_text(self, loc: Loc) -> InterpTextLit:
        """Parse ITEXT_START (ITEXT_CHUNK | ITEXT_EXPR_START <expr> ITEXT_EXPR_END)* ITEXT_END"""
        self._adv()  # consume ITEXT_START
        parts = []
        while not self._check(K.ITEXT_END) and not self._check(K.EOF):
            if self._check(K.ITEXT_CHUNK):
                parts.append(self._adv().value)  # plain text string
            elif self._check(K.ITEXT_EXPR_START):
                self._adv()  # consume {
                expr = self._expr()
                parts.append(expr)
                self._expect(K.ITEXT_EXPR_END)
            else:
                self._err("Unexpected token inside interpolated string")
        self._expect(K.ITEXT_END)
        return InterpTextLit(parts, loc)

    def _arglist(self) -> List[Node]:
        args = []
        while not self._check(K.RPAREN) and not self._check(K.EOF):
            # Check if this is a named argument: name: value
            if self._check(K.IDENT) and self._peek() and self._peek().kind == K.COLON:
                name = self._adv().value
                self._expect(K.COLON)
                value = self._expr()
                from .ast_nodes import NamedArg
                args.append(NamedArg(name, value, self._loc()))
            else:
                args.append(self._expr())
            if not self._match(K.COMMA):
                break
        return args
