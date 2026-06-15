"""
Rubble Parser
Converts a flat token stream into a structured AST.
Uses a recursive-descent strategy.
"""

from typing import List, Optional
from .lexer import Token, TT
from .ast_nodes import *


class ParseError(Exception):
    def __init__(self, message, token: Token):
        super().__init__(f"[Parse Error] Line {token.line}, Col {token.col}: {message} (got {token.type} '{token.value}')")
        self.token = token


class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def current(self) -> Token:
        return self.tokens[self.pos]

    def peek(self, offset=1) -> Token:
        idx = self.pos + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return self.tokens[-1]  # EOF

    def advance(self) -> Token:
        tok = self.tokens[self.pos]
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        return tok

    def check(self, *types) -> bool:
        return self.current().type in types

    def match(self, *types) -> Optional[Token]:
        if self.current().type in types:
            return self.advance()
        return None

    def expect(self, tt: str, msg: str = None) -> Token:
        if self.current().type == tt:
            return self.advance()
        raise ParseError(msg or f"Expected {tt}", self.current())

    def error(self, msg: str):
        raise ParseError(msg, self.current())

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def parse(self) -> Program:
        stmts = []
        while not self.check(TT["EOF"]):
            stmts.append(self.parse_statement())
        return Program(stmts)

    # ------------------------------------------------------------------
    # Statements
    # ------------------------------------------------------------------

    def parse_statement(self) -> Node:
        tok = self.current()

        if tok.type == TT["GATHER"]:
            return self.parse_gather()
        if tok.type == TT["RECIPE"]:
            return self.parse_recipe()
        if tok.type == TT["BLUEPRINT"]:
            return self.parse_blueprint()
        if tok.type in (TT["SLOT"], TT["LOCK"]):
            return self.parse_slot()
        if tok.type == TT["WRITE"]:
            return self.parse_write()
        if tok.type == TT["YIELD"]:
            return self.parse_yield()
        if tok.type == TT["JAM"]:
            self.advance()
            self.match(TT["SEMICOLON"])
            return JamStmt()
        if tok.type == TT["WRECK"]:
            return self.parse_wreck()
        if tok.type == TT["SCRAP"]:
            return self.parse_scrap()
        if tok.type == TT["LOOP"]:
            return self.parse_loop()
        if tok.type == TT["FOR"]:
            return self.parse_foreach()
        if tok.type == TT["IF"]:
            return self.parse_if()

        # Assignment or expression statement
        return self.parse_assign_or_expr()

    def parse_gather(self) -> GatherStmt:
        self.expect(TT["GATHER"])
        tok = self.current()
        if tok.type == TT["TEXT"]:
            path = self.advance().value
        elif tok.type == TT["IDENT"]:
            path = self.advance().value
        else:
            self.error("Expected module name or path after 'gather'")
        self.match(TT["SEMICOLON"])
        return GatherStmt(path)

    def parse_recipe(self) -> RecipeDecl:
        self.expect(TT["RECIPE"])
        name = self.expect(TT["IDENT"], "Expected recipe name").value
        self.expect(TT["LPAREN"])
        params = []
        while not self.check(TT["RPAREN"]):
            pname = self.expect(TT["IDENT"], "Expected parameter name").value
            self.expect(TT["COLON"])
            ptype = self.parse_type_name()
            params.append(Param(pname, ptype))
            if not self.match(TT["COMMA"]):
                break
        self.expect(TT["RPAREN"])
        self.expect(TT["ARROW"], "Expected '->' before return type")
        ret_type = self.parse_type_name()
        body = self.parse_block()
        return RecipeDecl(name, params, ret_type, body)

    def parse_blueprint(self) -> BlueprintDecl:
        self.expect(TT["BLUEPRINT"])
        name = self.expect(TT["IDENT"], "Expected blueprint name").value
        self.expect(TT["LBRACE"])
        fields = []
        while not self.check(TT["RBRACE"]):
            fname = self.expect(TT["IDENT"], "Expected field name").value
            self.expect(TT["COLON"])
            ftype = self.parse_type_name()
            fields.append(Param(fname, ftype))
            self.match(TT["COMMA"])
        self.expect(TT["RBRACE"])
        return BlueprintDecl(name, fields)

    def parse_slot(self) -> SlotDecl:
        is_lock = False
        if self.match(TT["LOCK"]):
            is_lock = True
        self.expect(TT["SLOT"])
        name = self.expect(TT["IDENT"], "Expected variable name after 'slot'").value
        self.expect(TT["ASSIGN"])
        value = self.parse_expr()
        self.match(TT["SEMICOLON"])
        return SlotDecl(name, value, is_lock)

    def parse_write(self) -> WriteStmt:
        self.expect(TT["WRITE"])
        value = self.parse_expr()
        self.match(TT["SEMICOLON"])
        return WriteStmt(value)

    def parse_yield(self) -> YieldStmt:
        self.expect(TT["YIELD"])
        value = self.parse_expr()
        self.match(TT["SEMICOLON"])
        return YieldStmt(value)

    def parse_wreck(self) -> WreckStmt:
        self.expect(TT["WRECK"])
        msg = self.parse_expr()
        self.match(TT["SEMICOLON"])
        return WreckStmt(msg)

    def parse_scrap(self) -> ScrapStmt:
        self.expect(TT["SCRAP"])
        name = self.expect(TT["IDENT"], "Expected variable name after 'scrap'").value
        self.match(TT["SEMICOLON"])
        return ScrapStmt(name)

    def parse_loop(self) -> LoopStmt:
        self.expect(TT["LOOP"])
        condition = self.parse_expr()
        body = self.parse_block()
        return LoopStmt(condition, body)

    def parse_foreach(self) -> ForEachStmt:
        self.expect(TT["FOR"])
        var = self.expect(TT["IDENT"], "Expected loop variable").value
        self.expect(TT["IN"])
        iterable = self.parse_expr()
        body = self.parse_block()
        return ForEachStmt(var, iterable, body)

    def parse_if(self) -> IfStmt:
        self.expect(TT["IF"])
        condition = self.parse_expr()
        then_block = self.parse_block()
        elif_clauses = []
        else_block = None
        while self.check(TT["ELIF"]):
            self.advance()
            elif_cond = self.parse_expr()
            elif_body = self.parse_block()
            elif_clauses.append((elif_cond, elif_body))
        if self.match(TT["ELSE"]):
            else_block = self.parse_block()
        return IfStmt(condition, then_block, elif_clauses, else_block)

    def parse_assign_or_expr(self) -> Node:
        """Handles assignment (name = expr) or bare expression statements."""
        expr = self.parse_expr()
        if self.match(TT["ASSIGN"]):
            rhs = self.parse_expr()
            self.match(TT["SEMICOLON"])
            return Assignment(expr, rhs)
        self.match(TT["SEMICOLON"])
        return ExprStmt(expr)

    # ------------------------------------------------------------------
    # Block
    # ------------------------------------------------------------------

    def parse_block(self) -> List[Node]:
        self.expect(TT["LBRACE"])
        stmts = []
        while not self.check(TT["RBRACE"]) and not self.check(TT["EOF"]):
            stmts.append(self.parse_statement())
        self.expect(TT["RBRACE"])
        return stmts

    # ------------------------------------------------------------------
    # Type names
    # ------------------------------------------------------------------

    def parse_type_name(self) -> str:
        """Returns a string representation of the type."""
        type_tokens = {
            TT["UNIT"]: "unit",
            TT["DECIMAL_T"]: "decimal",
            TT["TEXT_T"]: "text",
            TT["SWITCH"]: "switch",
            TT["CRATE"]: "crate",
            TT["EMPTY"]: "empty",
            TT["IDENT"]: None,   # custom blueprint name
        }
        tok = self.current()
        if tok.type in type_tokens:
            self.advance()
            name = type_tokens[tok.type] or tok.value
            # crate[InnerType]
            if name == "crate" and self.match(TT["LBRACKET"]):
                inner = self.parse_type_name()
                self.expect(TT["RBRACKET"])
                name = f"crate[{inner}]"
            # wire<Type>
            if self.current().type == TT["LT"]:
                self.advance()
                inner = self.parse_type_name()
                self.expect(TT["GT"])
                name = f"wire<{inner}>"
            return name
        # Allow wire keyword as a type annotation
        if tok.type == TT["WIRE"]:
            self.advance()
            self.expect(TT["LT"])
            inner = self.parse_type_name()
            self.expect(TT["GT"])
            return f"wire<{inner}>"
        self.error(f"Expected a type name")

    # ------------------------------------------------------------------
    # Expressions (Pratt / precedence climbing)
    # ------------------------------------------------------------------

    def parse_expr(self) -> Node:
        return self.parse_or()

    def parse_or(self) -> Node:
        left = self.parse_and()
        while self.check(TT["OR"]):
            op = self.advance().value
            right = self.parse_and()
            left = BinaryOp(left, op, right)
        return left

    def parse_and(self) -> Node:
        left = self.parse_equality()
        while self.check(TT["AND"]):
            op = self.advance().value
            right = self.parse_equality()
            left = BinaryOp(left, op, right)
        return left

    def parse_equality(self) -> Node:
        left = self.parse_comparison()
        while self.check(TT["EQ"], TT["NEQ"]):
            op = self.advance().value
            right = self.parse_comparison()
            left = BinaryOp(left, op, right)
        return left

    def parse_comparison(self) -> Node:
        left = self.parse_addition()
        while self.check(TT["LT"], TT["GT"], TT["LTE"], TT["GTE"]):
            op = self.advance().value
            right = self.parse_addition()
            left = BinaryOp(left, op, right)
        return left

    def parse_addition(self) -> Node:
        left = self.parse_multiplication()
        while self.check(TT["PLUS"], TT["MINUS"]):
            op = self.advance().value
            right = self.parse_multiplication()
            left = BinaryOp(left, op, right)
        return left

    def parse_multiplication(self) -> Node:
        left = self.parse_unary()
        while self.check(TT["STAR"], TT["SLASH"], TT["PERCENT"]):
            op = self.advance().value
            right = self.parse_unary()
            left = BinaryOp(left, op, right)
        return left

    def parse_unary(self) -> Node:
        if self.check(TT["MINUS"]):
            op = self.advance().value
            return UnaryOp(op, self.parse_unary())
        if self.check(TT["FLIP"]) or self.check(TT["NOT"]):
            self.advance()
            return UnaryOp("flip", self.parse_unary())
        return self.parse_postfix()

    def parse_postfix(self) -> Node:
        """Handle . field access, method calls, and [] index access."""
        expr = self.parse_primary()
        while True:
            if self.check(TT["DOT"]):
                self.advance()
                field = self.expect(TT["IDENT"], "Expected field or method name").value
                if self.check(TT["LPAREN"]):
                    self.advance()
                    args = self.parse_arg_list()
                    self.expect(TT["RPAREN"])
                    expr = MethodCall(expr, field, args)
                else:
                    expr = FieldAccess(expr, field)
            elif self.check(TT["LBRACKET"]):
                self.advance()
                index = self.parse_expr()
                self.expect(TT["RBRACKET"])
                expr = IndexAccess(expr, index)
            else:
                break
        return expr

    def parse_primary(self) -> Node:
        tok = self.current()

        # Literals
        if tok.type == TT["INT"]:
            self.advance()
            return IntLiteral(tok.value)
        if tok.type == TT["DECIMAL"]:
            self.advance()
            return DecimalLiteral(tok.value)
        if tok.type == TT["TEXT"]:
            self.advance()
            return TextLiteral(tok.value)
        if tok.type == TT["TRUE"]:
            self.advance()
            return SwitchLiteral(True)
        if tok.type == TT["FALSE"]:
            self.advance()
            return SwitchLiteral(False)
        if tok.type == TT["EMPTY"]:
            self.advance()
            return EmptyLiteral()

        # Crate (array) literal: [expr, ...]
        if tok.type == TT["LBRACKET"]:
            self.advance()
            elements = []
            while not self.check(TT["RBRACKET"]):
                elements.append(self.parse_expr())
                if not self.match(TT["COMMA"]):
                    break
            self.expect(TT["RBRACKET"])
            return CrateLiteral(elements)

        # Grouped expression
        if tok.type == TT["LPAREN"]:
            self.advance()
            expr = self.parse_expr()
            self.expect(TT["RPAREN"])
            return expr

        # smelt(value, Type)
        if tok.type == TT["SMELT"]:
            self.advance()
            self.expect(TT["LPAREN"])
            value = self.parse_expr()
            self.expect(TT["COMMA"])
            target_type = self.parse_type_name()
            self.expect(TT["RPAREN"])
            return SmeltExpr(value, target_type)

        # build BlueprintName(field: val, ...)
        if tok.type == TT["BUILD"]:
            self.advance()
            name = self.expect(TT["IDENT"], "Expected blueprint name after 'build'").value
            self.expect(TT["LPAREN"])
            kwargs = []
            while not self.check(TT["RPAREN"]):
                fname = self.expect(TT["IDENT"], "Expected field name").value
                self.expect(TT["COLON"])
                fval = self.parse_expr()
                kwargs.append((fname, fval))
                if not self.match(TT["COMMA"]):
                    break
            self.expect(TT["RPAREN"])
            return BuildExpr(name, kwargs)

        # wire varname
        if tok.type == TT["WIRE"]:
            self.advance()
            target = self.expect(TT["IDENT"], "Expected variable name after 'wire'").value
            return WireExpr(target)

        # unwrap expr
        if tok.type == TT["UNWRAP"]:
            self.advance()
            target = self.parse_primary()
            return UnwrapExpr(target)

        # Identifier or function call
        if tok.type == TT["IDENT"]:
            self.advance()
            if self.check(TT["LPAREN"]):
                self.advance()
                args = self.parse_arg_list()
                self.expect(TT["RPAREN"])
                return FunctionCall(tok.value, args)
            return Identifier(tok.value)

        self.error(f"Unexpected token in expression")

    def parse_arg_list(self) -> List[Node]:
        args = []
        while not self.check(TT["RPAREN"]) and not self.check(TT["EOF"]):
            args.append(self.parse_expr())
            if not self.match(TT["COMMA"]):
                break
        return args
