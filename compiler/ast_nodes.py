"""
Rubble Compiler — AST Node Definitions
All nodes carry source location (line, col) for error reporting.
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple, Dict


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

@dataclass
class UnionType(Node):
    """Union type: unit | text means either unit or text"""
    types: List[TypeNode]
    loc: Loc

@dataclass
class IntersectionType(Node):
    """Intersection type: type1 & type2 means both types must be satisfied"""
    types: List[TypeNode]
    loc: Loc

@dataclass
class NullableType(Node):
    """Nullable type: unit? means either unit or null"""
    inner_type: TypeNode
    loc: Loc

@dataclass
class TupleType(Node):
    """Tuple type: (unit, text) means a tuple of unit and text"""
    types: List[TypeNode]
    loc: Loc

@dataclass
class RecordLit(Node):
    """Record literal: {x: 10, y: 20}"""
    fields: Dict[str, Node]
    loc: Loc

@dataclass
class TuplePattern(Node):
    """Tuple pattern: (a, b) for matching tuples"""
    patterns: List[Node]
    loc: Loc

@dataclass
class ArrayType(Node):
    """Array type: unit[] means an array of unit"""
    element_type: TypeNode
    loc: Loc

@dataclass
class MapType(Node):
    """Map type: map[K, V] means a map from K to V"""
    key_type: TypeNode
    value_type: TypeNode
    loc: Loc

@dataclass
class SetType(Node):
    """Set type: set[T] means a set of T"""
    element_type: TypeNode
    loc: Loc

@dataclass
class OptionalChainExpr(Node):
    """Optional chaining: obj?.field or obj?.method()"""
    target: Node
    field: str
    loc: Loc

@dataclass
class NullCoalesceExpr(Node):
    """Null coalescing: value ?? default"""
    value: Node
    default: Node
    loc: Loc

@dataclass
class MacroDecl(Node):
    """Macro declaration: macro name(params) { body }"""
    name: str
    params: List[str]
    body: List[Node]
    loc: Loc

@dataclass
class MacroCall(Node):
    """Macro call: macro_name(args)"""
    name: str
    args: List[Node]
    loc: Loc


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
    """
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

@dataclass
class RangeExpr(Node):
    """Range expression: start..end for range loops"""
    start: Node
    end: Node
    loc: Loc

@dataclass
class SpreadExpr(Node):
    """Spread expression: ...crate or ...array"""
    value: Node
    loc: Loc

@dataclass
class NamedArg(Node):
    """Named argument in function call: name: value"""
    name: str
    value: Node
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
    type_node: Optional[TypeNode] = None

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
    """continue - skip to next loop iteration"""
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
class DestructPattern(Node):
    """Destructuring pattern: Vec2(x, y) or Point(x: 0, y: 0)"""
    type_name: str
    bindings: List[Tuple[str, Optional[Node]]]  # (field_name, optional_value)
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
    loc: Loc
    default: Optional[Node] = None
    variadic: bool = False

@dataclass
class LambdaExpr(Node):
    """Lambda/closure expression: fn(x) { x * 2 }"""
    params: List[Param]
    body: List[Node]
    loc: Loc

@dataclass
class EnumDecl(Node):
    """Enum declaration: enum Color { Red, Green, Blue }"""
    name: str
    variants: List[str]
    loc: Loc

@dataclass
class ConstDecl(Node):
    """Constant declaration: const MAX_SIZE = 1024"""
    name: str
    value: Node
    loc: Loc

@dataclass
class TypeAliasDecl(Node):
    """Type alias declaration: type MyInt = unit"""
    name: str
    target_type: TypeNode
    loc: Loc

@dataclass
class Decorator(Node):
    """Decorator: @inline or @export"""
    name: str
    args: List[Node]  # Optional arguments for the decorator
    loc: Loc

@dataclass
class ModuleDecl(Node):
    """Module declaration: module my_module { ... }"""
    name: str
    body: List[Node]
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
    decorators: List['Decorator'] = None  # Decorators like @inline, @export

@dataclass
class BlueprintDecl(Node):
    name: str
    fields: List[Param]
    loc: Loc
    decorators: List[Decorator] = None  # Decorators like @export
    methods: List['MethodDecl'] = None  # Methods defined in the blueprint

@dataclass
class MethodDecl(Node):
    """Method declaration inside a blueprint: fn blueprint_name.method_name(params) -> return_type { ... }"""
    blueprint_name: str
    name: str
    params: List[Param]
    return_type: TypeNode
    body: List[Node]
    loc: Loc
    decorators: List[Decorator] = None

@dataclass
class Program(Node):
    stmts: List[Node]
