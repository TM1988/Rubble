"""
Rubble Compiler — Type Checker & Inferencer
Walks the AST, infers types for slot declarations, enforces type rules,
and annotates every expression node with a `.rtype` attribute (a TypeNode).
"""

from typing import Dict, List, Optional, Tuple
from .ast_nodes import *


# ---------------------------------------------------------------------------
# Rubble type constants
# ---------------------------------------------------------------------------

T_UNIT    = TypeNode("unit")
T_DECIMAL = TypeNode("decimal")
T_TEXT    = TypeNode("text")
T_SWITCH  = TypeNode("switch")
T_EMPTY   = TypeNode("empty")

def t_crate(inner: TypeNode) -> TypeNode:
    return TypeNode("crate", inner)

def t_wire(inner: TypeNode) -> TypeNode:
    return TypeNode("wire", inner)


def types_equal(a: TypeNode, b: TypeNode) -> bool:
    if a.name != b.name:
        return False
    if a.inner is None and b.inner is None:
        return True
    if a.inner is None or b.inner is None:
        return False
    return types_equal(a.inner, b.inner)


# ---------------------------------------------------------------------------
# Symbol table / scope
# ---------------------------------------------------------------------------

class Scope:
    def __init__(self, parent: Optional['Scope'] = None):
        self._syms: Dict[str, Tuple[TypeNode, bool]] = {}
        self.parent = parent

    def define(self, name: str, typ: TypeNode, locked: bool = False):
        self._syms[name] = (typ, locked)

    def lookup(self, name: str) -> Optional[Tuple[TypeNode, bool]]:
        if name in self._syms:
            return self._syms[name]
        if self.parent:
            return self.parent.lookup(name)
        return None

    def is_locked(self, name: str) -> bool:
        r = self.lookup(name)
        return r[1] if r else False


# ---------------------------------------------------------------------------
# Type error
# ---------------------------------------------------------------------------

class TypeError_(Exception):
    def __init__(self, msg: str, loc: Loc):
        super().__init__(f"[Type Error] {loc.line}:{loc.col}: {msg}")
        self.loc = loc


# ---------------------------------------------------------------------------
# All stdlib method return types — shared between checker and codegen
# ---------------------------------------------------------------------------

