"""
Rubble Compiler — LLVM IR Code Generator
Lowers a type-checked Rubble AST to LLVM IR text (.ll).

Targets:
  unit    -> i64
  decimal -> double
  text    -> i8*
  switch  -> i1
  crate   -> { i64, <inner>* }   (length + heap pointer)
  wire<T> -> <T>*
  empty   -> void / null ptr
"""

from typing import Dict, List, Optional, Tuple
from .ast_nodes import *
from .type_checker import TypeNode, T_UNIT, T_DECIMAL, T_TEXT, T_SWITCH, T_EMPTY, types_equal


# ---------------------------------------------------------------------------
# LLVM type mapping
# ---------------------------------------------------------------------------

def llvm_type(t: TypeNode) -> str:
    if t.name == "unit":    return "i64"
    if t.name == "decimal": return "double"
    if t.name == "text":    return "i8*"
    if t.name == "switch":  return "i1"
    if t.name == "empty":   return "void"
    if t.name == "wire":
        return llvm_type(t.inner) + "*"
    if t.name == "crate":
        inner = llvm_type(t.inner) if t.inner else "i8"
        return f"%Crate_{inner.replace('*','p').replace(' ','_')}*"
    # Blueprint / custom struct
    return f"%{t.name}*"


def llvm_type_for_alloca(t: TypeNode) -> str:
    """Type used in alloca — structs without the pointer."""
    if t.name == "crate":
        inner = llvm_type(t.inner) if t.inner else "i8"
        return f"%Crate_{inner.replace('*','p').replace(' ','_')}"
    if t.name not in ("unit","decimal","text","switch","empty","wire"):
        return f"%{t.name}"
    return llvm_type(t)


# ---------------------------------------------------------------------------
# String constant pool
# ---------------------------------------------------------------------------

class StringPool:
    def __init__(self):
        self._pool: Dict[str, str] = {}
        self._counter = 0

    def get(self, value: str) -> str:
        if value not in self._pool:
            name = f"@.str.{self._counter}"
            self._counter += 1
            self._pool[value] = name
        return self._pool[value]

    def emit(self) -> List[str]:
        lines = []
        for value, name in self._pool.items():
            escaped = self._escape(value)
            length = len(value.encode('utf-8')) + 1  # +1 for null terminator
            lines.append(
                f'{name} = private unnamed_addr constant [{length} x i8] c"{escaped}\\00", align 1'
            )
        return lines

    def _escape(self, s: str) -> str:
        result = []
        for ch in s:
            if ch == '"':  result.append('\\22')
            elif ch == '\\': result.append('\\5C')
            elif ch == '\n': result.append('\\0A')
            elif ch == '\t': result.append('\\09')
            elif ch == '\r': result.append('\\0D')
            elif ch == '\0': result.append('\\00')
            else:            result.append(ch)
        return ''.join(result)


# ---------------------------------------------------------------------------
# Code generator
# ---------------------------------------------------------------------------

