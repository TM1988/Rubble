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

@dataclass
class SkipStmt(Node):
    """skip — continue to next loop iteration"""
    loc: Loc

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

@dataclass
class ForEachStmt(Node):
    var: str
    iterable: Node
    body: List[Node]
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

@dataclass
class RecipeDecl(Node):
    name: str
    params: List[Param]
    return_type: TypeNode
    body: List[Node]
    loc: Loc

@dataclass
class BlueprintDecl(Node):
    name: str
    fields: List[Param]
    loc: Loc

@dataclass
class Program(Node):
    stmts: List[Node]
