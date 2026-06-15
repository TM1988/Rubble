"""
Rubble AST Node Definitions
Every construct in the language is represented as a node in the Abstract Syntax Tree.
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Node:
    """Base class for all AST nodes."""
    pass


# ---------------------------------------------------------------------------
# Literals & Identifiers
# ---------------------------------------------------------------------------

@dataclass
class IntLiteral(Node):
    value: int

@dataclass
class DecimalLiteral(Node):
    value: float

@dataclass
class TextLiteral(Node):
    value: str

@dataclass
class SwitchLiteral(Node):
    value: bool  # True / False

@dataclass
class EmptyLiteral(Node):
    """Represents the `empty` keyword (null/none)."""
    pass

@dataclass
class Identifier(Node):
    name: str

@dataclass
class CrateLiteral(Node):
    """Array / list literal: [expr, expr, ...]"""
    elements: List[Node]


# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------

@dataclass
class BinaryOp(Node):
    left: Node
    op: str   # +  -  *  /  %  ==  !=  <  >  <=  >=  and  or
    right: Node

@dataclass
class UnaryOp(Node):
    op: str   # -  flip
    operand: Node

@dataclass
class IndexAccess(Node):
    """crate[index]"""
    target: Node
    index: Node

@dataclass
class FieldAccess(Node):
    """blueprint_instance.field"""
    target: Node
    field: str

@dataclass
class MethodCall(Node):
    """obj.method(args)  — used for library calls like panel.prompt(...)"""
    target: Node
    method: str
    args: List[Node]

@dataclass
class FunctionCall(Node):
    name: str
    args: List[Node]

@dataclass
class BuildExpr(Node):
    """build BlueprintName(field: val, ...)"""
    blueprint_name: str
    kwargs: List[tuple]   # [(field_name, expr), ...]

@dataclass
class WireExpr(Node):
    """wire varname  — creates a reference/pointer to a variable"""
    target: str

@dataclass
class UnwrapExpr(Node):
    """unwrap expr  — dereferences a pointer"""
    target: Node

@dataclass
class SmeltExpr(Node):
    """smelt(value, TargetType)"""
    value: Node
    target_type: str


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------

@dataclass
class SlotDecl(Node):
    """slot name = expr  |  lock slot name = expr"""
    name: str
    value: Node
    is_lock: bool = False          # True if prefixed with `lock`

@dataclass
class Assignment(Node):
    """name = expr  |  name[index] = expr  |  unwrap ptr = expr"""
    target: Node   # Identifier | IndexAccess | UnwrapExpr
    value: Node

@dataclass
class WriteStmt(Node):
    """write expr"""
    value: Node

@dataclass
class YieldStmt(Node):
    """yield expr"""
    value: Node

@dataclass
class JamStmt(Node):
    """jam — break out of the current loop"""
    pass

@dataclass
class WreckStmt(Node):
    """wreck "message" — fatal panic"""
    message: Node

@dataclass
class ScrapStmt(Node):
    """scrap varname — deallocate / delete a variable"""
    name: str

@dataclass
class IfStmt(Node):
    condition: Node
    then_block: List[Node]
    elif_clauses: List[tuple]   # [(condition, block), ...]
    else_block: Optional[List[Node]]

@dataclass
class LoopStmt(Node):
    """loop condition { body }"""
    condition: Node
    body: List[Node]

@dataclass
class ForEachStmt(Node):
    """for item in crate { body }  — syntactic sugar over loop"""
    var: str
    iterable: Node
    body: List[Node]

@dataclass
class ExprStmt(Node):
    """An expression used as a statement (e.g., a bare function call)."""
    expr: Node


# ---------------------------------------------------------------------------
# Top-level declarations
# ---------------------------------------------------------------------------

@dataclass
class Param(Node):
    name: str
    type_name: str

@dataclass
class RecipeDecl(Node):
    """recipe name(params) -> return_type { body }"""
    name: str
    params: List[Param]
    return_type: str          # 'empty' means void
    body: List[Node]

@dataclass
class BlueprintDecl(Node):
    """blueprint Name { field: type, ... }"""
    name: str
    fields: List[Param]       # reuse Param for (field_name, type_name)

@dataclass
class GatherStmt(Node):
    """gather "path/to/module"  |  gather stdlib_name"""
    path: str


@dataclass
class Program(Node):
    statements: List[Node]