STDLIB_METHODS: Dict[Tuple[str, str], TypeNode] = {
    # panel
    ("panel",    "prompt"):          T_TEXT,
    ("panel",    "grab"):            T_TEXT,
    # cabinet
    ("cabinet",  "list"):            t_crate(T_TEXT),
    ("cabinet",  "open"):            T_UNIT,
    ("cabinet",  "create"):          T_UNIT,
    ("cabinet",  "read"):            T_TEXT,
    ("cabinet",  "write"):           T_EMPTY,
    ("cabinet",  "exists"):          T_SWITCH,
    ("cabinet",  "delete"):          T_EMPTY,
    # machinery
    ("machinery","rest"):            T_EMPTY,
    ("machinery","ram"):             T_UNIT,
    ("machinery","halt"):            T_EMPTY,
    ("machinery","time"):            T_UNIT,
    ("machinery","args"):            t_crate(T_TEXT),
    ("machinery","env"):             T_TEXT,
    ("machinery","exit"):            T_EMPTY,
    # cable
    ("cable",    "connect"):         T_UNIT,
    ("cable",    "status"):          T_SWITCH,
    # canvas
    ("canvas",   "open"):            T_UNIT,
    ("canvas",   "clear"):           T_EMPTY,
    ("canvas",   "rect"):            T_EMPTY,
    ("canvas",   "circle"):          T_EMPTY,
    ("canvas",   "line"):            T_EMPTY,
    ("canvas",   "text"):            T_EMPTY,
    ("canvas",   "show"):            T_EMPTY,
    ("canvas",   "poll"):            T_UNIT,
    ("canvas",   "close"):           T_EMPTY,
    ("canvas",   "key"):             T_UNIT,
    ("canvas",   "key_just_pressed"):T_SWITCH,
    ("canvas",   "mouse_x"):         T_UNIT,
    ("canvas",   "mouse_y"):         T_UNIT,
    ("canvas",   "mouse_btn"):       T_UNIT,
    ("canvas",   "mouse_scroll"):    T_UNIT,
    ("canvas",   "fill_mode"):       T_EMPTY,
    ("canvas",   "set_title"):       T_EMPTY,
    ("canvas",   "resize"):          T_EMPTY,
    ("canvas",   "fullscreen"):      T_EMPTY,
    ("canvas",   "delta_time"):      T_DECIMAL,
    ("canvas",   "image_load"):      T_UNIT,
    ("canvas",   "image_draw"):      T_EMPTY,
    ("canvas",   "font_size"):       T_EMPTY,
    # math
    ("math", "sqrt"):   T_DECIMAL, ("math", "cbrt"):  T_DECIMAL,
    ("math", "pow"):    T_DECIMAL, ("math", "abs"):   T_DECIMAL,
    ("math", "floor"):  T_DECIMAL, ("math", "ceil"):  T_DECIMAL,
    ("math", "round"):  T_DECIMAL, ("math", "sin"):   T_DECIMAL,
    ("math", "cos"):    T_DECIMAL, ("math", "tan"):   T_DECIMAL,
    ("math", "asin"):   T_DECIMAL, ("math", "acos"):  T_DECIMAL,
    ("math", "atan"):   T_DECIMAL, ("math", "atan2"): T_DECIMAL,
    ("math", "log"):    T_DECIMAL, ("math", "log2"):  T_DECIMAL,
    ("math", "log10"):  T_DECIMAL, ("math", "exp"):   T_DECIMAL,
    ("math", "min"):    T_DECIMAL, ("math", "max"):   T_DECIMAL,
    ("math", "pi"):     T_DECIMAL, ("math", "e"):     T_DECIMAL,
    ("math", "inf"):    T_DECIMAL, ("math", "clamp"): T_DECIMAL,
    ("math", "lerp"):   T_DECIMAL,
    # rand
    ("rand", "int"):      T_UNIT,
    ("rand", "decimal"):  T_DECIMAL,
    ("rand", "seed"):     T_EMPTY,
    # time
    ("time", "now"):      T_UNIT,
    ("time", "format"):   T_TEXT,
    ("time", "sleep"):    T_EMPTY,
    # json
    ("json", "encode"):   T_TEXT,
    ("json", "decode"):   T_TEXT,
    ("json", "get"):      T_TEXT,
    ("json", "set"):      T_TEXT,
    # sound
    ("sound", "load"):    T_UNIT,
    ("sound", "play"):    T_EMPTY,
    ("sound", "stop"):    T_EMPTY,
    # thread
    ("thread", "spawn"):  T_UNIT,
    ("thread", "join"):   T_EMPTY,
}


# ---------------------------------------------------------------------------
# Type checker
# ---------------------------------------------------------------------------

