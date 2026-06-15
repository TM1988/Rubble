"""
Rubble Tree-Walk Interpreter
Walks the AST produced by the parser and executes each node directly.
"""

import sys
from typing import Any, Dict, List, Optional

from .ast_nodes import *
from .stdlib import STDLIB_REGISTRY, RubbleError, FileStream, Connection


# ---------------------------------------------------------------------------
# Runtime values & exceptions
# ---------------------------------------------------------------------------

class RubbleWreck(Exception):
    """Raised by the `wreck` keyword — fatal program panic."""
    def __init__(self, message: str):
        super().__init__(f"\n[WRECK] {message}")


class RubbleReturn(Exception):
    """Used to unwind the call stack when `yield` is executed."""
    def __init__(self, value: Any):
        self.value = value


class RubbleJam(Exception):
    """Used to break out of a loop via `jam`."""
    pass


class WireRef:
    """Represents a pointer/reference to a variable slot in an environment."""
    def __init__(self, env: 'Environment', name: str):
        self.env = env
        self.name = name

    def get(self) -> Any:
        return self.env.get(self.name)

    def set(self, value: Any):
        self.env.assign(self.name, value)

    def __repr__(self):
        return f"<wire -> {self.name}>"


class BlueprintInstance:
    """A runtime instance of a blueprint (struct/class)."""
    def __init__(self, blueprint_name: str, fields: Dict[str, Any]):
        self.blueprint_name = blueprint_name
        self.fields = fields

    def __repr__(self):
        fields_str = ", ".join(f"{k}: {v!r}" for k, v in self.fields.items())
        return f"{self.blueprint_name}({fields_str})"


class RubbleRecipe:
    """A callable recipe (function) stored at runtime."""
    def __init__(self, decl: 'RecipeDecl', closure: 'Environment'):
        self.decl = decl
        self.closure = closure

    def __repr__(self):
        return f"<recipe {self.decl.name}>"


# ---------------------------------------------------------------------------
# Environment (scope)
# ---------------------------------------------------------------------------

class RuntimeError_(Exception):
    def __init__(self, message: str):
        super().__init__(f"[Runtime Error] {message}")


class Environment:
    def __init__(self, parent: Optional['Environment'] = None):
        self._vars: Dict[str, Any] = {}
        self._locked: set = set()
        self.parent = parent

    def define(self, name: str, value: Any, locked: bool = False):
        self._vars[name] = value
        if locked:
            self._locked.add(name)

    def _find_env(self, name: str) -> Optional['Environment']:
        if name in self._vars:
            return self
        if self.parent:
            return self.parent._find_env(name)
        return None

    def get(self, name: str) -> Any:
        env = self._find_env(name)
        if env is None:
            raise RuntimeError_(f"Undefined variable: '{name}'")
        return env._vars[name]

    def assign(self, name: str, value: Any):
        env = self._find_env(name)
        if env is None:
            raise RuntimeError_(f"Undefined variable: '{name}'")
        if name in env._locked:
            raise RuntimeError_(f"Cannot reassign locked (constant) variable: '{name}'")
        env._vars[name] = value


# ---------------------------------------------------------------------------
# Interpreter
# ---------------------------------------------------------------------------