class CodeGen:
    def __init__(self, filename: str = "<input>"):
        self.filename = filename
        self._strings = StringPool()
        self._lines: List[str] = []
        self._counter = 0
        self._blueprints: Dict[str, BlueprintDecl] = {}
        self._crate_types: set = set()

        # Local variable map per function: name -> (alloca_reg, llvm_type_str)
        self._locals: Dict[str, Tuple[str, str]] = {}
        # Global constant pool for lock slot at module level
        self._globals_code: List[str] = []

        self._in_function = False
        self._current_func_name = ""
        self._loop_exit_blocks: List[str] = []   # stack for jam

    def _fresh(self, prefix="tmp") -> str:
        self._counter += 1
        return f"%{prefix}_{self._counter}"

    def _label(self, prefix="lbl") -> str:
        self._counter += 1
        return f"{prefix}_{self._counter}"

    def _emit(self, line: str):
        self._lines.append(line)

    def _emit_indent(self, line: str):
        self._lines.append("  " + line)

    # ------------------------------------------------------------------
    # Public entry
    # ------------------------------------------------------------------

    def generate(self, program: Program) -> str:
        self._collect_blueprints(program)
        self._emit_prelude()
        self._emit_stdlib_decls()
        self._emit_blueprint_types()
        self._emit_program(program)
        self._emit_postlude()
        return "\n".join(self._lines)

    # ------------------------------------------------------------------
    # Prelude / postlude
    # ------------------------------------------------------------------

    def _emit_prelude(self):
        self._emit(f'; Rubble compiled output — {self.filename}')
        # Use a generic datalayout; clang will override with the host triple
        self._emit('target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"')
        self._emit('')

    def _emit_postlude(self):
        # String pool at the end
        if self._strings._pool:
            self._emit('')
            for line in self._strings.emit():
                self._emit(line)

    def _emit_stdlib_decls(self):
        self._emit('; ---- External C stdlib declarations ----')
        # I/O
        self._emit('declare i32 @printf(i8*, ...)')
        self._emit('declare i32 @puts(i8*)')
        self._emit('declare i8* @fgets(i8*, i32, i8*)')
        self._emit('declare i32 @fflush(i8*)')
        self._emit('declare i8* @stdin_ptr() ; stub')
        # Memory
        self._emit('declare i8* @malloc(i64)')
        self._emit('declare void @free(i8*)')
        self._emit('declare i8* @memcpy(i8*, i8*, i64)')
        # String
        self._emit('declare i64 @strlen(i8*)')
        self._emit('declare i8* @strcpy(i8*, i8*)')
        self._emit('declare i8* @strcat(i8*, i8*)')
        self._emit('declare i32 @strcmp(i8*, i8*)')
        self._emit('declare i8* @strdup(i8*)')
        # Process
        self._emit('declare void @exit(i32) noreturn')
        self._emit('declare void @abort() noreturn')
        # Sleep
        self._emit('declare i32 @rubble_machinery_rest(i64)')
        self._emit('declare void @Sleep(i32)')
        # Rubble stdlib stubs (implemented in rubble_stdlib.c)
        self._emit('declare i8* @rubble_panel_prompt(i8*)')
        self._emit('declare i8* @rubble_panel_grab()')
        self._emit('declare i64 @rubble_machinery_ram()')
        self._emit('declare i64 @rubble_cabinet_open(i8*)')
        self._emit('declare i64 @rubble_cabinet_create(i8*)')
        self._emit('declare i64 @rubble_cable_connect(i8*, i64)')
        self._emit('declare i8* @rubble_line_read(i64)')
        self._emit('')

    def _collect_blueprints(self, program: Program):
        for s in program.stmts:
            if isinstance(s, BlueprintDecl):
                self._blueprints[s.name] = s

    def _emit_blueprint_types(self):
        if not self._blueprints:
            return
        self._emit('; ---- Blueprint struct types ----')
        for name, bp in self._blueprints.items():
            fields = ", ".join(llvm_type(f.type_node) for f in bp.fields)
            self._emit(f'%{name} = type {{ {fields} }}')
        self._emit('')

    # ------------------------------------------------------------------
    # Program
    # ------------------------------------------------------------------

    def _emit_program(self, program: Program):
        # Collect global lock slots
        global_slots = []
        other_stmts = []
        for s in program.stmts:
            if isinstance(s, SlotDecl) and s.is_lock and not self._in_function:
                global_slots.append(s)
            else:
                other_stmts.append(s)

        # Emit global constants
        for s in global_slots:
            self._emit_global_const(s)

        # Emit recipe declarations
        recipes = [s for s in other_stmts if isinstance(s, RecipeDecl)]
        non_recipes = [s for s in other_stmts if not isinstance(s, RecipeDecl)
                      and not isinstance(s, BlueprintDecl)
                      and not isinstance(s, GatherStmt)]

        for r in recipes:
            self._emit_recipe(r)

        # Wrap top-level non-recipe statements in main()
        if non_recipes:
            self._emit('')
            self._emit('define i32 @main() {')
            self._emit('entry:')
            self._in_function = True
            self._current_func_name = "main"
            self._locals = {}
            for s in non_recipes:
                self._emit_stmt(s)
            self._emit_indent('ret i32 0')
            self._emit('}')
            self._in_function = False

    def _emit_global_const(self, node: SlotDecl):
        """Emit a module-level global constant for lock slot."""
        typ = getattr(node, 'inferred_type', None)
        if typ is None:
            return
        ll = llvm_type(typ)
        # For text constants, create a global string reference
        if typ.name == "text" and isinstance(node.value, TextLit):
            str_name = self._strings.get(node.value.value)
            length = len(node.value.value.encode('utf-8')) + 1
            self._emit(f'@{node.name} = private global i8* getelementptr inbounds ([{length} x i8], [{length} x i8]* {str_name}, i64 0, i64 0)')
        elif typ.name == "unit" and isinstance(node.value, IntLit):
            self._emit(f'@{node.name} = private constant i64 {node.value.value}')
        elif typ.name == "decimal" and isinstance(node.value, DecimalLit):
            self._emit(f'@{node.name} = private constant double {node.value.value}')
        elif typ.name == "switch" and isinstance(node.value, SwitchLit):
            self._emit(f'@{node.name} = private constant i1 {1 if node.value.value else 0}')

    # ------------------------------------------------------------------
    # Recipe → LLVM function
    # ------------------------------------------------------------------

    def _emit_recipe(self, node: RecipeDecl):
        self._emit('')
        ret_ll = llvm_type(node.return_type) if node.return_type.name != "empty" else "void"
        params_ll = ", ".join(f"{llvm_type(p.type_node)} %{p.name}" for p in node.params)
        self._emit(f'define {ret_ll} @{node.name}({params_ll}) {{')
        self._emit('entry:')
        self._in_function = True
        self._current_func_name = node.name
        old_locals = self._locals
        self._locals = {}

        # Alloca for each parameter so they are mutable locals
        for p in node.params:
            ll = llvm_type(p.type_node)
            alloca = f"%{p.name}.addr"
            self._emit_indent(f'{alloca} = alloca {ll}')
            self._emit_indent(f'store {ll} %{p.name}, {ll}* {alloca}')
            self._locals[p.name] = (alloca, ll)

        for s in node.body:
            self._emit_stmt(s)

        # Default return for void recipes
        if node.return_type.name == "empty":
            self._emit_indent('ret void')
        else:
            # If no explicit yield, return zero value
            self._emit_indent(f'ret {ret_ll} {self._zero_value(node.return_type)}')

        self._emit('}')
        self._locals = old_locals
        self._in_function = False

    def _zero_value(self, t: TypeNode) -> str:
        if t.name == "unit":    return "0"
        if t.name == "decimal": return "0.0"
        if t.name == "switch":  return "0"
        if t.name in ("text", "wire", "crate"): return "null"
        return "null"

    # ------------------------------------------------------------------
    # Statement emission
    # ------------------------------------------------------------------

    def _emit_stmt(self, node: Node):
        if isinstance(node, SlotDecl):
            self._emit_slot(node)
        elif isinstance(node, AssignStmt):
            self._emit_assign(node)
        elif isinstance(node, WriteStmt):
            self._emit_write(node)
        elif isinstance(node, YieldStmt):
            self._emit_yield(node)
        elif isinstance(node, JamStmt):
            self._emit_jam(node)
        elif isinstance(node, WreckStmt):
            self._emit_wreck(node)
        elif isinstance(node, ScrapStmt):
            self._emit_scrap(node)
        elif isinstance(node, IfStmt):
            self._emit_if(node)
        elif isinstance(node, LoopStmt):
            self._emit_loop(node)
        elif isinstance(node, ForEachStmt):
            self._emit_foreach(node)
        elif isinstance(node, ExprStmt):
            self._emit_expr(node.expr)   # discard result
        elif isinstance(node, RecipeDecl):
            pass  # already emitted at top level
        elif isinstance(node, BlueprintDecl):
            pass  # already emitted as type
        elif isinstance(node, GatherStmt):
            pass  # handled at link time

    def _emit_slot(self, node: SlotDecl):
        typ = getattr(node, 'inferred_type', None)
        if typ is None:
            return
        ll = llvm_type(typ)
        alloca = f"%{node.name}.addr"
        self._emit_indent(f'{alloca} = alloca {ll}')
        val_reg = self._emit_expr(node.value)
        if val_reg:
            self._emit_indent(f'store {ll} {val_reg}, {ll}* {alloca}')
        self._locals[node.name] = (alloca, ll)

    def _emit_assign(self, node: AssignStmt):
        rhs = self._emit_expr(node.value)
        if isinstance(node.target, Ident):
            entry = self._locals.get(node.target.name)
            if entry:
                alloca, ll = entry
                self._emit_indent(f'store {ll} {rhs}, {ll}* {alloca}')
        elif isinstance(node.target, UnwrapExpr):
            ptr = self._emit_expr(node.target.target)
            t = getattr(node.target.target, 'rtype', None)
            if t and t.name == "wire":
                inner_ll = llvm_type(t.inner)
                self._emit_indent(f'store {inner_ll} {rhs}, {inner_ll}* {ptr}')
        elif isinstance(node.target, FieldExpr):
            self._emit_field_store(node.target, rhs)

    def _emit_field_store(self, field_expr: FieldExpr, val_reg: str):
        obj_t = getattr(field_expr.target, 'rtype', None)
        if obj_t and obj_t.name in self._blueprints:
            bp = self._blueprints[obj_t.name]
            for i, f in enumerate(bp.fields):
                if f.name == field_expr.field:
                    obj_ptr = self._emit_expr(field_expr.target)
                    field_ptr = self._fresh("fptr")
                    field_ll = llvm_type(f.type_node)
                    self._emit_indent(
                        f'{field_ptr} = getelementptr inbounds %{obj_t.name}, %{obj_t.name}* {obj_ptr}, i32 0, i32 {i}'
                    )
                    self._emit_indent(f'store {field_ll} {val_reg}, {field_ll}* {field_ptr}')
                    return

    def _emit_write(self, node: WriteStmt):
        val = self._emit_expr(node.value)
        t = getattr(node.value, 'rtype', T_TEXT)
        self._emit_write_value(val, t)

    def _emit_write_value(self, val_reg: str, t: TypeNode):
        if t.name == "text":
            # puts appends a newline automatically
            self._emit_indent(f'call i32 @puts(i8* {val_reg})')
        elif t.name == "unit":
            fmt_str  = "%lld\n"
            fmt_name = self._strings.get(fmt_str)
            flen     = len(fmt_str) + 1
            fmt_gep  = self._fresh("fmtgep")
            self._emit_indent(
                f'{fmt_gep} = getelementptr inbounds [{flen} x i8], [{flen} x i8]* {fmt_name}, i64 0, i64 0'
            )
            self._emit_indent(f'call i32 (i8*, ...) @printf(i8* {fmt_gep}, i64 {val_reg})')
        elif t.name == "decimal":
            fmt_str  = "%f\n"
            fmt_name = self._strings.get(fmt_str)
            flen     = len(fmt_str) + 1
            fmt_gep  = self._fresh("fmtgep")
            self._emit_indent(
                f'{fmt_gep} = getelementptr inbounds [{flen} x i8], [{flen} x i8]* {fmt_name}, i64 0, i64 0'
            )
            self._emit_indent(f'call i32 (i8*, ...) @printf(i8* {fmt_gep}, double {val_reg})')
        elif t.name == "switch":
            # print true or false
            true_str  = self._strings.get("true")
            false_str = self._strings.get("false")
            true_ptr  = self._fresh("trueptr")
            false_ptr = self._fresh("falseptr")
            sel       = self._fresh("boolstr")
            self._emit_indent(
                f'{true_ptr} = getelementptr inbounds [5 x i8], [5 x i8]* {self._get_str_const("true")}, i64 0, i64 0'
            )
            self._emit_indent(
                f'{false_ptr} = getelementptr inbounds [6 x i8], [6 x i8]* {self._get_str_const("false")}, i64 0, i64 0'
            )
            self._emit_indent(f'{sel} = select i1 {val_reg}, i8* {true_ptr}, i8* {false_ptr}')
            self._emit_indent(f'call i32 @puts(i8* {sel})')
        else:
            # fallback: just call puts with a placeholder
            self._emit_indent(f'call i32 @puts(i8* {val_reg})')

    def _get_str_const(self, s: str) -> str:
        """Get or create a string constant, return the global name."""
        return self._strings.get(s)

    def _emit_yield(self, node: YieldStmt):
        val = self._emit_expr(node.value)
        t = getattr(node.value, 'rtype', T_EMPTY)
        if t.name == "empty":
            self._emit_indent('ret void')
        else:
            self._emit_indent(f'ret {llvm_type(t)} {val}')
        # Unreachable after yield
        dead = self._label("after_yield")
        self._emit(f'{dead}:')

    def _emit_jam(self, node: JamStmt):
        if self._loop_exit_blocks:
            self._emit_indent(f'br label %{self._loop_exit_blocks[-1]}')
        dead = self._label("after_jam")
        self._emit(f'{dead}:')

    def _emit_wreck(self, node: WreckStmt):
        msg = self._emit_expr(node.message)
        # Print the message then call exit(1)
        self._emit_indent(f'call i32 @puts(i8* {msg})')
        self._emit_indent('call void @exit(i32 1)')
        self._emit_indent('unreachable')
        dead = self._label("after_wreck")
        self._emit(f'{dead}:')

    def _emit_scrap(self, node: ScrapStmt):
        entry = self._locals.get(node.name)
        if entry:
            alloca, ll = entry
            # For heap types (text, crate) emit free
            if ll in ("i8*",) or ll.endswith("*"):
                val = self._fresh("scrap")
                self._emit_indent(f'{val} = load {ll}, {ll}* {alloca}')
                cast = self._fresh("scrapcast")
                self._emit_indent(f'{cast} = bitcast {ll} {val} to i8*')
                self._emit_indent(f'call void @free(i8* {cast})')
            del self._locals[node.name]

    def _emit_if(self, node: IfStmt):
        cond = self._emit_expr(node.condition)
        then_lbl  = self._label("then")
        merge_lbl = self._label("merge")

        if node.elif_clauses or node.else_block:
            next_lbl = self._label("elif_or_else")
        else:
            next_lbl = merge_lbl

        self._emit_indent(f'br i1 {cond}, label %{then_lbl}, label %{next_lbl}')
        self._emit(f'{then_lbl}:')
        self._emit_block(node.then_block)
        self._emit_indent(f'br label %{merge_lbl}')

        # elif chains
        for idx, (ec, eb) in enumerate(node.elif_clauses):
            self._emit(f'{next_lbl}:')
            ec_val = self._emit_expr(ec)
            elif_body = self._label("elif_body")
            if idx < len(node.elif_clauses) - 1:
                next_lbl = self._label("elif_or_else")
            else:
                next_lbl = self._label("else") if node.else_block else merge_lbl
            self._emit_indent(f'br i1 {ec_val}, label %{elif_body}, label %{next_lbl}')
            self._emit(f'{elif_body}:')
            self._emit_block(eb)
            self._emit_indent(f'br label %{merge_lbl}')

        if node.else_block:
            self._emit(f'{next_lbl}:')
            self._emit_block(node.else_block)
            self._emit_indent(f'br label %{merge_lbl}')

        self._emit(f'{merge_lbl}:')

    def _emit_loop(self, node: LoopStmt):
        cond_lbl = self._label("loop_cond")
        body_lbl = self._label("loop_body")
        exit_lbl = self._label("loop_exit")

        self._loop_exit_blocks.append(exit_lbl)
        self._emit_indent(f'br label %{cond_lbl}')
        self._emit(f'{cond_lbl}:')
        cond = self._emit_expr(node.condition)
        self._emit_indent(f'br i1 {cond}, label %{body_lbl}, label %{exit_lbl}')
        self._emit(f'{body_lbl}:')
        self._emit_block(node.body)
        self._emit_indent(f'br label %{cond_lbl}')
        self._emit(f'{exit_lbl}:')
        self._loop_exit_blocks.pop()

    def _emit_foreach(self, node: ForEachStmt):
        it_val = self._emit_expr(node.iterable)
        it_t   = getattr(node.iterable, 'rtype', None)
        # For now, foreach over crate uses a manual index loop
        # crate layout: { i64 length, <inner>* data }
        idx_alloca = self._fresh("for_idx")
        self._emit_indent(f'{idx_alloca} = alloca i64')
        self._emit_indent(f'store i64 0, i64* {idx_alloca}')

        # Get length
        len_ptr  = self._fresh("len_ptr")
        len_val  = self._fresh("len_val")
        inner_ll = "i8"
        if it_t and it_t.name == "crate" and it_t.inner:
            inner_ll = llvm_type(it_t.inner)

        cond_lbl = self._label("for_cond")
        body_lbl = self._label("for_body")
        exit_lbl = self._label("for_exit")
        self._loop_exit_blocks.append(exit_lbl)

        crate_type = f"%Crate_{inner_ll.replace('*','p').replace(' ','_')}"
        self._emit_indent(f'br label %{cond_lbl}')
        self._emit(f'{cond_lbl}:')
        cur_idx = self._fresh("cur_idx")
        self._emit_indent(f'{cur_idx} = load i64, i64* {idx_alloca}')

        # Get crate length from struct field 0
        lp = self._fresh("lp")
        lv = self._fresh("lv")
        self._emit_indent(f'{lp} = getelementptr inbounds {crate_type}, {crate_type}* {it_val}, i32 0, i32 0')
        self._emit_indent(f'{lv} = load i64, i64* {lp}')
        cmp = self._fresh("for_cmp")
        self._emit_indent(f'{cmp} = icmp slt i64 {cur_idx}, {lv}')
        self._emit_indent(f'br i1 {cmp}, label %{body_lbl}, label %{exit_lbl}')

        self._emit(f'{body_lbl}:')
        # Load element
        dp = self._fresh("dp")
        dp2 = self._fresh("dp2")
        elem = self._fresh("elem")
        self._emit_indent(f'{dp} = getelementptr inbounds {crate_type}, {crate_type}* {it_val}, i32 0, i32 1')
        self._emit_indent(f'{dp2} = load {inner_ll}*, {inner_ll}** {dp}')
        self._emit_indent(f'{elem} = getelementptr inbounds {inner_ll}, {inner_ll}* {dp2}, i64 {cur_idx}')
        elem_val = self._fresh("elem_val")
        self._emit_indent(f'{elem_val} = load {inner_ll}, {inner_ll}* {elem}')

        # Store loop var
        var_alloca = f"%{node.var}.addr"
        self._emit_indent(f'{var_alloca} = alloca {inner_ll}')
        self._emit_indent(f'store {inner_ll} {elem_val}, {inner_ll}* {var_alloca}')
        self._locals[node.var] = (var_alloca, inner_ll)

        self._emit_block(node.body)

        # Increment index
        next_idx = self._fresh("next_idx")
        self._emit_indent(f'{next_idx} = add i64 {cur_idx}, 1')
        self._emit_indent(f'store i64 {next_idx}, i64* {idx_alloca}')
        self._emit_indent(f'br label %{cond_lbl}')
        self._emit(f'{exit_lbl}:')
        self._loop_exit_blocks.pop()
        del self._locals[node.var]

    def _emit_block(self, stmts: List[Node]):
        saved = dict(self._locals)
        for s in stmts:
            self._emit_stmt(s)
        # Restore scope (remove block-local vars)
        self._locals = saved

    # ------------------------------------------------------------------
    # Expression emission — returns the register holding the value
    # ------------------------------------------------------------------

    def _emit_expr(self, node: Node) -> str:
        if isinstance(node, IntLit):
            return str(node.value)

        if isinstance(node, DecimalLit):
            return str(node.value)

        if isinstance(node, SwitchLit):
            return "1" if node.value else "0"

        if isinstance(node, EmptyLit):
            return "null"

        if isinstance(node, TextLit):
            const_name = self._strings.get(node.value)
            length = len(node.value.encode('utf-8')) + 1
            reg = self._fresh("str")
            self._emit_indent(
                f'{reg} = getelementptr inbounds [{length} x i8], [{length} x i8]* {const_name}, i64 0, i64 0'
            )
            return reg

        if isinstance(node, Ident):
            entry = self._locals.get(node.name)
            if entry:
                alloca, ll = entry
                reg = self._fresh("load")
                self._emit_indent(f'{reg} = load {ll}, {ll}* {alloca}')
                return reg
            # Global constant
            t = getattr(node, 'rtype', None)
            if t:
                ll = llvm_type(t)
                reg = self._fresh("gload")
                self._emit_indent(f'{reg} = load {ll}, {ll}* @{node.name}')
                return reg
            return f"@{node.name}"

        if isinstance(node, BinOp):
            return self._emit_binop(node)

        if isinstance(node, UnaryOp):
            return self._emit_unary(node)

        if isinstance(node, SmeltExpr):
            return self._emit_smelt(node)

        if isinstance(node, WireExpr):
            entry = self._locals.get(node.target)
            if entry:
                alloca, _ = entry
                return alloca
            return f"@{node.target}"

        if isinstance(node, UnwrapExpr):
            ptr = self._emit_expr(node.target)
            t = getattr(node.target, 'rtype', None)
            if t and t.name == "wire":
                inner_ll = llvm_type(t.inner)
                reg = self._fresh("deref")
                self._emit_indent(f'{reg} = load {inner_ll}, {inner_ll}* {ptr}')
                return reg
            return ptr

        if isinstance(node, FieldExpr):
            return self._emit_field_load(node)

        if isinstance(node, IndexExpr):
            return self._emit_index(node)

        if isinstance(node, CallExpr):
            return self._emit_call(node)

        if isinstance(node, BuildExpr):
            return self._emit_build(node)

        if isinstance(node, CrateLit):
            return self._emit_crate_lit(node)

        return "null"

    def _emit_binop(self, node: BinOp) -> str:
        left  = self._emit_expr(node.left)
        right = self._emit_expr(node.right)
        lt    = getattr(node.left,  'rtype', T_UNIT)
        rt    = getattr(node.right, 'rtype', T_UNIT)
        op    = node.op
        reg   = self._fresh("op")

        is_float = (lt.name == "decimal" or rt.name == "decimal")
        is_text  = (lt.name == "text"    or rt.name == "text")

        if op == "+":
            if is_text:
                # String concat via malloc + strcpy + strcat
                len1 = self._fresh("len1")
                len2 = self._fresh("len2")
                total_raw = self._fresh("total_raw")
                total = self._fresh("total")
                buf   = self._fresh("buf")
                self._emit_indent(f'{len1} = call i64 @strlen(i8* {left})')
                self._emit_indent(f'{len2} = call i64 @strlen(i8* {right})')
                self._emit_indent(f'{total_raw} = add i64 {len1}, {len2}')
                self._emit_indent(f'{total} = add i64 {total_raw}, 1')
                self._emit_indent(f'{buf} = call i8* @malloc(i64 {total})')
                self._emit_indent(f'call i8* @strcpy(i8* {buf}, i8* {left})')
                self._emit_indent(f'call i8* @strcat(i8* {buf}, i8* {right})')
                return buf
            if is_float:
                self._emit_indent(f'{reg} = fadd double {left}, {right}')
            else:
                self._emit_indent(f'{reg} = add i64 {left}, {right}')
            return reg

        arith_map = {
            "-":  ("fsub", "sub"),
            "*":  ("fmul", "mul"),
            "/":  ("fdiv", "sdiv"),
            "%":  ("frem", "srem"),
        }
        if op in arith_map:
            fi, ii = arith_map[op]
            if is_float:
                self._emit_indent(f'{reg} = {fi} double {left}, {right}')
            else:
                self._emit_indent(f'{reg} = {ii} i64 {left}, {right}')
            return reg

        cmp_map = {
            "==": ("fcmp oeq", "icmp eq"),
            "!=": ("fcmp one", "icmp ne"),
            "<":  ("fcmp olt", "icmp slt"),
            ">":  ("fcmp ogt", "icmp sgt"),
            "<=": ("fcmp ole", "icmp sle"),
            ">=": ("fcmp oge", "icmp sge"),
        }
        if op in cmp_map:
            fc, ic = cmp_map[op]
            if is_float:
                self._emit_indent(f'{reg} = {fc} double {left}, {right}')
            elif lt.name == "text":
                cmp_res = self._fresh("strcmp_res")
                self._emit_indent(f'{cmp_res} = call i32 @strcmp(i8* {left}, i8* {right})')
                if op == "==":
                    self._emit_indent(f'{reg} = icmp eq i32 {cmp_res}, 0')
                elif op == "!=":
                    self._emit_indent(f'{reg} = icmp ne i32 {cmp_res}, 0')
                else:
                    self._emit_indent(f'{reg} = icmp slt i32 {cmp_res}, 0')
            else:
                self._emit_indent(f'{reg} = {ic} i64 {left}, {right}')
            return reg

        if op == "and":
            self._emit_indent(f'{reg} = and i1 {left}, {right}')
            return reg
        if op == "or":
            self._emit_indent(f'{reg} = or i1 {left}, {right}')
            return reg

        return "0"

    def _emit_unary(self, node: UnaryOp) -> str:
        val = self._emit_expr(node.operand)
        t   = getattr(node.operand, 'rtype', T_UNIT)
        reg = self._fresh("unary")
        if node.op == "-":
            if t.name == "decimal":
                self._emit_indent(f'{reg} = fneg double {val}')
            else:
                self._emit_indent(f'{reg} = sub i64 0, {val}')
        elif node.op == "flip":
            self._emit_indent(f'{reg} = xor i1 {val}, 1')
        return reg

    def _emit_smelt(self, node: SmeltExpr) -> str:
        src   = self._emit_expr(node.value)
        src_t = getattr(node.value, 'rtype', T_UNIT)
        dst_t = node.target_type
        reg   = self._fresh("smelt")

        # unit -> decimal
        if src_t.name == "unit" and dst_t.name == "decimal":
            self._emit_indent(f'{reg} = sitofp i64 {src} to double')
        # decimal -> unit
        elif src_t.name == "decimal" and dst_t.name == "unit":
            self._emit_indent(f'{reg} = fptosi double {src} to i64')
        # * -> switch
        elif dst_t.name == "switch":
            if src_t.name == "unit":
                self._emit_indent(f'{reg} = icmp ne i64 {src}, 0')
            else:
                self._emit_indent(f'{reg} = icmp ne i64 0, 0  ; smelt to switch')
        # * -> text: call sprintf helper
        elif dst_t.name == "text":
            buf = self._fresh("smelt_buf")
            self._emit_indent(f'{buf} = call i8* @malloc(i64 64)')
            if src_t.name == "unit":
                fmt_gep = self._fresh("fmtgep")
                fmt_const = self._get_str_const("%lld")
                flen = len("%lld") + 1
                self._emit_indent(
                    f'{fmt_gep} = getelementptr inbounds [{flen} x i8], [{flen} x i8]* {fmt_const}, i64 0, i64 0'
                )
                self._emit_indent(f'call i32 (i8*, i8*, ...) @sprintf(i8* {buf}, i8* {fmt_gep}, i64 {src})')
            elif src_t.name == "decimal":
                fmt_gep = self._fresh("fmtgep")
                fmt_const = self._get_str_const("%f")
                flen = len("%f") + 1
                self._emit_indent(
                    f'{fmt_gep} = getelementptr inbounds [{flen} x i8], [{flen} x i8]* {fmt_const}, i64 0, i64 0'
                )
                self._emit_indent(f'call i32 (i8*, i8*, ...) @sprintf(i8* {buf}, i8* {fmt_gep}, double {src})')
            else:
                self._emit_indent(f'call i8* @strcpy(i8* {buf}, i8* {src})')
            reg = buf
        # text -> unit
        elif src_t.name == "text" and dst_t.name == "unit":
            self._emit_indent(f'declare i64 @atoll(i8*)')
            self._emit_indent(f'{reg} = call i64 @atoll(i8* {src})')
        # text -> decimal
        elif src_t.name == "text" and dst_t.name == "decimal":
            self._emit_indent(f'declare double @atof(i8*)')
            self._emit_indent(f'{reg} = call double @atof(i8* {src})')
        else:
            reg = src  # identity

        return reg

    def _emit_field_load(self, node: FieldExpr) -> str:
        obj_t = getattr(node.target, 'rtype', None)
        if obj_t and obj_t.name in self._blueprints:
            bp = self._blueprints[obj_t.name]
            for i, f in enumerate(bp.fields):
                if f.name == node.field:
                    obj_ptr = self._emit_expr(node.target)
                    field_ll = llvm_type(f.type_node)
                    ptr = self._fresh("fptr")
                    val = self._fresh("fval")
                    self._emit_indent(
                        f'{ptr} = getelementptr inbounds %{obj_t.name}, %{obj_t.name}* {obj_ptr}, i32 0, i32 {i}'
                    )
                    self._emit_indent(f'{val} = load {field_ll}, {field_ll}* {ptr}')
                    return val
        # stdlib field (status etc.) — return opaque
        return "null"

    def _emit_index(self, node: IndexExpr) -> str:
        target = self._emit_expr(node.target)
        index  = self._emit_expr(node.index)
        t = getattr(node.target, 'rtype', None)
        if t and t.name == "crate" and t.inner:
            inner_ll   = llvm_type(t.inner)
            crate_type = f"%Crate_{inner_ll.replace('*','p').replace(' ','_')}"
            dp   = self._fresh("dp")
            dp2  = self._fresh("dp2")
            ep   = self._fresh("ep")
            val  = self._fresh("elem")
            self._emit_indent(
                f'{dp} = getelementptr inbounds {crate_type}, {crate_type}* {target}, i32 0, i32 1'
            )
            self._emit_indent(f'{dp2} = load {inner_ll}*, {inner_ll}** {dp}')
            self._emit_indent(f'{ep} = getelementptr inbounds {inner_ll}, {inner_ll}* {dp2}, i64 {index}')
            self._emit_indent(f'{val} = load {inner_ll}, {inner_ll}* {ep}')
            return val
        return "null"

    def _emit_call(self, node: CallExpr) -> str:
        # Method call
        if isinstance(node.callee, FieldExpr):
            return self._emit_method_call(node)

        # Plain recipe call
        if isinstance(node.callee, Ident):
            name = node.callee.name
            args = [(self._emit_expr(a), getattr(a, 'rtype', T_UNIT)) for a in node.args]
            arg_str = ", ".join(f"{llvm_type(t)} {v}" for v, t in args)
            ret_t = getattr(node, 'rtype', T_EMPTY)
            if ret_t.name == "empty":
                self._emit_indent(f'call void @{name}({arg_str})')
                return "null"
            reg = self._fresh("call")
            self._emit_indent(f'{reg} = call {llvm_type(ret_t)} @{name}({arg_str})')
            return reg

        return "null"

    def _emit_method_call(self, node: CallExpr) -> str:
        fe = node.callee
        obj_name = fe.target.name if isinstance(fe.target, Ident) else "?"
        method   = fe.field
        args     = [(self._emit_expr(a), getattr(a, 'rtype', T_UNIT)) for a in node.args]
        ret_t    = getattr(node, 'rtype', T_EMPTY)
        reg      = self._fresh("mcall")

        # Stdlib mappings
        stdlib = {
            ("panel",    "prompt"):  ("rubble_panel_prompt",  "i8*",  ["i8*"]),
            ("panel",    "grab"):    ("rubble_panel_grab",    "i8*",  []),
            ("machinery","rest"):    ("usleep",               "i32",  ["i32"]),
            ("machinery","ram"):     ("rubble_machinery_ram", "i64",  []),
            ("machinery","halt"):    ("exit",                 "void", ["i32"]),
            ("cabinet",  "open"):    ("rubble_cabinet_open",  "i64",  ["i8*"]),
            ("cabinet",  "create"):  ("rubble_cabinet_create","i64",  ["i8*"]),
            ("cable",    "connect"): ("rubble_cable_connect", "i64",  ["i8*", "i64"]),
        }
        key = (obj_name, method)
        if key in stdlib:
            fn, ret_ll, _ = stdlib[key]
            arg_str = ", ".join(f"{llvm_type(t)} {v}" for v, t in args)
            if ret_ll == "void":
                self._emit_indent(f'call void @{fn}({arg_str})')
                return "null"
            self._emit_indent(f'{reg} = call {ret_ll} @{fn}({arg_str})')
            return reg

        # Crate built-ins
        obj_t = getattr(fe.target, 'rtype', None)
        if obj_t and obj_t.name == "crate":
            return self._emit_crate_builtin(fe.target, obj_t, method, args, reg)

        # Text built-ins
        if obj_t and obj_t.name == "text":
            return self._emit_text_builtin(fe.target, method, args, reg)

        # Generic file/connection read/write/close/status
        obj_val = self._emit_expr(fe.target)
        if method == "read":
            self._emit_indent(f'{reg} = call i8* @rubble_line_read(i64 {obj_val})')
            return reg
        if method in ("write", "close"):
            arg_str = ", ".join(f"{llvm_type(t)} {v}" for v, t in args)
            self._emit_indent(f'call void @rubble_{method}(i64 {obj_val}, {arg_str})')
            return "null"
        if method == "status":
            self._emit_indent(f'{reg} = call i1 @rubble_status(i64 {obj_val})')
            return reg
        if method == "length":
            if obj_t and obj_t.name == "text":
                str_val = self._emit_expr(fe.target)
                self._emit_indent(f'{reg} = call i64 @strlen(i8* {str_val})')
                return reg

        return "null"

    def _emit_crate_builtin(self, target, obj_t, method, args, reg):
        # Simplified: just return null for now (full crate runtime needs stdlib C)
        return "null"

    def _emit_text_builtin(self, target, method, args, reg):
        obj_val = self._emit_expr(target)
        if method == "length":
            self._emit_indent(f'{reg} = call i64 @strlen(i8* {obj_val})')
            return reg
        return "null"

    def _emit_build(self, node: BuildExpr) -> str:
        bp = self._blueprints.get(node.blueprint)
        if not bp:
            return "null"
        ptr = self._fresh("bp")
        struct_ll = llvm_type(TypeNode(node.blueprint))
        # Alloca on stack (could malloc for heap — stack for v1)
        self._emit_indent(f'{ptr} = alloca %{node.blueprint}')
        for fname, fexpr in node.kwargs:
            for i, f in enumerate(bp.fields):
                if f.name == fname:
                    fval = self._emit_expr(fexpr)
                    fll  = llvm_type(f.type_node)
                    fptr = self._fresh("fptr")
                    self._emit_indent(
                        f'{fptr} = getelementptr inbounds %{node.blueprint}, %{node.blueprint}* {ptr}, i32 0, i32 {i}'
                    )
                    self._emit_indent(f'store {fll} {fval}, {fll}* {fptr}')
        return ptr

    def _emit_crate_lit(self, node: CrateLit) -> str:
        if not node.elements:
            return "null"
        t = getattr(node, 'rtype', None)
        if not t or t.name != "crate":
            return "null"
        inner_ll   = llvm_type(t.inner) if t.inner else "i8"
        crate_name = f"Crate_{inner_ll.replace('*','p').replace(' ','_')}"
        self._crate_types.add((crate_name, inner_ll))
        n = len(node.elements)
        # malloc array
        arr_ptr = self._fresh("arr")
        total   = self._fresh("arr_size")
        self._emit_indent(f'{total} = mul i64 {n}, 8')  # assume 8 bytes per element
        self._emit_indent(f'{arr_ptr} = call i8* @malloc(i64 {total})')
        typed_ptr = self._fresh("arr_typed")
        self._emit_indent(f'{typed_ptr} = bitcast i8* {arr_ptr} to {inner_ll}*')
        for i, elem in enumerate(node.elements):
            ev  = self._emit_expr(elem)
            ep  = self._fresh("ep")
            self._emit_indent(f'{ep} = getelementptr inbounds {inner_ll}, {inner_ll}* {typed_ptr}, i64 {i}')
            self._emit_indent(f'store {inner_ll} {ev}, {inner_ll}* {ep}')
        # Alloc crate struct
        crate_ptr = self._fresh("crate")
        self._emit_indent(f'{crate_ptr} = alloca %{crate_name}')
        lp = self._fresh("lp")
        dp = self._fresh("dp")
        self._emit_indent(f'{lp} = getelementptr inbounds %{crate_name}, %{crate_name}* {crate_ptr}, i32 0, i32 0')
        self._emit_indent(f'store i64 {n}, i64* {lp}')
        self._emit_indent(f'{dp} = getelementptr inbounds %{crate_name}, %{crate_name}* {crate_ptr}, i32 0, i32 1')
        self._emit_indent(f'store {inner_ll}* {typed_ptr}, {inner_ll}** {dp}')
        return crate_ptr

    def _emit_crate_type_defs(self) -> List[str]:
        """Return crate struct type definitions that were needed."""
        lines = []
        for name, inner_ll in self._crate_types:
            lines.append(f'%{name} = type {{ i64, {inner_ll}* }}')
        return lines