class TypeChecker:
    def __init__(self):
        self.globals = Scope()
        self._blueprints: Dict[str, BlueprintDecl] = {}
        self._recipes: Dict[str, RecipeDecl] = {}
        self._current_return_type: Optional[TypeNode] = None
        self._gathered: set = set()
        self._seed_stdlib()

    def _seed_stdlib(self):
        for name in ("panel", "cabinet", "machinery", "cable", "canvas", "math",
                     "rand", "time", "json", "sound", "thread"):
            self.globals.define(name, TypeNode(name))
        self.globals.define("panel_prompt",   T_TEXT)
        self.globals.define("panel_grab",     T_TEXT)
        self.globals.define("cabinet_list",   t_crate(T_TEXT))
        self.globals.define("cabinet_open",   T_UNIT)
        self.globals.define("cabinet_create", T_UNIT)
        self.globals.define("machinery_rest", T_EMPTY)
        self.globals.define("machinery_ram",  T_UNIT)
        self.globals.define("machinery_halt", T_EMPTY)
        self.globals.define("cable_connect",  T_UNIT)
        self.globals.define("line_read",      T_TEXT)

    def check(self, program: Program):
        self._scan_top_level(program.stmts)
        for stmt in program.stmts:
            self._check_stmt(stmt, self.globals)

    # ------------------------------------------------------------------
    # Pre-scan: register recipe and blueprint names for forward refs
    # ------------------------------------------------------------------

    def _scan_top_level(self, stmts: List[Node]):
        for stmt in stmts:
            if isinstance(stmt, RecipeDecl):
                self._recipes[stmt.name] = stmt
                self.globals.define(stmt.name, T_EMPTY)
            elif isinstance(stmt, BlueprintDecl):
                self._blueprints[stmt.name] = stmt

    # ------------------------------------------------------------------
    # Statement checking
    # ------------------------------------------------------------------

    def _check_stmt(self, node: Node, scope: Scope):
        if isinstance(node, GatherStmt):
            self._gathered.add(node.module)
            obj_map = {
                "panel": "panel", "cabinet": "cabinet", "machinery": "machinery",
                "cable": "cable", "rand": "rand", "time": "time",
                "json": "json", "sound": "sound", "thread": "thread",
            }
            if node.module in obj_map:
                scope.define(node.module, TypeNode(obj_map[node.module]))

        elif isinstance(node, BlueprintDecl):
            self._blueprints[node.name] = node

        elif isinstance(node, RecipeDecl):
            self._check_recipe(node)

        elif isinstance(node, SlotDecl):
            typ = self._infer(node.value, scope)
            node.inferred_type = typ
            scope.define(node.name, typ, locked=node.is_lock)

        elif isinstance(node, AssignStmt):
            rhs_type = self._infer(node.value, scope)
            if isinstance(node.target, Ident):
                entry = scope.lookup(node.target.name)
                if entry is None:
                    raise TypeError_(f"Undefined variable '{node.target.name}'", node.loc)
                lhs_type, locked = entry
                if locked:
                    raise TypeError_(f"Cannot reassign locked slot '{node.target.name}'", node.loc)
                if not types_equal(lhs_type, rhs_type):
                    raise TypeError_(
                        f"Type mismatch: '{node.target.name}' is {lhs_type} but assigned {rhs_type}",
                        node.loc)
            elif isinstance(node.target, FieldExpr):
                obj_type = self._infer(node.target.target, scope)
                self._check_field_type(obj_type, node.target.field, rhs_type, node.loc)
            elif isinstance(node.target, UnwrapExpr):
                ptr_type = self._infer(node.target.target, scope)
                if ptr_type.name != "wire":
                    raise TypeError_(f"Cannot unwrap non-wire type {ptr_type}", node.loc)
                if not types_equal(ptr_type.inner, rhs_type):
                    raise TypeError_(
                        f"Wire points to {ptr_type.inner} but assigned {rhs_type}", node.loc)

        elif isinstance(node, WriteStmt):
            self._infer(node.value, scope)

        elif isinstance(node, YieldStmt):
            if self._current_return_type is None:
                raise TypeError_("'yield' outside of a recipe", node.loc)
            actual = self._infer(node.value, scope)
            if not types_equal(actual, self._current_return_type):
                raise TypeError_(
                    f"Recipe return type is {self._current_return_type} but yielding {actual}",
                    node.loc)

        elif isinstance(node, WreckStmt):
            self._infer(node.message, scope)

        elif isinstance(node, ScrapStmt):
            if scope.lookup(node.name) is None:
                raise TypeError_(f"scrap: undefined variable '{node.name}'", node.loc)

        elif isinstance(node, IfStmt):
            cond_t = self._infer(node.condition, scope)
            if not types_equal(cond_t, T_SWITCH):
                raise TypeError_(f"if condition must be switch, got {cond_t}", node.loc)
            self._check_block(node.then_block, scope)
            for ec, eb in node.elif_clauses:
                et = self._infer(ec, scope)
                if not types_equal(et, T_SWITCH):
                    raise TypeError_(f"elif condition must be switch, got {et}", node.loc)
                self._check_block(eb, scope)
            if node.else_block:
                self._check_block(node.else_block, scope)

        elif isinstance(node, MatchStmt):
            self._infer(node.value, scope)
            for pat, body in node.arms:
                self._infer(pat, scope)
                self._check_block(body, scope)
            if node.default_block:
                self._check_block(node.default_block, scope)

        elif isinstance(node, LoopStmt):
            cond_t = self._infer(node.condition, scope)
            if not types_equal(cond_t, T_SWITCH):
                raise TypeError_(f"loop condition must be switch, got {cond_t}", node.loc)
            self._check_block(node.body, scope)

        elif isinstance(node, ForEachStmt):
            it_type = self._infer(node.iterable, scope)
            if it_type.name != "crate":
                raise TypeError_(f"for-in requires a crate, got {it_type}", node.loc)
            inner = it_type.inner or T_EMPTY
            inner_scope = Scope(parent=scope)
            inner_scope.define(node.var, inner)
            self._check_block(node.body, inner_scope)

        elif isinstance(node, ExprStmt):
            self._infer(node.expr, scope)

        elif isinstance(node, (JamStmt, SkipStmt)):
            pass

    def _check_recipe(self, node: RecipeDecl):
        scope = Scope(parent=self.globals)
        for p in node.params:
            if p.variadic:
                scope.define(p.name, t_crate(p.type_node.inner or p.type_node))
            else:
                scope.define(p.name, p.type_node)
            if p.default is not None:
                dt = self._infer(p.default, self.globals)
                if not types_equal(dt, p.type_node):
                    raise TypeError_(
                        f"Default value for '{p.name}' has type {dt}, expected {p.type_node}",
                        node.loc)
        old_ret = self._current_return_type
        if node.return_types:
            self._current_return_type = TypeNode(f"__ret_{node.name}")
        else:
            self._current_return_type = node.return_type
        self._check_block(node.body, scope)
        self._current_return_type = old_ret

    def _check_block(self, stmts: List[Node], parent: Scope):
        block_scope = Scope(parent=parent)
        for s in stmts:
            self._check_stmt(s, block_scope)

    def _check_field_type(self, obj_type: TypeNode, field: str, assigned: TypeNode, loc: Loc):
        if obj_type.name not in self._blueprints:
            raise TypeError_(f"Field access on non-blueprint type {obj_type}", loc)
        bp = self._blueprints[obj_type.name]
        for f in bp.fields:
            if f.name == field:
                if not types_equal(f.type_node, assigned):
                    raise TypeError_(
                        f"Field '{field}' is {f.type_node} but assigned {assigned}", loc)
                return
        raise TypeError_(f"Blueprint '{obj_type.name}' has no field '{field}'", loc)

    # ------------------------------------------------------------------
    # Type inference
    # ------------------------------------------------------------------

    def _infer(self, node: Node, scope: Scope) -> TypeNode:
        t = self._infer_inner(node, scope)
        node.rtype = t
        return t

    def _infer_inner(self, node: Node, scope: Scope) -> TypeNode:
        if isinstance(node, IntLit):     return T_UNIT
        if isinstance(node, DecimalLit): return T_DECIMAL
        if isinstance(node, TextLit):    return T_TEXT
        if isinstance(node, SwitchLit):  return T_SWITCH
        if isinstance(node, EmptyLit):   return T_EMPTY

        if isinstance(node, InterpTextLit):
            for part in node.parts:
                if isinstance(part, Node):
                    self._infer(part, scope)
            return T_TEXT

        if isinstance(node, CrateLit):
            if not node.elements:
                return t_crate(T_EMPTY)
            elem_t = self._infer(node.elements[0], scope)
            for e in node.elements[1:]:
                et = self._infer(e, scope)
                if not types_equal(elem_t, et):
                    raise TypeError_("Crate elements must all be the same type", node.loc)
            return t_crate(elem_t)

        if isinstance(node, Ident):
            entry = scope.lookup(node.name)
            if entry is None:
                raise TypeError_(f"Undefined variable '{node.name}'", node.loc)
            return entry[0]

        if isinstance(node, BinOp):
            return self._infer_binop(node, scope)

        if isinstance(node, UnaryOp):
            if node.op == "flip":
                t = self._infer(node.operand, scope)
                if not types_equal(t, T_SWITCH):
                    raise TypeError_(f"flip requires switch, got {t}", node.loc)
                return T_SWITCH
            if node.op == "-":
                t = self._infer(node.operand, scope)
                if t.name not in ("unit", "decimal"):
                    raise TypeError_(f"Unary '-' requires unit or decimal, got {t}", node.loc)
                return t

        if isinstance(node, IndexExpr):
            t = self._infer(node.target, scope)
            if t.name != "crate":
                raise TypeError_(f"Index on non-crate type {t}", node.loc)
            self._infer(node.index, scope)
            return t.inner or T_EMPTY

        if isinstance(node, FieldExpr):
            return self._infer_field(node, scope)

        if isinstance(node, CallExpr):
            return self._infer_call(node, scope)

        if isinstance(node, BuildExpr):
            return self._infer_build(node, scope)

        if isinstance(node, WireExpr):
            entry = scope.lookup(node.target)
            if entry is None:
                raise TypeError_(f"wire: undefined variable '{node.target}'", node.loc)
            return t_wire(entry[0])

        if isinstance(node, UnwrapExpr):
            t = self._infer(node.target, scope)
            if t.name != "wire":
                raise TypeError_(f"unwrap on non-wire type {t}", node.loc)
            return t.inner or T_EMPTY

        if isinstance(node, SmeltExpr):
            self._infer(node.value, scope)
            return node.target_type

        raise TypeError_(f"Cannot infer type of {type(node).__name__}", Loc(0, 0))

    def _infer_binop(self, node: BinOp, scope: Scope) -> TypeNode:
        lt = self._infer(node.left, scope)
        rt = self._infer(node.right, scope)
        op = node.op
        if op in ("and", "or"):
            return T_SWITCH
        if op in ("==", "!=", "<", ">", "<=", ">="):
            return T_SWITCH
        if op in ("+", "-", "*", "/", "%"):
            if lt.name == "text" or rt.name == "text":
                return T_TEXT
            if lt.name == "decimal" or rt.name == "decimal":
                return T_DECIMAL
            if lt.name == "unit" and rt.name == "unit":
                return T_UNIT
            raise TypeError_(f"Cannot apply '{op}' to {lt} and {rt}", node.loc)
        raise TypeError_(f"Unknown operator '{op}'", node.loc)

    def _infer_field(self, node: FieldExpr, scope: Scope) -> TypeNode:
        obj_t = self._infer(node.target, scope)
        if obj_t.name in self._blueprints:
            bp = self._blueprints[obj_t.name]
            for f in bp.fields:
                if f.name == node.field:
                    return f.type_node
            raise TypeError_(f"Blueprint '{obj_t.name}' has no field '{node.field}'", node.loc)
        return T_TEXT

    def _infer_call(self, node: CallExpr, scope: Scope) -> TypeNode:
        if isinstance(node.callee, FieldExpr):
            obj_t = self._infer(node.callee.target, scope)
            method = node.callee.field
            for a in node.args:
                self._infer(a, scope)
            if isinstance(node.callee.target, Ident):
                key = (node.callee.target.name, method)
                if key in STDLIB_METHODS:
                    return STDLIB_METHODS[key]
            if obj_t.name == "crate":
                if method in ("push", "set", "sort", "reverse"): return T_EMPTY
                if method == "pop":                               return obj_t.inner or T_EMPTY
                if method in ("length", "index"):                 return T_UNIT
                if method == "get":                               return obj_t.inner or T_EMPTY
                if method == "contains":                          return T_SWITCH
                if method == "slice":                             return obj_t
                if method == "join":                              return T_TEXT
            if obj_t.name == "text":
                if method in ("upper", "lower", "trim", "replace", "slice"): return T_TEXT
                if method == "length":                            return T_UNIT
                if method == "index":                             return T_UNIT
                if method == "split":                             return t_crate(T_TEXT)
                if method in ("contains", "starts", "ends"):      return T_SWITCH
            if method == "read":   return T_TEXT
            if method == "write":  return T_EMPTY
            if method == "close":  return T_EMPTY
            if method == "status": return T_SWITCH
            if method == "length": return T_UNIT
            return T_EMPTY

        if isinstance(node.callee, Ident):
            name = node.callee.name
            if name in self._recipes:
                decl = self._recipes[name]
                for a in node.args:
                    self._infer(a, scope)
                if decl.return_types:
                    return TypeNode(f"__ret_{name}")
                return decl.return_type
            entry = scope.lookup(name)
            if entry:
                return entry[0]
            raise TypeError_(f"Undefined recipe '{name}'", node.loc)

        return T_EMPTY

    def _infer_build(self, node: BuildExpr, scope: Scope) -> TypeNode:
        if node.blueprint not in self._blueprints:
            raise TypeError_(f"Unknown blueprint '{node.blueprint}'", node.loc)
        bp = self._blueprints[node.blueprint]
        expected = {f.name: f.type_node for f in bp.fields}
        for fname, fexpr in node.kwargs:
            if fname not in expected:
                raise TypeError_(f"Blueprint '{node.blueprint}' has no field '{fname}'", node.loc)
            actual = self._infer(fexpr, scope)
            if not types_equal(actual, expected[fname]):
                raise TypeError_(
                    f"Field '{fname}' expects {expected[fname]}, got {actual}", node.loc)
        return TypeNode(node.blueprint)
