"""
Rubble Compiler — AST Node Definitions
All nodes carry source location (line, col) for error reporting.
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple


class Node:
    pass


# ---------------------------------------------------------------------------
# Source location mixin
# ---------------------------------------------------------------------------

@dataclass
class Loc:
    line: int
    col: int


# ---------------------------------------------------------------------------
# Type annotations (as strings resolved during type-checking)
# ---------------------------------------------------------------------------

@dataclass
class TypeNode(Node):
    """A type reference in source code, e.g. unit, decimal, text, switch, crate[unit]"""
    name: str          # "unit" | "decimal" | "text" | "switch" | "crate" | "empty" | custom
    inner: Optional['TypeNode'] = None   # for crate[T] or wire<T>

    def __str__(self):
        if self.inner:
            return f"{self.name}[{self.inner}]"
        return self.name


# ---------------------------------------------------------------------------
# Literals
# ---------------------------------------------------------------------------

@dataclass
class IntLit(Node):
    value: int
    loc: Loc

@dataclass
class DecimalLit(Node):
    value: float
    loc: Loc

@dataclass
class TextLit(Node):
    value: str
    loc: Loc

@dataclass
class SwitchLit(Node):
    value: bool
    loc: Loc

@dataclass
class EmptyLit(Node):
    loc: Loc

@dataclass
class CrateLit(Node):
    elements: List[Node]
    loc: Loc

@dataclass
class InterpTextLit(Node):
    """String interpolation: f"hello {name}, you are {age} years old"
    parts is a list of either str (literal chunk) or Node (expression to interpolate).
    ""
    parts: List   # List[str | Node]
    loc: Loc


@dataclass
class SwitchStmt(Node):
    value: Node
    arms: List[Tuple[Node, List[Node]]]  # [(pattern, body)]
    default_block: Optional[List[Node]]
    loc: Loc


@dataclass
class MatchExpr(Node):
    value: Node
    arms: List[Tuple[Node, Node]]  # [(pattern, expression)]
    default_expr: Optional[Node]
    loc: Loc



# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------

@dataclass
class Ident(Node):
    name: str
    loc: Loc

@dataclass
class BinOp(Node):
    left: Node
    op: str
    right: Node
    loc: Loc

@dataclass
class UnaryOp(Node):
    op: str       # "-" | "flip"
    operand: Node
    loc: Loc

@dataclass
class IndexExpr(Node):
    target: Node
    index: Node
    loc: Loc

@dataclass
class FieldExpr(Node):
    target: Node
    field: str
    loc: Loc

@dataclass
class CallExpr(Node):
    callee: Node        # Ident or FieldExpr (for method calls)
    args: List[Node]
    loc: Loc

@dataclass
class BuildExpr(Node):
    blueprint: str
    kwargs: List[Tuple[str, Node]]
    loc: Loc

@dataclass
class WireExpr(Node):
    target: str
    loc: Loc

@dataclass
class UnwrapExpr(Node):
    target: Node
    loc: Loc

@dataclass
class SmeltExpr(Node):
    value: Node
    target_type: TypeNode
    loc: Loc


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------

@dataclass
class SlotDecl(Node):
    name: str
    value: Node
    is_lock: bool
    loc: Loc

@dataclass
class AssignStmt(Node):
    target: Node          # Ident | IndexExpr | UnwrapExpr | FieldExpr
    value: Node
    loc: Loc

@dataclass
class WriteStmt(Node):
    value: Node
    loc: Loc

@dataclass
class YieldStmt(Node):
    value: Node
    loc: Loc

@dataclass
class JamStmt(Node):
    loc: Loc
    label: Optional[str] = None   # labeled break: jam outer

@dataclass
class SkipStmt(Node):
    """continue — skip to next loop iteration"""
    loc: Loc
    label: Optional[str] = None   # labeled continue: skip outer

@dataclass
class WreckStmt(Node):
    message: Node
    loc: Loc

@dataclass
class ScrapStmt(Node):
    name: str
    loc: Loc

@dataclass
class ExprStmt(Node):
    expr: Node
    loc: Loc

@dataclass
class IfStmt(Node):
    condition: Node
    then_block: List[Node]
    elif_clauses: List[Tuple[Node, List[Node]]]
    else_block: Optional[List[Node]]
    loc: Loc

@dataclass
class LoopStmt(Node):
    condition: Node
    body: List[Node]
    loc: Loc
    label: Optional[str] = None   # optional loop label for labeled break/continue

@dataclass
class ForEachStmt(Node):
    var: str
    iterable: Node
    body: List[Node]
    loc: Loc
    label: Optional[str] = None

@dataclass
class MatchStmt(Node):
    """match value { case x => block ... default => block }"""
    value: Node
    arms: List[Tuple[Node, List[Node]]]   # (pattern_expr, body)
    default_block: Optional[List[Node]]
    loc: Loc

@dataclass
class GatherStmt(Node):
    module: str
    loc: Loc


# ---------------------------------------------------------------------------
# Top-level declarations
# ---------------------------------------------------------------------------

@dataclass
class Param(Node):
    name: str
    type_node: TypeNode
    default: Optional[Node] = None
    variadic: bool = False
    loc: Loc

@dataclass
class RecipeDecl(Node):
    name: str
    params: List[Param]
    return_type: TypeNode
    body: List[Node]
    loc: Loc
    # Multi-return: if return_types has >1 entry, the recipe returns a
    # heap-allocated blueprint named __ret_<name> generated automatically.
    return_types: Optional[List['TypeNode']] = None  # None = single return

@dataclass
class BlueprintDecl(Node):
    name: str
    fields: List[Param]
    loc: Loc

@dataclass
class Program(Node):
    stmts: List[Node]