class Interpreter:
    def __init__(self):
        self.global_env = Environment()
        self._blueprints: Dict[str, BlueprintDecl] = {}
        self._setup_globals()

    def _setup_globals(self):
        """Seed the global scope with stdlib objects."""
        for name, obj in STDLIB_REGISTRY.items():
            self.global_env.define(name, obj)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def execute(self, program: Program, env: Environment = None):
        env = env or self.global_env
        for stmt in program.statements:
            self._exec(stmt, env)

    # ------------------------------------------------------------------
    # Statement dispatch
    # ------------------------------------------------------------------

    def _exec(self, node: Node, env: Environment) -> Any:
        method = f"_exec_{type(node).__name__}"
        handler = getattr(self, method, None)
        if handler is None:
            raise RuntimeError_(f"No executor for node type: {type(node).__name__}")
        return handler(node, env)

    def _exec_Program(self, node: Program, env: Environment):
        for stmt in node.statements:
            self._exec(stmt, env)

    def _exec_GatherStmt(self, node: GatherStmt, env: Environment):
        """
        `gather` imports a stdlib name or a .rbl file.
        Stdlib names are already seeded; file imports are executed.
        """
        if node.path in STDLIB_REGISTRY:
            # Already available globally — nothing extra to do
            return
        # Treat as a file path
        import os
        path = node.path
        if not path.endswith('.rbl') and not path.endswith('.rubble'):
            path += '.rbl'
        if not os.path.isabs(path):
            path = os.path.join(os.getcwd(), path)
        if not os.path.exists(path):
            raise RuntimeError_(f"gather: file not found: {path!r}")
        with open(path, 'r', encoding='utf-8') as f:
            source = f.read()
        from .lexer import Lexer
        from .parser import Parser
        tokens = Lexer(source).tokenize()
        ast = Parser(tokens).parse()
        self.execute(ast, self.global_env)

    def _exec_BlueprintDecl(self, node: BlueprintDecl, env: Environment):
        self._blueprints[node.name] = node

    def _exec_RecipeDecl(self, node: RecipeDecl, env: Environment):
        recipe = RubbleRecipe(node, env)
        env.define(node.name, recipe)

    def _exec_SlotDecl(self, node: SlotDecl, env: Environment):
        value = self._eval(node.value, env)
        env.define(node.name, value, locked=node.is_lock)

    def _exec_Assignment(self, node: Assignment, env: Environment):
        value = self._eval(node.value, env)
        target = node.target
        if isinstance(target, Identifier):
            env.assign(target.name, value)
        elif isinstance(target, IndexAccess):
            crate = self._eval(target.target, env)
            index = self._eval(target.index, env)
            if not isinstance(crate, list):
                raise RuntimeError_("Index assignment on a non-crate value")
            crate[int(index)] = value
        elif isinstance(target, UnwrapExpr):
            ref = self._eval(target.target, env)
            if not isinstance(ref, WireRef):
                raise RuntimeError_("Cannot unwrap a non-wire value")
            ref.set(value)
        elif isinstance(target, FieldAccess):
            obj = self._eval(target.target, env)
            if not isinstance(obj, BlueprintInstance):
                raise RuntimeError_(f"Field assignment on a non-blueprint value")
            obj.fields[target.field] = value
        else:
            raise RuntimeError_(f"Invalid assignment target: {type(target).__name__}")

    def _exec_WriteStmt(self, node: WriteStmt, env: Environment):
        value = self._eval(node.value, env)
        print(self._to_display(value))

    def _exec_YieldStmt(self, node: YieldStmt, env: Environment):
        value = self._eval(node.value, env)
        raise RubbleReturn(value)

    def _exec_JamStmt(self, node: JamStmt, env: Environment):
        raise RubbleJam()

    def _exec_WreckStmt(self, node: WreckStmt, env: Environment):
        msg = self._eval(node.message, env)
        raise RubbleWreck(str(msg))

    def _exec_ScrapStmt(self, node: ScrapStmt, env: Environment):
        """Remove a variable from the nearest scope that holds it."""
        e = env._find_env(node.name)
        if e is None:
            raise RuntimeError_(f"scrap: undefined variable '{node.name}'")
        del e._vars[node.name]
        e._locked.discard(node.name)

    def _exec_IfStmt(self, node: IfStmt, env: Environment):
        if self._is_truthy(self._eval(node.condition, env)):
            self._exec_block(node.then_block, env)
        else:
            for elif_cond, elif_body in node.elif_clauses:
                if self._is_truthy(self._eval(elif_cond, env)):
                    self._exec_block(elif_body, env)
                    return
            if node.else_block is not None:
                self._exec_block(node.else_block, env)

    def _exec_LoopStmt(self, node: LoopStmt, env: Environment):
        try:
            while self._is_truthy(self._eval(node.condition, env)):
                try:
                    self._exec_block(node.body, env)
                except RubbleJam:
                    break
        except RubbleJam:
            pass

    def _exec_ForEachStmt(self, node: ForEachStmt, env: Environment):
        iterable = self._eval(node.iterable, env)
        if not isinstance(iterable, (list, str)):
            raise RuntimeError_(f"for-in expects a crate or text, got {type(iterable).__name__}")
        loop_env = Environment(parent=env)
        try:
            for item in iterable:
                loop_env.define(node.var, item)
                try:
                    self._exec_block(node.body, loop_env)
                except RubbleJam:
                    break
        except RubbleJam:
            pass

    def _exec_ExprStmt(self, node: ExprStmt, env: Environment):
        self._eval(node.expr, env)

    # ------------------------------------------------------------------
    # Block execution
    # ------------------------------------------------------------------

    def _exec_block(self, stmts: List[Node], parent_env: Environment):
        block_env = Environment(parent=parent_env)
        for stmt in stmts:
            self._exec(stmt, block_env)

    # ------------------------------------------------------------------
    # Expression evaluation
    # ------------------------------------------------------------------

    def _eval(self, node: Node, env: Environment) -> Any:
        method = f"_eval_{type(node).__name__}"
        handler = getattr(self, method, None)
        if handler is None:
            raise RuntimeError_(f"No evaluator for node type: {type(node).__name__}")
        return handler(node, env)

    def _eval_IntLiteral(self, node: IntLiteral, env: Environment) -> int:
        return node.value

    def _eval_DecimalLiteral(self, node: DecimalLiteral, env: Environment) -> float:
        return node.value

    def _eval_TextLiteral(self, node: TextLiteral, env: Environment) -> str:
        return node.value

    def _eval_SwitchLiteral(self, node: SwitchLiteral, env: Environment) -> bool:
        return node.value

    def _eval_EmptyLiteral(self, node: EmptyLiteral, env: Environment):
        return None

    def _eval_Identifier(self, node: Identifier, env: Environment) -> Any:
        return env.get(node.name)

    def _eval_CrateLiteral(self, node: CrateLiteral, env: Environment) -> list:
        return [self._eval(e, env) for e in node.elements]

    def _eval_BinaryOp(self, node: BinaryOp, env: Environment) -> Any:
        left = self._eval(node.left, env)
        right = self._eval(node.right, env)
        op = node.op
        if op == '+':
            # Support text concatenation
            if isinstance(left, str) or isinstance(right, str):
                return self._to_display(left) + self._to_display(right)
            return left + right
        if op == '-':  return left - right
        if op == '*':  return left * right
        if op == '/':
            if right == 0:
                raise RuntimeError_("Division by zero")
            return left / right
        if op == '%':  return left % right
        if op == '==': return left == right
        if op == '!=': return left != right
        if op == '<':  return left < right
        if op == '>':  return left > right
        if op == '<=': return left <= right
        if op == '>=': return left >= right
        if op == 'and': return self._is_truthy(left) and self._is_truthy(right)
        if op == 'or':  return self._is_truthy(left) or self._is_truthy(right)
        raise RuntimeError_(f"Unknown binary operator: {op!r}")

    def _eval_UnaryOp(self, node: UnaryOp, env: Environment) -> Any:
        operand = self._eval(node.operand, env)
        if node.op == '-':
            return -operand
        if node.op == 'flip':
            return not self._is_truthy(operand)
        raise RuntimeError_(f"Unknown unary operator: {node.op!r}")

    def _eval_IndexAccess(self, node: IndexAccess, env: Environment) -> Any:
        target = self._eval(node.target, env)
        index = self._eval(node.index, env)
        if isinstance(target, list):
            try:
                return target[int(index)]
            except IndexError:
                raise RuntimeError_(f"Crate index out of range: {index}")
        if isinstance(target, str):
            try:
                return target[int(index)]
            except IndexError:
                raise RuntimeError_(f"Text index out of range: {index}")
        raise RuntimeError_(f"Cannot index into type: {type(target).__name__}")

    def _eval_FieldAccess(self, node: FieldAccess, env: Environment) -> Any:
        target = self._eval(node.target, env)
        if isinstance(target, BlueprintInstance):
            if node.field not in target.fields:
                raise RuntimeError_(f"Blueprint '{target.blueprint_name}' has no field '{node.field}'")
            return target.fields[node.field]
        raise RuntimeError_(f"Field access on non-blueprint value: {type(target).__name__}")

    def _eval_MethodCall(self, node: MethodCall, env: Environment) -> Any:
        target = self._eval(node.target, env)
        args = [self._eval(a, env) for a in node.args]
        method = node.method

        # Crate (list) built-in methods
        if isinstance(target, list):
            return self._crate_method(target, method, args)

        # Text (str) built-in methods
        if isinstance(target, str):
            return self._text_method(target, method, args)

        # Blueprint instance method? (not supported yet — forward-compatible)
        if isinstance(target, BlueprintInstance):
            raise RuntimeError_(f"Blueprint method calls are not yet supported")

        # Stdlib objects: Panel, Cabinet, Machinery, Cable, FileStream, Connection
        callable_method = getattr(target, method, None)
        if callable_method is None:
            raise RuntimeError_(f"Object {type(target).__name__!r} has no action '{method}'")
        try:
            return callable_method(*args)
        except RubbleError as e:
            raise RuntimeError_(str(e))
        except TypeError as e:
            raise RuntimeError_(f"Wrong arguments for '{method}': {e}")

    def _crate_method(self, crate: list, method: str, args: list) -> Any:
        """Built-in methods on crate (list) values."""
        if method == "push":
            crate.append(args[0]); return None
        if method == "pop":
            if not crate: raise RuntimeError_("crate.pop: crate is empty")
            return crate.pop()
        if method == "length":
            return len(crate)
        if method == "get":
            return crate[int(args[0])]
        if method == "set":
            crate[int(args[0])] = args[1]; return None
        if method == "contains":
            return args[0] in crate
        raise RuntimeError_(f"Crate has no action '{method}'")

    def _text_method(self, text: str, method: str, args: list) -> Any:
        """Built-in methods on text (string) values."""
        if method == "length":  return len(text)
        if method == "upper":   return text.upper()
        if method == "lower":   return text.lower()
        if method == "trim":    return text.strip()
        if method == "split":
            sep = args[0] if args else " "
            return text.split(str(sep))
        if method == "contains": return str(args[0]) in text
        if method == "starts":   return text.startswith(str(args[0]))
        if method == "ends":     return text.endswith(str(args[0]))
        raise RuntimeError_(f"Text has no action '{method}'")

    def _eval_FunctionCall(self, node: FunctionCall, env: Environment) -> Any:
        callee = env.get(node.name)
        args = [self._eval(a, env) for a in node.args]
        if not isinstance(callee, RubbleRecipe):
            raise RuntimeError_(f"'{node.name}' is not a recipe")
        return self._call_recipe(callee, args)

    def _call_recipe(self, recipe: RubbleRecipe, args: List[Any]) -> Any:
        decl = recipe.decl
        if len(args) != len(decl.params):
            raise RuntimeError_(
                f"Recipe '{decl.name}' expects {len(decl.params)} argument(s), got {len(args)}"
            )
        call_env = Environment(parent=recipe.closure)
        for param, value in zip(decl.params, args):
            call_env.define(param.name, value)
        try:
            self._exec_block(decl.body, call_env)
        except RubbleReturn as ret:
            return ret.value
        return None

    def _eval_BuildExpr(self, node: BuildExpr, env: Environment) -> BlueprintInstance:
        if node.blueprint_name not in self._blueprints:
            raise RuntimeError_(f"Unknown blueprint: '{node.blueprint_name}'")
        decl = self._blueprints[node.blueprint_name]
        expected = {p.name for p in decl.fields}
        provided = {k for k, _ in node.kwargs}
        missing = expected - provided
        extra = provided - expected
        if missing:
            raise RuntimeError_(f"build {node.blueprint_name}: missing fields: {missing}")
        if extra:
            raise RuntimeError_(f"build {node.blueprint_name}: unknown fields: {extra}")
        fields = {}
        for fname, fexpr in node.kwargs:
            fields[fname] = self._eval(fexpr, env)
        return BlueprintInstance(node.blueprint_name, fields)

    def _eval_WireExpr(self, node: WireExpr, env: Environment) -> WireRef:
        # Validate that the variable exists
        env.get(node.target)
        e = env._find_env(node.target)
        return WireRef(e, node.target)

    def _eval_UnwrapExpr(self, node: UnwrapExpr, env: Environment) -> Any:
        ref = self._eval(node.target, env)
        if not isinstance(ref, WireRef):
            raise RuntimeError_("Cannot unwrap a non-wire value")
        return ref.get()

    def _eval_SmeltExpr(self, node: SmeltExpr, env: Environment) -> Any:
        value = self._eval(node.value, env)
        t = node.target_type
        try:
            if t == "unit":    return int(value)
            if t == "decimal": return float(value)
            if t == "text":    return self._to_display(value)
            if t == "switch":  return bool(value)
        except (ValueError, TypeError) as e:
            raise RuntimeError_(f"smelt failed: cannot convert {value!r} to {t}: {e}")
        raise RuntimeError_(f"smelt: unknown target type '{t}'")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_truthy(self, value: Any) -> bool:
        if value is None:       return False
        if isinstance(value, bool): return value
        if isinstance(value, (int, float)): return value != 0
        if isinstance(value, str):  return len(value) > 0
        if isinstance(value, list): return len(value) > 0
        return True

    def _to_display(self, value: Any) -> str:
        if value is None:           return "empty"
        if isinstance(value, bool): return "true" if value else "false"
        if isinstance(value, list):
            inner = ", ".join(self._to_display(v) for v in value)
            return f"[{inner}]"
        return str(value)
