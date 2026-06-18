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
from .type_checker import (
    STDLIB_METHODS,
    T_DECIMAL,
    T_EMPTY,
    T_SWITCH,
    T_TEXT,
    T_UNIT,
    TypeNode,
    types_equal,
)

# ---------------------------------------------------------------------------
# LLVM type mapping
# ---------------------------------------------------------------------------


def llvm_type(t: TypeNode) -> str:
    if t.name == "unit":
        return "i64"
    if t.name == "i8":
        return "i8"
    if t.name == "i16":
        return "i16"
    if t.name == "i32":
        return "i32"
    if t.name == "u8":
        return "i8"
    if t.name == "u16":
        return "i16"
    if t.name == "u32":
        return "i32"
    if t.name == "u64":
        return "i64"
    if t.name == "decimal":
        return "double"
    if t.name == "text":
        return "i8*"
    if t.name == "switch":
        return "i1"
    if t.name == "empty":
        return "void"
    if t.name == "fn":
        return "i8*"  # Function pointer - simplified for now
    if t.name == "wire":
        return llvm_type(t.inner) + "*"
    if t.name == "crate":
        inner = llvm_type(t.inner) if t.inner else "i8"
        return f"%Crate_{inner.replace('*', 'p').replace(' ', '_')}*"
    # Blueprint / custom struct
    return f"%{t.name}*"


def llvm_type_for_alloca(t: TypeNode) -> str:
    """Type used in alloca — structs without the pointer."""
    if t.name == "crate":
        inner = llvm_type(t.inner) if t.inner else "i8"
        return f"%Crate_{inner.replace('*', 'p').replace(' ', '_')}"
    if t.name not in ("unit", "i8", "i16", "i32", "u8", "u16", "u32", "u64", "decimal", "text", "switch", "empty", "wire", "fn"):
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
            length = len(value.encode("utf-8")) + 1  # +1 for null terminator
            lines.append(
                f'{name} = private unnamed_addr constant [{length} x i8] c"{escaped}\\00", align 1'
            )
        return lines

    def _escape(self, s: str) -> str:
        result = []
        for ch in s:
            if ch == '"':
                result.append("\\22")
            elif ch == "\\":
                result.append("\\5C")
            elif ch == "\n":
                result.append("\\0A")
            elif ch == "\t":
                result.append("\\09")
            elif ch == "\r":
                result.append("\\0D")
            elif ch == "\0":
                result.append("\\00")
            else:
                result.append(ch)
        return "".join(result)


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
        self._enums: Dict[str, EnumDecl] = {}
        self._crate_types: set = set()
        self._recipes_map: Dict[str, "RecipeDecl"] = {}  # name -> decl for default args

        # Local variable map per function: name -> (alloca_reg, llvm_type_str)
        self._locals: Dict[str, Tuple[str, str]] = {}
        self._globals_code: List[str] = []

        self._in_function = False
        self._current_func_name = ""
        self._loop_exit_blocks: List[str] = []
        self._loop_cond_blocks: List[str] = []
        self._loop_label_exits: Dict[str, str] = {}
        self._loop_label_conds: Dict[str, str] = {}

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
        self._collect_enums(program)
        self._collect_recipes(program)
        self._emit_prelude()
        self._emit_stdlib_decls()
        self._emit_blueprint_types()
        self._emit_enum_types()
        self._emit_program(program)
        self._emit_postlude()
        return "\n".join(self._lines)

    # ------------------------------------------------------------------
    # Prelude / postlude
    # ------------------------------------------------------------------

    def _emit_prelude(self):
        self._emit(f"; Rubble compiled output — {self.filename}")
        self._emit(
            'target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"'
        )
        self._emit("")

    def _emit_postlude(self):
        if self._strings._pool:
            self._emit("")
            for line in self._strings.emit():
                self._emit(line)

    def _emit_stdlib_decls(self):
        self._emit("; ---- External C stdlib declarations ----")
        # I/O
        self._emit("declare i32 @printf(i8*, ...)")
        self._emit("declare i32 @puts(i8*)")
        self._emit("declare i8* @fgets(i8*, i32, i8*)")
        self._emit("declare i32 @fflush(i8*)")
        # Memory
        self._emit("declare i8* @malloc(i64)")
        self._emit("declare void @free(i8*)")
        self._emit("declare i8* @memcpy(i8*, i8*, i64)")
        self._emit("declare i8* @realloc(i8*, i64)")
        # String
        self._emit("declare i64 @strlen(i8*)")
        self._emit("declare i8* @strcpy(i8*, i8*)")
        self._emit("declare i8* @strcat(i8*, i8*)")
        self._emit("declare i32 @strcmp(i8*, i8*)")
        self._emit("declare i8* @strdup(i8*)")
        self._emit("declare i8* @strstr(i8*, i8*)")
        self._emit("declare i8* @strchr(i8*, i32)")
        # Process
        self._emit("declare void @exit(i32) noreturn")
        self._emit("declare void @abort() noreturn")
        # Rubble stdlib stubs (implemented in rubble_stdlib.c)
        self._emit("declare i8* @rubble_panel_prompt(i8*)")
        self._emit("declare i8* @rubble_panel_grab()")
        self._emit("declare i32 @rubble_machinery_rest(i64)")
        self._emit("declare i64 @rubble_machinery_ram()")
        self._emit("declare i64 @rubble_machinery_time()")
        self._emit("declare i8* @rubble_machinery_env(i8*)")
        self._emit("declare i8** @rubble_machinery_args(i64*)")
        self._emit("declare i64 @rubble_cabinet_open(i8*)")
        self._emit("declare i64 @rubble_cabinet_create(i8*)")
        self._emit("declare i8* @rubble_cabinet_read(i8*)")
        self._emit("declare void @rubble_cabinet_write(i8*, i8*)")
        self._emit("declare i1  @rubble_cabinet_exists(i8*)")
        self._emit("declare void @rubble_cabinet_delete(i8*)")
        self._emit("declare i64 @rubble_cable_connect(i8*, i64)")
        self._emit("declare i8* @rubble_line_read(i64)")
        self._emit("")
        # Text helpers
        self._emit("declare i8* @rubble_text_upper(i8*)")
        self._emit("declare i8* @rubble_text_lower(i8*)")
        self._emit("declare i8* @rubble_text_trim(i8*)")
        self._emit("declare i8* @rubble_text_replace(i8*, i8*, i8*)")
        self._emit("declare i8* @rubble_text_slice(i8*, i64, i64)")
        self._emit("declare i64 @rubble_text_index(i8*, i8*)")
        self._emit("declare i8** @rubble_text_split(i8*, i8*, i64*)")
        self._emit("")
        # Crate helpers
        self._emit("declare void @rubble_crate_sort_i64(i8*, i64)")
        self._emit("declare void @rubble_crate_reverse(i8*, i64, i64)")
        self._emit("declare i8* @rubble_crate_join(i8**, i64, i8*)")
        self._emit("")
        # rand
        self._emit("declare i64  @rubble_rand_int(i64, i64)")
        self._emit("declare double @rubble_rand_decimal()")
        self._emit("declare void @rubble_rand_seed(i64)")
        self._emit("")
        # time module
        self._emit("declare i64  @rubble_time_now()")
        self._emit("declare i8*  @rubble_time_format(i64, i8*)")
        self._emit("")
        # json module
        self._emit("declare i8*  @rubble_json_encode(i8*)")
        self._emit("declare i8*  @rubble_json_decode(i8*)")
        self._emit("declare i8*  @rubble_json_get(i8*, i8*)")
        self._emit("declare i8*  @rubble_json_set(i8*, i8*, i8*)")
        self._emit("")
        # canvas — windowed drawing surface
        self._emit("declare i64 @rubble_canvas_open(i8*, i64, i64)")
        self._emit("declare void @rubble_canvas_clear(i64, i64, i64, i64)")
        self._emit(
            "declare void @rubble_canvas_rect(i64, i64, i64, i64, i64, i64, i64, i64)"
        )
        self._emit(
            "declare void @rubble_canvas_circle(i64, i64, i64, i64, i64, i64, i64)"
        )
        self._emit(
            "declare void @rubble_canvas_line(i64, i64, i64, i64, i64, i64, i64, i64)"
        )
        self._emit(
            "declare void @rubble_canvas_text(i64, i64, i64, i8*, i64, i64, i64)"
        )
        self._emit("declare void @rubble_canvas_show(i64)")
        self._emit("declare i64  @rubble_canvas_poll(i64)")
        self._emit("declare void @rubble_canvas_close(i64)")
        self._emit("declare i64  @rubble_canvas_key(i64, i64)")
        self._emit("declare i1   @rubble_canvas_key_just_pressed(i64, i64)")
        self._emit("declare i64  @rubble_canvas_mouse_x(i64)")
        self._emit("declare i64  @rubble_canvas_mouse_y(i64)")
        self._emit("declare i64  @rubble_canvas_mouse_btn(i64, i64)")
        self._emit("declare i64  @rubble_canvas_mouse_scroll(i64)")
        self._emit("declare void @rubble_canvas_fill_mode(i64, i64)")
        self._emit("declare void @rubble_canvas_set_title(i64, i8*)")
        self._emit("declare void @rubble_canvas_resize(i64, i64, i64)")
        self._emit("declare void @rubble_canvas_fullscreen(i64)")
        self._emit("declare double @rubble_canvas_delta_time(i64)")
        self._emit("declare i64  @rubble_canvas_image_load(i8*)")
        self._emit("declare void @rubble_canvas_image_draw(i64, i64, i64, i64)")
        self._emit("declare void @rubble_canvas_font_size(i64, i64)")
        self._emit("")
        # sound
        self._emit("declare i64  @rubble_sound_load(i8*)")
        self._emit("declare void @rubble_sound_play(i64)")
        self._emit("declare void @rubble_sound_stop(i64)")
        self._emit("")
        # thread
        self._emit("declare i64  @rubble_thread_spawn(i8*)")
        self._emit("declare void @rubble_thread_join(i64)")
        self._emit("")
        # http
        self._emit("declare i8* @rubble_http_get(i8*)")
        self._emit("")
        # db
        self._emit("declare i64  @rubble_db_open(i8*)")
        self._emit("declare i32  @rubble_db_execute(i64, i8*)")
        self._emit("declare i8* @rubble_db_query(i64, i8*)")
        self._emit("declare void @rubble_db_close(i64)")
        self._emit("")
        # math stdlib
        self._emit("declare double @rubble_math_sqrt(double)")
        self._emit("declare double @rubble_math_cbrt(double)")
        self._emit("declare double @rubble_math_pow(double, double)")
        self._emit("declare double @rubble_math_abs(double)")
        self._emit("declare double @rubble_math_floor(double)")
        self._emit("declare double @rubble_math_ceil(double)")
        self._emit("declare double @rubble_math_round(double)")
        self._emit("declare double @rubble_math_sin(double)")
        self._emit("declare double @rubble_math_cos(double)")
        self._emit("declare double @rubble_math_tan(double)")
        self._emit("declare double @rubble_math_asin(double)")
        self._emit("declare double @rubble_math_acos(double)")
        self._emit("declare double @rubble_math_atan(double)")
        self._emit("declare double @rubble_math_atan2(double, double)")
        self._emit("declare double @rubble_math_log(double)")
        self._emit("declare double @rubble_math_log2(double)")
        self._emit("declare double @rubble_math_log10(double)")
        self._emit("declare double @rubble_math_exp(double)")
        self._emit("declare double @rubble_math_min(double, double)")
        self._emit("declare double @rubble_math_max(double, double)")
        self._emit("declare double @rubble_math_pi()")
        self._emit("declare double @rubble_math_e()")
        self._emit("declare double @rubble_math_inf()")
        self._emit("declare double @rubble_math_clamp(double, double, double)")
        self._emit("declare double @rubble_math_lerp(double, double, double)")
        self._emit("")
        # String conversion helpers
        self._emit("declare i64 @atoll(i8*)")
        self._emit("declare double @atof(i8*)")
        self._emit("")

    def _collect_blueprints(self, program: Program):
        for s in program.stmts:
            if isinstance(s, BlueprintDecl):
                self._blueprints[s.name] = s

    def _collect_enums(self, program: Program):
        for s in program.stmts:
            if isinstance(s, EnumDecl):
                self._enums[s.name] = s

    def _collect_recipes(self, program: Program):
        for s in program.stmts:
            if isinstance(s, RecipeDecl):
                self._recipes_map[s.name] = s

    def _emit_blueprint_types(self):
        if not self._blueprints:
            return
        self._emit("; ---- Blueprint struct types ----")
        for name, bp in self._blueprints.items():
            fields_ll = ", ".join(f"{llvm_type(f.type_node)} %f{i}" for i, f in enumerate(bp.fields))
            self._emit(f"%{name} = type {{ {fields_ll} }}")

    def _emit_enum_types(self):
        if not self._enums:
            return
        self._emit("; ---- Enum types ----")
        for name, enum_decl in self._enums.items():
            # Enums are represented as i64 with variant indices
            self._emit(f"; {name} enum with {len(enum_decl.variants)} variants")
            for i, variant in enumerate(enum_decl.variants):
                self._emit(f"; {name}.{variant} = {i}")
        self._emit("")

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

        for s in global_slots:
            self._emit_global_const(s)

        recipes = [s for s in other_stmts if isinstance(s, RecipeDecl)]
        non_recipes = [
            s
            for s in other_stmts
            if not isinstance(s, RecipeDecl)
            and not isinstance(s, BlueprintDecl)
            and not isinstance(s, GatherStmt)
        ]

        for r in recipes:
            self._emit_recipe(r)

        if non_recipes:
            self._emit("")
            self._emit("define i32 @main() {")
            self._emit("entry:")
            self._in_function = True
            self._current_func_name = "main"
            self._locals = {}
            for s in non_recipes:
                self._emit_stmt(s)
            self._emit_indent("ret i32 0")
            self._emit("}")
            self._in_function = False

    def _emit_global_const(self, node: SlotDecl):
        typ = getattr(node, "inferred_type", None)
        if typ is None:
            return
        ll = llvm_type(typ)
        if typ.name == "text" and isinstance(node.value, TextLit):
            str_name = self._strings.get(node.value.value)
            length = len(node.value.value.encode("utf-8")) + 1
            self._emit(
                f"@{node.name} = private global i8* getelementptr inbounds ([{length} x i8], [{length} x i8]* {str_name}, i64 0, i64 0)"
            )
        elif typ.name == "unit" and isinstance(node.value, IntLit):
            self._emit(f"@{node.name} = private constant i64 {node.value.value}")
        elif typ.name == "decimal" and isinstance(node.value, DecimalLit):
            self._emit(f"@{node.name} = private constant double {node.value.value}")
        elif typ.name == "switch" and isinstance(node.value, SwitchLit):
            self._emit(
                f"@{node.name} = private constant i1 {1 if node.value.value else 0}"
            )

    # ------------------------------------------------------------------
    # Recipe → LLVM function
    # ------------------------------------------------------------------

    def _emit_recipe(self, node: RecipeDecl):
        self._emit("")

        # ── Multi-return: synthesise a blueprint struct ──────────────────
        if node.return_types:
            ret_bp_name = f"__ret_{node.name}"
            # Register the synthetic blueprint so field access works
            from .ast_nodes import BlueprintDecl
            from .ast_nodes import Param as BParam

            synth_fields = [BParam(f"v{i}", t) for i, t in enumerate(node.return_types)]
            synth_bp = BlueprintDecl(ret_bp_name, synth_fields, node.loc)
            self._blueprints[ret_bp_name] = synth_bp
            # Emit struct type
            fields_ll = ", ".join(llvm_type(t) for t in node.return_types)
            self._emit(f"%{ret_bp_name} = type {{ {fields_ll} }}")
            ret_ll = f"%{ret_bp_name}*"
        else:
            ret_ll = (
                llvm_type(node.return_type)
                if node.return_type.name != "empty"
                else "void"
            )

        # ── Build LLVM param list (skip variadics — handled inside body) ─
        non_variadic = [p for p in node.params if not p.variadic]
        variadic_p = next((p for p in node.params if p.variadic), None)

        params_ll = ", ".join(
            f"{llvm_type(p.type_node)} %{p.name}" for p in non_variadic
        )
        if variadic_p:
            params_ll = (params_ll + ", ...") if params_ll else "..."

        self._emit(f"define {ret_ll} @{node.name}({params_ll}) {{")
        self._emit("entry:")
        self._in_function = True
        self._current_func_name = node.name
        old_locals = self._locals
        self._locals = {}

        for p in non_variadic:
            ll = llvm_type(p.type_node)
            alloca = f"%{p.name}.addr"
            self._emit_indent(f"{alloca} = alloca {ll}")
            if p.default is not None:
                # Default value: caller passes -1/null/0 as sentinel → use default
                # Simpler approach: always store param value; defaults are handled at call site
                self._emit_indent(f"store {ll} %{p.name}, {ll}* {alloca}")
            else:
                self._emit_indent(f"store {ll} %{p.name}, {ll}* {alloca}")
            self._locals[p.name] = (alloca, ll)

        for s in node.body:
            self._emit_stmt(s)

        if node.return_types:
            # Heap-allocate the return struct as sentinel (real yield handles it)
            sz = self._fresh("retsz")
            self._emit_indent(f"{sz} = mul i64 1, {len(node.return_types) * 8}")
            raw = self._fresh("retraw")
            self._emit_indent(f"{raw} = call i8* @malloc(i64 {sz})")
            ptr = self._fresh("retptr")
            self._emit_indent(f"{ptr} = bitcast i8* {raw} to %{f'__ret_{node.name}'}*")
            self._emit_indent(f"ret {ret_ll} {ptr}")
        elif ret_ll == "void":
            self._emit_indent("ret void")
        else:
            self._emit_indent(f"ret {ret_ll} {self._zero_value(node.return_type)}")

        self._emit("}")
        self._locals = old_locals
        self._in_function = False

    def _zero_value(self, t: TypeNode) -> str:
        if t.name == "unit":
            return "0"
        if t.name == "decimal":
            return "0.0"
        if t.name == "switch":
            return "0"
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
        elif isinstance(node, SkipStmt):
            self._emit_skip(node)
        elif isinstance(node, WreckStmt):
            self._emit_wreck(node)
        elif isinstance(node, ScrapStmt):
            self._emit_scrap(node)
        elif isinstance(node, IfStmt):
            self._emit_if(node)
        elif isinstance(node, MatchStmt):
            self._emit_match(node)
        elif isinstance(node, LoopStmt):
            self._emit_loop(node)
        elif isinstance(node, ForEachStmt):
            self._emit_foreach(node)
        elif isinstance(node, ExprStmt):
            self._emit_expr(node.expr)
        elif isinstance(node, (RecipeDecl, BlueprintDecl, EnumDecl, ConstDecl, Decorator, ModuleDecl, MethodDecl, TypeAliasDecl, UnionType, IntersectionType, NullableType, TupleType, RecordLit, TuplePattern, ArrayType, MapType, SetType, OptionalChainExpr, NullCoalesceExpr, GatherStmt)):
            pass  # handled elsewhere

    def _emit_slot(self, node: SlotDecl):
        typ = getattr(node, "inferred_type", None)
        if typ is None:
            return
        ll = llvm_type(typ)
        alloca = f"%{node.name}.addr"
        self._emit_indent(f"{alloca} = alloca {ll}")
        val_reg = self._emit_expr(node.value)
        if val_reg:
            self._emit_indent(f"store {ll} {val_reg}, {ll}* {alloca}")
        self._locals[node.name] = (alloca, ll)

    def _emit_assign(self, node: AssignStmt):
        rhs = self._emit_expr(node.value)
        if isinstance(node.target, Ident):
            entry = self._locals.get(node.target.name)
            if entry:
                alloca, ll = entry
                self._emit_indent(f"store {ll} {rhs}, {ll}* {alloca}")
        elif isinstance(node.target, UnwrapExpr):
            ptr = self._emit_expr(node.target.target)
            t = getattr(node.target.target, "rtype", None)
            if t and t.name == "wire":
                inner_ll = llvm_type(t.inner)
                self._emit_indent(f"store {inner_ll} {rhs}, {inner_ll}* {ptr}")
        elif isinstance(node.target, FieldExpr):
            self._emit_field_store(node.target, rhs)
        elif isinstance(node.target, IndexExpr):
            self._emit_index_store(node.target, rhs)

    def _emit_index_store(self, ie: IndexExpr, val: str):
        target = self._emit_expr(ie.target)
        index = self._emit_expr(ie.index)
        t = getattr(ie.target, "rtype", None)
        if t and t.name == "crate" and t.inner:
            inner_ll = llvm_type(t.inner)
            crate_type = f"%Crate_{inner_ll.replace('*', 'p').replace(' ', '_')}"
            dp = self._fresh("dp")
            dp2 = self._fresh("dp2")
            ep = self._fresh("ep")
            self._emit_indent(
                f"{dp} = getelementptr inbounds {crate_type}, {crate_type}* {target}, i32 0, i32 1"
            )
            self._emit_indent(f"{dp2} = load {inner_ll}*, {inner_ll}** {dp}")
            self._emit_indent(
                f"{ep} = getelementptr inbounds {inner_ll}, {inner_ll}* {dp2}, i64 {index}"
            )
            self._emit_indent(f"store {inner_ll} {val}, {inner_ll}* {ep}")

    def _emit_field_store(self, field_expr: FieldExpr, val_reg: str):
        obj_t = getattr(field_expr.target, "rtype", None)
        if obj_t and obj_t.name in self._blueprints:
            bp = self._blueprints[obj_t.name]
            for i, f in enumerate(bp.fields):
                if f.name == field_expr.field:
                    obj_ptr = self._emit_expr(field_expr.target)
                    field_ptr = self._fresh("fptr")
                    field_ll = llvm_type(f.type_node)
                    self._emit_indent(
                        f"{field_ptr} = getelementptr inbounds %{obj_t.name}, %{obj_t.name}* {obj_ptr}, i32 0, i32 {i}"
                    )
                    self._emit_indent(
                        f"store {field_ll} {val_reg}, {field_ll}* {field_ptr}"
                    )
                    return

    def _emit_write(self, node: WriteStmt):
        val = self._emit_expr(node.value)
        t = getattr(node.value, "rtype", T_TEXT)
        self._emit_write_value(val, t)

    def _emit_write_value(self, val_reg: str, t: TypeNode):
        if t.name == "text":
            self._emit_indent(f"call i32 @puts(i8* {val_reg})")
        elif t.name == "unit":
            fmt_str = "%lld\n"
            fmt_name = self._strings.get(fmt_str)
            flen = len(fmt_str) + 1
            fmt_gep = self._fresh("fmtgep")
            self._emit_indent(
                f"{fmt_gep} = getelementptr inbounds [{flen} x i8], [{flen} x i8]* {fmt_name}, i64 0, i64 0"
            )
            self._emit_indent(
                f"call i32 (i8*, ...) @printf(i8* {fmt_gep}, i64 {val_reg})"
            )
        elif t.name == "decimal":
            fmt_str = "%g\n"
            fmt_name = self._strings.get(fmt_str)
            flen = len(fmt_str) + 1
            fmt_gep = self._fresh("fmtgep")
            self._emit_indent(
                f"{fmt_gep} = getelementptr inbounds [{flen} x i8], [{flen} x i8]* {fmt_name}, i64 0, i64 0"
            )
            self._emit_indent(
                f"call i32 (i8*, ...) @printf(i8* {fmt_gep}, double {val_reg})"
            )
        elif t.name == "switch":
            true_ptr = self._fresh("trueptr")
            false_ptr = self._fresh("falseptr")
            sel = self._fresh("boolstr")
            self._emit_indent(
                f"{true_ptr} = getelementptr inbounds [5 x i8], [5 x i8]* {self._get_str_const('true')}, i64 0, i64 0"
            )
            self._emit_indent(
                f"{false_ptr} = getelementptr inbounds [6 x i8], [6 x i8]* {self._get_str_const('false')}, i64 0, i64 0"
            )
            self._emit_indent(
                f"{sel} = select i1 {val_reg}, i8* {true_ptr}, i8* {false_ptr}"
            )
            self._emit_indent(f"call i32 @puts(i8* {sel})")
        else:
            self._emit_indent(f"call i32 @puts(i8* {val_reg})")

    def _get_str_const(self, s: str) -> str:
        return self._strings.get(s)

    def _emit_yield(self, node: YieldStmt):
        val = self._emit_expr(node.value)
        t = getattr(node.value, "rtype", T_EMPTY)
        if t.name == "empty":
            self._emit_indent("ret void")
        else:
            self._emit_indent(f"ret {llvm_type(t)} {val}")
        dead = self._label("after_yield")
        self._emit(f"{dead}:")

    def _emit_jam(self, node: JamStmt):
        # Labeled break: search loop stack for matching label
        if node.label and node.label in self._loop_label_exits:
            self._emit_indent(f"br label %{self._loop_label_exits[node.label]}")
        elif self._loop_exit_blocks:
            self._emit_indent(f"br label %{self._loop_exit_blocks[-1]}")
        dead = self._label("after_jam")
        self._emit(f"{dead}:")

    def _emit_skip(self, node: SkipStmt):
        # Labeled continue: search loop stack for matching label
        if node.label and node.label in self._loop_label_conds:
            self._emit_indent(f"br label %{self._loop_label_conds[node.label]}")
        elif self._loop_cond_blocks:
            self._emit_indent(f"br label %{self._loop_cond_blocks[-1]}")
        dead = self._label("after_skip")
        self._emit(f"{dead}:")

    def _emit_wreck(self, node: WreckStmt):
        msg = self._emit_expr(node.message)
        self._emit_indent(f"call i32 @puts(i8* {msg})")
        self._emit_indent("call void @exit(i32 1)")
        self._emit_indent("unreachable")
        dead = self._label("after_wreck")
        self._emit(f"{dead}:")

    def _emit_scrap(self, node: ScrapStmt):
        entry = self._locals.get(node.name)
        if entry:
            alloca, ll = entry
            if ll in ("i8*",) or ll.endswith("*"):
                val = self._fresh("scrap")
                self._emit_indent(f"{val} = load {ll}, {ll}* {alloca}")
                cast = self._fresh("scrapcast")
                self._emit_indent(f"{cast} = bitcast {ll} {val} to i8*")
                self._emit_indent(f"call void @free(i8* {cast})")
            del self._locals[node.name]

    def _emit_if(self, node: IfStmt):
        cond = self._emit_expr(node.condition)
        then_lbl = self._label("then")
        merge_lbl = self._label("merge")

        if node.elif_clauses or node.else_block:
            next_lbl = self._label("elif_or_else")
        else:
            next_lbl = merge_lbl

        self._emit_indent(f"br i1 {cond}, label %{then_lbl}, label %{next_lbl}")
        self._emit(f"{then_lbl}:")
        self._emit_block(node.then_block)
        self._emit_indent(f"br label %{merge_lbl}")

        for idx, (ec, eb) in enumerate(node.elif_clauses):
            self._emit(f"{next_lbl}:")
            ec_val = self._emit_expr(ec)
            elif_body = self._label("elif_body")
            if idx < len(node.elif_clauses) - 1:
                next_lbl = self._label("elif_or_else")
            else:
                next_lbl = self._label("else") if node.else_block else merge_lbl
            self._emit_indent(f"br i1 {ec_val}, label %{elif_body}, label %{next_lbl}")
            self._emit(f"{elif_body}:")
            self._emit_block(eb)
            self._emit_indent(f"br label %{merge_lbl}")

        if node.else_block:
            self._emit(f"{next_lbl}:")
            self._emit_block(node.else_block)
            self._emit_indent(f"br label %{merge_lbl}")

        self._emit(f"{merge_lbl}:")

    def _emit_match(self, node: MatchStmt):
        """Emit match as a chain of icmp/fcmp branches."""
        val_reg = self._emit_expr(node.value)
        val_t = getattr(node.value, "rtype", T_UNIT)
        merge_lbl = self._label("match_merge")

        next_lbl = None
        for idx, (pat, body) in enumerate(node.arms):
            arm_lbl = self._label("match_arm")
            next_lbl = self._label("match_next")

            # Check if pattern is a destructuring pattern
            if isinstance(pat, DestructPattern):
                # For destructuring patterns, we always match (type checking ensures compatibility)
                # Extract field values and bind them to variables
                for field_name, default_value in pat.bindings:
                    # Get field index from blueprint
                    if pat.type_name in self._blueprints:
                        bp = self._blueprints[pat.type_name]
                        field_idx = None
                        for i, f in enumerate(bp.fields):
                            if f.name == field_name:
                                field_idx = i
                                break
                        if field_idx is not None:
                            # Extract field value
                            field_reg = self._fresh("field")
                            self._emit_indent(f"{field_reg} = getelementptr inbounds %{pat.type_name}, %{pat.type_name}* {val_reg}, i32 0, i32 {field_idx}")
                            field_val = self._fresh("field_val")
                            field_type = llvm_type(bp.fields[field_idx].type_node)
                            self._emit_indent(f"{field_val} = load {field_type}, {field_type}* {field_reg}")
                            # Bind to variable name in locals
                            self._locals[field_name] = (f"%{field_name}.addr", field_type)
                            self._emit_indent(f"%{field_name}.addr = alloca {field_type}")
                            self._emit_indent(f"store {field_type} {field_val}, {field_type}* %{field_name}.addr")
                # Always branch to arm for destructuring patterns
                self._emit_indent(f"br label %{arm_lbl}")
            else:
                pat_reg = self._emit_expr(pat)
                # Compare value with pattern
                cmp_reg = self._fresh("match_cmp")
                if val_t.name == "decimal":
                    self._emit_indent(f"{cmp_reg} = fcmp oeq double {val_reg}, {pat_reg}")
                elif val_t.name == "text":
                    strcmp_res = self._fresh("strcmp")
                    self._emit_indent(
                        f"{strcmp_res} = call i32 @strcmp(i8* {val_reg}, i8* {pat_reg})"
                    )
                    self._emit_indent(f"{cmp_reg} = icmp eq i32 {strcmp_res}, 0")
                else:
                    self._emit_indent(f"{cmp_reg} = icmp eq i64 {val_reg}, {pat_reg}")

                self._emit_indent(f"br i1 {cmp_reg}, label %{arm_lbl}, label %{next_lbl}")

            self._emit(f"{arm_lbl}:")
            self._emit_block(body)
            self._emit_indent(f"br label %{merge_lbl}")
            if not isinstance(pat, DestructPattern):
                self._emit(f"{next_lbl}:")

        if node.default_block:
            self._emit_block(node.default_block)
        self._emit_indent(f"br label %{merge_lbl}")
        self._emit(f"{merge_lbl}:")

    def _emit_loop(self, node: LoopStmt):
        cond_lbl = self._label("loop_cond")
        body_lbl = self._label("loop_body")
        exit_lbl = self._label("loop_exit")

        self._loop_exit_blocks.append(exit_lbl)
        self._loop_cond_blocks.append(cond_lbl)
        if node.label:
            self._loop_label_exits[node.label] = exit_lbl
            self._loop_label_conds[node.label] = cond_lbl
        self._emit_indent(f"br label %{cond_lbl}")
        self._emit(f"{cond_lbl}:")
        cond = self._emit_expr(node.condition)
        self._emit_indent(f"br i1 {cond}, label %{body_lbl}, label %{exit_lbl}")
        self._emit(f"{body_lbl}:")
        self._emit_block(node.body)
        self._emit_indent(f"br label %{cond_lbl}")
        self._emit(f"{exit_lbl}:")
        self._loop_exit_blocks.pop()
        self._loop_cond_blocks.pop()
        if node.label:
            self._loop_label_exits.pop(node.label, None)
            self._loop_label_conds.pop(node.label, None)

    def _emit_foreach(self, node: ForEachStmt):
        # Check if this is a range loop (RangeExpr)
        from .ast_nodes import RangeExpr
        if isinstance(node.iterable, RangeExpr):
            self._emit_range_loop(node)
            return

        it_val = self._emit_expr(node.iterable)
        it_t = getattr(node.iterable, "rtype", None)
        idx_alloca = self._fresh("for_idx")
        self._emit_indent(f"{idx_alloca} = alloca i64")
        self._emit_indent(f"store i64 0, i64* {idx_alloca}")

        inner_ll = "i8"
        if it_t and it_t.name == "crate" and it_t.inner:
            inner_ll = llvm_type(it_t.inner)

        cond_lbl = self._label("for_cond")
        body_lbl = self._label("for_body")
        exit_lbl = self._label("for_exit")
        self._loop_exit_blocks.append(exit_lbl)
        self._loop_cond_blocks.append(cond_lbl)
        if node.label:
            self._loop_label_exits[node.label] = exit_lbl
            self._loop_label_conds[node.label] = cond_lbl

        crate_type = f"%Crate_{inner_ll.replace('*', 'p').replace(' ', '_')}"
        self._emit_indent(f"br label %{cond_lbl}")
        self._emit(f"{cond_lbl}:")
        cur_idx = self._fresh("cur_idx")
        self._emit_indent(f"{cur_idx} = load i64, i64* {idx_alloca}")

        lp = self._fresh("lp")
        lv = self._fresh("lv")
        self._emit_indent(
            f"{lp} = getelementptr inbounds {crate_type}, {crate_type}* {it_val}, i32 0, i32 0"
        )
        self._emit_indent(f"{lv} = load i64, i64* {lp}")
        cmp = self._fresh("for_cmp")
        self._emit_indent(f"{cmp} = icmp slt i64 {cur_idx}, {lv}")
        self._emit_indent(f"br i1 {cmp}, label %{body_lbl}, label %{exit_lbl}")

        self._emit(f"{body_lbl}:")
        dp = self._fresh("dp")
        dp2 = self._fresh("dp2")
        elem = self._fresh("elem")
        self._emit_indent(
            f"{dp} = getelementptr inbounds {crate_type}, {crate_type}* {it_val}, i32 0, i32 1"
        )
        self._emit_indent(f"{dp2} = load {inner_ll}*, {inner_ll}** {dp}")
        self._emit_indent(
            f"{elem} = getelementptr inbounds {inner_ll}, {inner_ll}* {dp2}, i64 {cur_idx}"
        )
        elem_val = self._fresh("elem_val")
        self._emit_indent(f"{elem_val} = load {inner_ll}, {inner_ll}* {elem}")

        var_alloca = f"%{node.var}.addr"
        self._emit_indent(f"{var_alloca} = alloca {inner_ll}")
        self._emit_indent(f"store {inner_ll} {elem_val}, {inner_ll}* {var_alloca}")
        self._locals[node.var] = (var_alloca, inner_ll)

        self._emit_block(node.body)

        next_idx = self._fresh("next_idx")
        self._emit_indent(f"{next_idx} = add i64 {cur_idx}, 1")
        self._emit_indent(f"store i64 {next_idx}, i64* {idx_alloca}")
        self._emit_indent(f"br label %{cond_lbl}")
        self._emit(f"{exit_lbl}:")
        self._loop_exit_blocks.pop()
        self._loop_cond_blocks.pop()
        if node.label:
            self._loop_label_exits.pop(node.label, None)
            self._loop_label_conds.pop(node.label, None)
        if node.var in self._locals:
            del self._locals[node.var]

    def _emit_range_loop(self, node: ForEachStmt):
        """Emit code for range loop: for i in start..end"""
        from .ast_nodes import RangeExpr
        range_expr = node.iterable
        start_val = self._emit_expr(range_expr.start)
        end_val = self._emit_expr(range_expr.end)

        # Allocate counter variable
        counter_alloca = self._fresh("range_counter")
        self._emit_indent(f"{counter_alloca} = alloca i64")
        self._emit_indent(f"store i64 {start_val}, i64* {counter_alloca}")

        # Set up loop labels
        cond_lbl = self._label("range_cond")
        body_lbl = self._label("range_body")
        exit_lbl = self._label("range_exit")
        self._loop_exit_blocks.append(exit_lbl)
        self._loop_cond_blocks.append(cond_lbl)
        if node.label:
            self._loop_label_exits[node.label] = exit_lbl
            self._loop_label_conds[node.label] = cond_lbl

        # Jump to condition
        self._emit_indent(f"br label %{cond_lbl}")

        # Condition block
        self._emit(f"{cond_lbl}:")
        cur_counter = self._fresh("cur_counter")
        self._emit_indent(f"{cur_counter} = load i64, i64* {counter_alloca}")
        cmp = self._fresh("range_cmp")
        self._emit_indent(f"{cmp} = icmp slt i64 {cur_counter}, {end_val}")
        self._emit_indent(f"br i1 {cmp}, label %{body_lbl}, label %{exit_lbl}")

        # Body block
        self._emit(f"{body_lbl}:")
        # Store current counter value in loop variable
        var_alloca = f"%{node.var}.addr"
        self._emit_indent(f"{var_alloca} = alloca i64")
        self._emit_indent(f"store i64 {cur_counter}, i64* {var_alloca}")
        self._locals[node.var] = (var_alloca, "i64")

        self._emit_block(node.body)

        # Increment counter and loop back
        next_counter = self._fresh("next_counter")
        self._emit_indent(f"{next_counter} = add i64 {cur_counter}, 1")
        self._emit_indent(f"store i64 {next_counter}, i64* {counter_alloca}")
        self._emit_indent(f"br label %{cond_lbl}")

        # Exit block
        self._emit(f"{exit_lbl}:")
        self._loop_exit_blocks.pop()
        self._loop_cond_blocks.pop()
        if node.label:
            self._loop_label_exits.pop(node.label, None)
            self._loop_label_conds.pop(node.label, None)
        if node.var in self._locals:
            del self._locals[node.var]

    def _emit_block(self, stmts: List[Node]):
        saved = dict(self._locals)
        for s in stmts:
            self._emit_stmt(s)
        self._locals = saved

    # ------------------------------------------------------------------
    # Expression emission — returns the register holding the value
    # ------------------------------------------------------------------

    def _emit_expr(self, node: Node) -> str:
        if isinstance(node, IntLit):
            return str(node.value)

        if isinstance(node, DecimalLit):
            # LLVM needs hex float or full precision for doubles
            return repr(node.value)

        if isinstance(node, SwitchLit):
            return "1" if node.value else "0"

        if isinstance(node, EmptyLit):
            return "null"

        if isinstance(node, TextLit):
            const_name = self._strings.get(node.value)
            length = len(node.value.encode("utf-8")) + 1
            reg = self._fresh("str")
            self._emit_indent(
                f"{reg} = getelementptr inbounds [{length} x i8], [{length} x i8]* {const_name}, i64 0, i64 0"
            )
            return reg

        if isinstance(node, InterpTextLit):
            return self._emit_interp_text(node)

        if isinstance(node, SwitchStmt):
            return self._emit_switch(node)

        if isinstance(node, MatchExpr):
            return self._emit_match_expr(node)

        if isinstance(node, Ident):
            entry = self._locals.get(node.name)
            if entry:
                alloca, ll = entry
                reg = self._fresh("load")
                self._emit_indent(f"{reg} = load {ll}, {ll}* {alloca}")
                return reg
            t = getattr(node, "rtype", None)
            if t:
                ll = llvm_type(t)
                reg = self._fresh("gload")
                self._emit_indent(f"{reg} = load {ll}, {ll}* @{node.name}")
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
            t = getattr(node.target, "rtype", None)
            if t and t.name == "wire":
                inner_ll = llvm_type(t.inner)
                reg = self._fresh("deref")
                self._emit_indent(f"{reg} = load {inner_ll}, {inner_ll}* {ptr}")
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

        if isinstance(node, LambdaExpr):
            return self._emit_lambda(node)

        if isinstance(node, SpreadExpr):
            # Spread operator: ...value
            # For now, just emit the value (spread semantics would be context-dependent)
            return self._emit_expr(node.value)

        if isinstance(node, NamedArg):
            # Named argument: name: value
            # For now, just emit the value (named argument semantics would require parameter matching)
            return self._emit_expr(node.value)

        return "null"

    def _emit_lambda(self, node: LambdaExpr) -> str:
        """Emit a lambda as a function and return a function pointer."""
        # Generate a unique name for the lambda function
        lambda_name = self._fresh("lambda")
        # Save current function state
        saved_locals = dict(self._locals)
        saved_ret = self._current_return_type

        # Build parameter list for LLVM
        param_types = []
        param_names = []
        for param in node.params:
            param_type = param.type_node
            param_ll = llvm_type(param_type)
            param_types.append(param_ll)
            param_names.append(param.name)

        # Emit function definition
        ret_type = "i64"  # Default to unit (i64) for now
        self._emit(f"define {ret_type} @{lambda_name}({', '.join(f'{t} %n' for t in param_types)}) {{")

        # Set up locals for parameters
        self._locals = {}
        for i, param in enumerate(node.params):
            param_alloca = f"%{param.name}.addr"
            param_ll = llvm_type(param.type_node)
            self._emit_indent(f"{param_alloca} = alloca {param_ll}")
            self._emit_indent(f"store {param_ll} %n, {param_ll}* {param_alloca}")
            self._locals[param.name] = (param_alloca, param_ll)

        # Emit lambda body
        self._emit_block(node.body)

        # Default return if no explicit yield
        self._emit_indent(f"ret {ret_type} 0")

        self._emit("}")

        # Restore function state
        self._locals = saved_locals
        self._current_return_type = saved_ret

        # Return function pointer as i8*
        ptr_reg = self._fresh("fn_ptr")
        self._emit_indent(f"{ptr_reg} = bitcast {ret_type} ({', '.join(param_types)})* @{lambda_name} to i8*")
        return ptr_reg

    def _emit_interp_text(self, node: InterpTextLit) -> str:
        """Compile f"hello {name}!" into a series of string concatenations."""
        # Build a list of i8* registers, one per part, then concat all
        parts_regs = []  # list of (reg, is_heap) — is_heap tracks if we should free
        for part in node.parts:
            if isinstance(part, str):
                const_name = self._strings.get(part)
                length = len(part.encode("utf-8")) + 1
                reg = self._fresh("istr")
                self._emit_indent(
                    f"{reg} = getelementptr inbounds [{length} x i8], [{length} x i8]* {const_name}, i64 0, i64 0"
                )
                parts_regs.append(reg)
            else:
                # Expression — convert to text
                val = self._emit_expr(part)
                t = getattr(part, "rtype", T_TEXT)
                if t.name == "text":
                    parts_regs.append(val)
                else:
                    # smelt to text
                    buf = self._fresh("ibuf")
                    self._emit_indent(f"{buf} = call i8* @malloc(i64 64)")
                    if t.name == "unit":
                        fmt_const = self._get_str_const("%lld")
                        flen = len("%lld") + 1
                        fmt_gep = self._fresh("ifmtgep")
                        self._emit_indent(
                            f"{fmt_gep} = getelementptr inbounds [{flen} x i8], [{flen} x i8]* {fmt_const}, i64 0, i64 0"
                        )
                        self._emit_indent(
                            f"call i32 (i8*, i8*, ...) @sprintf(i8* {buf}, i8* {fmt_gep}, i64 {val})"
                        )
                    elif t.name == "decimal":
                        fmt_const = self._get_str_const("%g")
                        flen = len("%g") + 1
                        fmt_gep = self._fresh("ifmtgep")
                        self._emit_indent(
                            f"{fmt_gep} = getelementptr inbounds [{flen} x i8], [{flen} x i8]* {fmt_const}, i64 0, i64 0"
                        )
                        self._emit_indent(
                            f"call i32 (i8*, i8*, ...) @sprintf(i8* {buf}, i8* {fmt_gep}, double {val})"
                        )
                    elif t.name == "switch":
                        true_ptr = self._fresh("itp")
                        false_ptr = self._fresh("ifp")
                        sel_s = self._fresh("isel")
                        self._emit_indent(
                            f"{true_ptr} = getelementptr inbounds [5 x i8], [5 x i8]* {self._get_str_const('true')}, i64 0, i64 0"
                        )
                        self._emit_indent(
                            f"{false_ptr} = getelementptr inbounds [6 x i8], [6 x i8]* {self._get_str_const('false')}, i64 0, i64 0"
                        )
                        self._emit_indent(
                            f"{sel_s} = select i1 {val}, i8* {true_ptr}, i8* {false_ptr}"
                        )
                        self._emit_indent(f"call i8* @strcpy(i8* {buf}, i8* {sel_s})")
                    else:
                        self._emit_indent(f"call i8* @strcpy(i8* {buf}, i8* {val})")
                    parts_regs.append(buf)

        if not parts_regs:
            const_name = self._strings.get("")
            reg = self._fresh("empty_istr")
            self._emit_indent(
                f"{reg} = getelementptr inbounds [1 x i8], [1 x i8]* {const_name}, i64 0, i64 0"
            )
            return reg

        if len(parts_regs) == 1:
            return parts_regs[0]

        # Compute total length and concatenate
        acc = parts_regs[0]
        for other in parts_regs[1:]:
            len1 = self._fresh("ilen1")
            len2 = self._fresh("ilen2")
            tot = self._fresh("itot")
            tot2 = self._fresh("itot2")
            newbuf = self._fresh("icatbuf")
            self._emit_indent(f"{len1} = call i64 @strlen(i8* {acc})")
            self._emit_indent(f"{len2} = call i64 @strlen(i8* {other})")
            self._emit_indent(f"{tot}  = add i64 {len1}, {len2}")
            self._emit_indent(f"{tot2} = add i64 {tot}, 1")
            self._emit_indent(f"{newbuf} = call i8* @malloc(i64 {tot2})")
            self._emit_indent(f"call i8* @strcpy(i8* {newbuf}, i8* {acc})")
            self._emit_indent(f"call i8* @strcat(i8* {newbuf}, i8* {other})")
            acc = newbuf

        return acc

    def _emit_binop(self, node: BinOp) -> str:
        left = self._emit_expr(node.left)
        right = self._emit_expr(node.right)
        lt = getattr(node.left, "rtype", T_UNIT)
        rt = getattr(node.right, "rtype", T_UNIT)
        op = node.op
        reg = self._fresh("op")

        is_float = lt.name == "decimal" or rt.name == "decimal"
        is_text = lt.name == "text" or rt.name == "text"

        if op == "+":
            if is_text:
                len1 = self._fresh("len1")
                len2 = self._fresh("len2")
                total_raw = self._fresh("total_raw")
                total = self._fresh("total")
                buf = self._fresh("buf")
                self._emit_indent(f"{len1} = call i64 @strlen(i8* {left})")
                self._emit_indent(f"{len2} = call i64 @strlen(i8* {right})")
                self._emit_indent(f"{total_raw} = add i64 {len1}, {len2}")
                self._emit_indent(f"{total} = add i64 {total_raw}, 1")
                self._emit_indent(f"{buf} = call i8* @malloc(i64 {total})")
                self._emit_indent(f"call i8* @strcpy(i8* {buf}, i8* {left})")
                self._emit_indent(f"call i8* @strcat(i8* {buf}, i8* {right})")
                return buf
            if is_float:
                self._emit_indent(f"{reg} = fadd double {left}, {right}")
            else:
                self._emit_indent(f"{reg} = add i64 {left}, {right}")
            return reg

        arith_map = {
            "-": ("fsub", "sub"),
            "*": ("fmul", "mul"),
            "/": ("fdiv", "sdiv"),
            "%": ("frem", "srem"),
        }
        if op in arith_map:
            fi, ii = arith_map[op]
            if is_float:
                self._emit_indent(f"{reg} = {fi} double {left}, {right}")
            else:
                self._emit_indent(f"{reg} = {ii} i64 {left}, {right}")
            return reg

        cmp_map = {
            "==": ("fcmp oeq", "icmp eq"),
            "!=": ("fcmp one", "icmp ne"),
            "<": ("fcmp olt", "icmp slt"),
            ">": ("fcmp ogt", "icmp sgt"),
            "<=": ("fcmp ole", "icmp sle"),
            ">=": ("fcmp oge", "icmp sge"),
        }
        if op in cmp_map:
            fc, ic = cmp_map[op]
            if is_float:
                self._emit_indent(f"{reg} = {fc} double {left}, {right}")
            elif lt.name == "text":
                cmp_res = self._fresh("strcmp_res")
                self._emit_indent(
                    f"{cmp_res} = call i32 @strcmp(i8* {left}, i8* {right})"
                )
                if op == "==":
                    self._emit_indent(f"{reg} = icmp eq i32 {cmp_res}, 0")
                elif op == "!=":
                    self._emit_indent(f"{reg} = icmp ne i32 {cmp_res}, 0")
                else:
                    self._emit_indent(f"{reg} = icmp slt i32 {cmp_res}, 0")
            else:
                self._emit_indent(f"{reg} = {ic} i64 {left}, {right}")
            return reg

        if op == "and":
            self._emit_indent(f"{reg} = and i1 {left}, {right}")
            return reg
        if op == "or":
            self._emit_indent(f"{reg} = or i1 {left}, {right}")
            return reg

        return "0"

    def _emit_unary(self, node: UnaryOp) -> str:
        val = self._emit_expr(node.operand)
        t = getattr(node.operand, "rtype", T_UNIT)
        reg = self._fresh("unary")
        if node.op == "-":
            if t.name == "decimal":
                self._emit_indent(f"{reg} = fneg double {val}")
            else:
                self._emit_indent(f"{reg} = sub i64 0, {val}")
        elif node.op == "flip":
            self._emit_indent(f"{reg} = xor i1 {val}, 1")
        return reg

    def _emit_smelt(self, node: SmeltExpr) -> str:
        src = self._emit_expr(node.value)
        src_t = getattr(node.value, "rtype", T_UNIT)
        dst_t = node.target_type
        reg = self._fresh("smelt")

        if src_t.name == "unit" and dst_t.name == "decimal":
            self._emit_indent(f"{reg} = sitofp i64 {src} to double")
        elif src_t.name == "decimal" and dst_t.name == "unit":
            self._emit_indent(f"{reg} = fptosi double {src} to i64")
        elif dst_t.name == "switch":
            if src_t.name == "unit":
                self._emit_indent(f"{reg} = icmp ne i64 {src}, 0")
            else:
                self._emit_indent(f"{reg} = icmp ne i64 0, 0")
        elif dst_t.name == "text":
            buf = self._fresh("smelt_buf")
            self._emit_indent(f"{buf} = call i8* @malloc(i64 64)")
            if src_t.name == "unit":
                fmt_gep = self._fresh("fmtgep")
                fmt_const = self._get_str_const("%lld")
                flen = len("%lld") + 1
                self._emit_indent(
                    f"{fmt_gep} = getelementptr inbounds [{flen} x i8], [{flen} x i8]* {fmt_const}, i64 0, i64 0"
                )
                self._emit_indent(
                    f"call i32 (i8*, i8*, ...) @sprintf(i8* {buf}, i8* {fmt_gep}, i64 {src})"
                )
            elif src_t.name == "decimal":
                fmt_gep = self._fresh("fmtgep")
                fmt_const = self._get_str_const("%g")
                flen = len("%g") + 1
                self._emit_indent(
                    f"{fmt_gep} = getelementptr inbounds [{flen} x i8], [{flen} x i8]* {fmt_const}, i64 0, i64 0"
                )
                self._emit_indent(
                    f"call i32 (i8*, i8*, ...) @sprintf(i8* {buf}, i8* {fmt_gep}, double {src})"
                )
            else:
                self._emit_indent(f"call i8* @strcpy(i8* {buf}, i8* {src})")
            reg = buf
        elif src_t.name == "text" and dst_t.name == "unit":
            self._emit_indent(f"{reg} = call i64 @atoll(i8* {src})")
        elif src_t.name == "text" and dst_t.name == "decimal":
            self._emit_indent(f"{reg} = call double @atof(i8* {src})")
        else:
            reg = src

        return reg

    def _emit_field_load(self, node: FieldExpr) -> str:
        obj_t = getattr(node.target, "rtype", None)
        if obj_t and obj_t.name in self._blueprints:
            bp = self._blueprints[obj_t.name]
            for i, f in enumerate(bp.fields):
                if f.name == node.field:
                    obj_ptr = self._emit_expr(node.target)
                    field_ll = llvm_type(f.type_node)
                    ptr = self._fresh("fptr")
                    val = self._fresh("fval")
                    self._emit_indent(
                        f"{ptr} = getelementptr inbounds %{obj_t.name}, %{obj_t.name}* {obj_ptr}, i32 0, i32 {i}"
                    )
                    self._emit_indent(f"{val} = load {field_ll}, {field_ll}* {ptr}")
                    return val
        return "null"

    def _emit_index(self, node: IndexExpr) -> str:
        target = self._emit_expr(node.target)
        index = self._emit_expr(node.index)
        t = getattr(node.target, "rtype", None)
        if t and t.name == "crate" and t.inner:
            inner_ll = llvm_type(t.inner)
            crate_type = f"%Crate_{inner_ll.replace('*', 'p').replace(' ', '_')}"
            dp = self._fresh("dp")
            dp2 = self._fresh("dp2")
            ep = self._fresh("ep")
            val = self._fresh("elem")
            self._emit_indent(
                f"{dp} = getelementptr inbounds {crate_type}, {crate_type}* {target}, i32 0, i32 1"
            )
            self._emit_indent(f"{dp2} = load {inner_ll}*, {inner_ll}** {dp}")
            self._emit_indent(
                f"{ep} = getelementptr inbounds {inner_ll}, {inner_ll}* {dp2}, i64 {index}"
            )
            self._emit_indent(f"{val} = load {inner_ll}, {inner_ll}* {ep}")
            return val
        return "null"

    def _emit_call(self, node: CallExpr) -> str:
        if isinstance(node.callee, FieldExpr):
            return self._emit_method_call(node)

        if isinstance(node.callee, Ident):
            name = node.callee.name
            # Look up the recipe decl to fill in defaults
            from .type_checker import TypeChecker  # avoid circular; use stored decls

            # We access the recipe through the AST program scan (stored in _recipes_map)
            decl = self._recipes_map.get(name)
            if decl:
                # Build arg list, filling defaults for missing trailing args
                non_variadic_params = [p for p in decl.params if not p.variadic]
                variadic_p = next((p for p in decl.params if p.variadic), None)
                call_args = list(node.args)
                arg_regs = []
                for i, p in enumerate(non_variadic_params):
                    if i < len(call_args):
                        v = self._emit_expr(call_args[i])
                        t = getattr(call_args[i], "rtype", p.type_node)
                        arg_regs.append((v, t))
                    elif p.default is not None:
                        v = self._emit_expr(p.default)
                        arg_regs.append((v, p.type_node))
                    else:
                        arg_regs.append(("0", p.type_node))
                # Variadic args
                if variadic_p:
                    for extra in call_args[len(non_variadic_params) :]:
                        v = self._emit_expr(extra)
                        t = getattr(extra, "rtype", T_UNIT)
                        arg_regs.append((v, t))
                arg_str = ", ".join(f"{llvm_type(t)} {v}" for v, t in arg_regs)
                ret_t = getattr(node, "rtype", T_EMPTY)
                if decl.return_types:
                    # Returns a heap-allocated multi-return struct
                    bp_name = f"__ret_{name}"
                    reg = self._fresh("call")
                    self._emit_indent(f"{reg} = call %{bp_name}* @{name}({arg_str})")
                    return reg
                if ret_t.name == "empty":
                    self._emit_indent(f"call void @{name}({arg_str})")
                    return "null"
                reg = self._fresh("call")
                self._emit_indent(f"{reg} = call {llvm_type(ret_t)} @{name}({arg_str})")
                return reg
            # Fallback: no recipe decl info, emit as-is
            args = [
                (self._emit_expr(a), getattr(a, "rtype", T_UNIT)) for a in node.args
            ]
            arg_str = ", ".join(f"{llvm_type(t)} {v}" for v, t in args)
            ret_t = getattr(node, "rtype", T_EMPTY)
            if ret_t.name == "empty":
                self._emit_indent(f"call void @{name}({arg_str})")
                return "null"
            reg = self._fresh("call")
            self._emit_indent(f"{reg} = call {llvm_type(ret_t)} @{name}({arg_str})")
            return reg

        return "null"

    # Map of (module, method) -> (c_function_name, return_ll_type)
    # Built dynamically from STDLIB_METHODS to avoid duplication
    _STDLIB_FN: Dict[Tuple[str, str], Tuple[str, str]] = {
        ("panel", "prompt"): ("rubble_panel_prompt", "i8*"),
        ("panel", "grab"): ("rubble_panel_grab", "i8*"),
        ("cabinet", "open"): ("rubble_cabinet_open", "i64"),
        ("cabinet", "create"): ("rubble_cabinet_create", "i64"),
        ("cabinet", "read"): ("rubble_cabinet_read", "i8*"),
        ("cabinet", "write"): ("rubble_cabinet_write", "void"),
        ("cabinet", "exists"): ("rubble_cabinet_exists", "i1"),
        ("cabinet", "delete"): ("rubble_cabinet_delete", "void"),
        ("machinery", "rest"): ("rubble_machinery_rest", "void"),
        ("machinery", "ram"): ("rubble_machinery_ram", "i64"),
        ("machinery", "halt"): ("exit", "void"),
        ("machinery", "time"): ("rubble_machinery_time", "i64"),
        ("machinery", "env"): ("rubble_machinery_env", "i8*"),
        ("cable", "connect"): ("rubble_cable_connect", "i64"),
        ("canvas", "open"): ("rubble_canvas_open", "i64"),
        ("canvas", "clear"): ("rubble_canvas_clear", "void"),
        ("canvas", "rect"): ("rubble_canvas_rect", "void"),
        ("canvas", "circle"): ("rubble_canvas_circle", "void"),
        ("canvas", "line"): ("rubble_canvas_line", "void"),
        ("canvas", "text"): ("rubble_canvas_text", "void"),
        ("canvas", "show"): ("rubble_canvas_show", "void"),
        ("canvas", "poll"): ("rubble_canvas_poll", "i64"),
        ("canvas", "close"): ("rubble_canvas_close", "void"),
        ("canvas", "key"): ("rubble_canvas_key", "i64"),
        ("canvas", "key_just_pressed"): ("rubble_canvas_key_just_pressed", "i1"),
        ("canvas", "mouse_x"): ("rubble_canvas_mouse_x", "i64"),
        ("canvas", "mouse_y"): ("rubble_canvas_mouse_y", "i64"),
        ("canvas", "mouse_btn"): ("rubble_canvas_mouse_btn", "i64"),
        ("canvas", "mouse_scroll"): ("rubble_canvas_mouse_scroll", "i64"),
        ("canvas", "fill_mode"): ("rubble_canvas_fill_mode", "void"),
        ("canvas", "set_title"): ("rubble_canvas_set_title", "void"),
        ("canvas", "resize"): ("rubble_canvas_resize", "void"),
        ("canvas", "fullscreen"): ("rubble_canvas_fullscreen", "void"),
        ("canvas", "delta_time"): ("rubble_canvas_delta_time", "double"),
        ("canvas", "image_load"): ("rubble_canvas_image_load", "i64"),
        ("canvas", "image_draw"): ("rubble_canvas_image_draw", "void"),
        ("canvas", "font_size"): ("rubble_canvas_font_size", "void"),
        ("sound", "load"): ("rubble_sound_load", "i64"),
        ("sound", "play"): ("rubble_sound_play", "void"),
        ("sound", "stop"): ("rubble_sound_stop", "void"),
        ("thread", "join"): ("rubble_thread_join", "void"),
        ("http", "get"): ("rubble_http_get", "i8*"),
        ("db", "open"): ("rubble_db_open", "i64"),
        ("db", "execute"): ("rubble_db_execute", "i32"),
        ("db", "query"): ("rubble_db_query", "i8*"),
        ("db", "close"): ("rubble_db_close", "void"),
        ("rand", "int"): ("rubble_rand_int", "i64"),
        ("rand", "decimal"): ("rubble_rand_decimal", "double"),
        ("rand", "seed"): ("rubble_rand_seed", "void"),
        # time module
        ("time", "now"): ("rubble_time_now", "i64"),
        ("time", "format"): ("rubble_time_format", "i8*"),
        ("time", "sleep"): ("rubble_machinery_rest", "void"),
        # json module
        ("json", "encode"): ("rubble_json_encode", "i8*"),
        ("json", "decode"): ("rubble_json_decode", "i8*"),
        ("json", "get"): ("rubble_json_get", "i8*"),
        ("json", "set"): ("rubble_json_set", "i8*"),
        ("math", "sqrt"): ("rubble_math_sqrt", "double"),
        ("math", "cbrt"): ("rubble_math_cbrt", "double"),
        ("math", "pow"): ("rubble_math_pow", "double"),
        ("math", "abs"): ("rubble_math_abs", "double"),
        ("math", "floor"): ("rubble_math_floor", "double"),
        ("math", "ceil"): ("rubble_math_ceil", "double"),
        ("math", "round"): ("rubble_math_round", "double"),
        ("math", "sin"): ("rubble_math_sin", "double"),
        ("math", "cos"): ("rubble_math_cos", "double"),
        ("math", "tan"): ("rubble_math_tan", "double"),
        ("math", "asin"): ("rubble_math_asin", "double"),
        ("math", "acos"): ("rubble_math_acos", "double"),
        ("math", "atan"): ("rubble_math_atan", "double"),
        ("math", "atan2"): ("rubble_math_atan2", "double"),
        ("math", "log"): ("rubble_math_log", "double"),
        ("math", "log2"): ("rubble_math_log2", "double"),
        ("math", "log10"): ("rubble_math_log10", "double"),
        ("math", "exp"): ("rubble_math_exp", "double"),
        ("math", "min"): ("rubble_math_min", "double"),
        ("math", "max"): ("rubble_math_max", "double"),
        ("math", "pi"): ("rubble_math_pi", "double"),
        ("math", "e"): ("rubble_math_e", "double"),
        ("math", "inf"): ("rubble_math_inf", "double"),
        ("math", "clamp"): ("rubble_math_clamp", "double"),
        ("math", "lerp"): ("rubble_math_lerp", "double"),
    }

    def _emit_method_call(self, node: CallExpr) -> str:
        fe = node.callee
        method = fe.field
        ret_t = getattr(node, "rtype", T_EMPTY)
        reg = self._fresh("mcall")
        obj_name = fe.target.name if isinstance(fe.target, Ident) else None

        # Special: machinery.args() returns a crate — build it from argv
        if obj_name == "machinery" and method == "args":
            return self._emit_machinery_args(reg)

        # Special: thread.spawn takes a recipe name (function pointer)
        if obj_name == "thread" and method == "spawn":
            if node.args:
                fn_node = node.args[0]
                if isinstance(fn_node, Ident):
                    fn_ptr = self._fresh("fptr_cast")
                    self._emit_indent(
                        f"{fn_ptr} = bitcast void ()* @{fn_node.name} to i8*"
                    )
                    self._emit_indent(
                        f"{reg} = call i64 @rubble_thread_spawn(i8* {fn_ptr})"
                    )
                    return reg
            return "null"

        # Standard stdlib dispatch
        key = (obj_name, method)
        if key in self._STDLIB_FN:
            fn, ret_ll = self._STDLIB_FN[key]
            args = [
                (self._emit_expr(a), getattr(a, "rtype", T_UNIT)) for a in node.args
            ]
            arg_str = ", ".join(f"{llvm_type(t)} {v}" for v, t in args)
            if ret_ll == "void":
                self._emit_indent(f"call void @{fn}({arg_str})")
                return "null"
            self._emit_indent(f"{reg} = call {ret_ll} @{fn}({arg_str})")
            return reg

        # Crate built-ins
        obj_t = getattr(fe.target, "rtype", None)
        if obj_t and obj_t.name == "crate":
            args = [
                (self._emit_expr(a), getattr(a, "rtype", T_UNIT)) for a in node.args
            ]
            return self._emit_crate_builtin(fe.target, obj_t, method, args, reg)

        # Text built-ins
        if obj_t and obj_t.name == "text":
            args = [
                (self._emit_expr(a), getattr(a, "rtype", T_UNIT)) for a in node.args
            ]
            return self._emit_text_builtin(fe.target, method, args, reg)

        # cabinet.list — returns crate[text]
        if obj_name == "cabinet" and method == "list":
            return self._emit_cabinet_list(node, reg)

        # Generic file/connection methods
        obj_val = self._emit_expr(fe.target)
        args = [(self._emit_expr(a), getattr(a, "rtype", T_UNIT)) for a in node.args]
        if method == "read":
            self._emit_indent(f"{reg} = call i8* @rubble_line_read(i64 {obj_val})")
            return reg
        if method in ("write", "close"):
            arg_str = ", ".join(f"{llvm_type(t)} {v}" for v, t in args)
            self._emit_indent(f"call void @rubble_{method}(i64 {obj_val}, {arg_str})")
            return "null"
        if method == "status":
            self._emit_indent(f"{reg} = call i1 @rubble_status(i64 {obj_val})")
            return reg
        if method == "length":
            if obj_t and obj_t.name == "text":
                str_val = self._emit_expr(fe.target)
                self._emit_indent(f"{reg} = call i64 @strlen(i8* {str_val})")
                return reg

        return "null"

    def _emit_machinery_args(self, reg: str) -> str:
        """Build a crate[text] from rubble_machinery_args()."""
        inner_ll = "i8*"
        crate_name = "Crate_i8p"
        self._crate_types.add((crate_name, inner_ll))

        count_alloca = self._fresh("argc_a")
        self._emit_indent(f"{count_alloca} = alloca i64")
        self._emit_indent(f"store i64 0, i64* {count_alloca}")
        argv = self._fresh("argv")
        self._emit_indent(
            f"{argv} = call i8** @rubble_machinery_args(i64* {count_alloca})"
        )
        count = self._fresh("argc")
        self._emit_indent(f"{count} = load i64, i64* {count_alloca}")

        crate_ptr = self._fresh("args_crate")
        self._emit_indent(f"{crate_ptr} = alloca %{crate_name}")
        lp = self._fresh("lp")
        dp = self._fresh("dp")
        self._emit_indent(
            f"{lp} = getelementptr inbounds %{crate_name}, %{crate_name}* {crate_ptr}, i32 0, i32 0"
        )
        self._emit_indent(f"store i64 {count}, i64* {lp}")
        self._emit_indent(
            f"{dp} = getelementptr inbounds %{crate_name}, %{crate_name}* {crate_ptr}, i32 0, i32 1"
        )
        # Cast i8** to i8** (same type)
        self._emit_indent(f"store i8** {argv}, i8*** {dp}")
        return crate_ptr

    def _emit_cabinet_list(self, node: CallExpr, reg: str) -> str:
        """cabinet.list(path) is handled by rubble_stdlib.c returning a Crate_i8p."""
        # For now, return null — the C function rubble_cabinet_list fills it
        # The full implementation requires a C helper that returns a struct
        self._emit_indent(f"{reg} = alloca %Crate_i8p")
        inner_ll = "i8*"
        crate_name = "Crate_i8p"
        self._crate_types.add((crate_name, inner_ll))
        if node.args:
            path_val = self._emit_expr(node.args[0])
            self._emit_indent(
                f"call void @rubble_cabinet_list_fill(i8* {path_val}, %Crate_i8p* {reg})"
            )
        return reg

    def _emit_crate_builtin(self, target, obj_t, method, args, reg):
        obj_val = self._emit_expr(target)
        inner = obj_t.inner if obj_t.inner else T_UNIT
        inner_ll = llvm_type(inner)
        cname = f"Crate_{inner_ll.replace('*', 'p').replace(' ', '_')}"
        self._crate_types.add((cname, inner_ll))

        if method == "length":
            lp = self._fresh("lp")
            self._emit_indent(
                f"{lp} = getelementptr inbounds %{cname}, %{cname}* {obj_val}, i32 0, i32 0"
            )
            self._emit_indent(f"{reg} = load i64, i64* {lp}")
            return reg

        if method == "get":
            idx = args[0][0]
            dp = self._fresh("dp")
            dp2 = self._fresh("dp2")
            ep = self._fresh("ep")
            self._emit_indent(
                f"{dp} = getelementptr inbounds %{cname}, %{cname}* {obj_val}, i32 0, i32 1"
            )
            self._emit_indent(f"{dp2} = load {inner_ll}*, {inner_ll}** {dp}")
            self._emit_indent(
                f"{ep} = getelementptr inbounds {inner_ll}, {inner_ll}* {dp2}, i64 {idx}"
            )
            self._emit_indent(f"{reg} = load {inner_ll}, {inner_ll}* {ep}")
            return reg

        if method == "set":
            idx = args[0][0]
            val = args[1][0]
            dp = self._fresh("dp")
            dp2 = self._fresh("dp2")
            ep = self._fresh("ep")
            self._emit_indent(
                f"{dp} = getelementptr inbounds %{cname}, %{cname}* {obj_val}, i32 0, i32 1"
            )
            self._emit_indent(f"{dp2} = load {inner_ll}*, {inner_ll}** {dp}")
            self._emit_indent(
                f"{ep} = getelementptr inbounds {inner_ll}, {inner_ll}* {dp2}, i64 {idx}"
            )
            self._emit_indent(f"store {inner_ll} {val}, {inner_ll}* {ep}")
            return "null"

        if method == "push":
            val = args[0][0]
            lp = self._fresh("lp")
            old_len = self._fresh("old_len")
            new_len = self._fresh("new_len")
            old_dp = self._fresh("old_dp")
            old_ptr = self._fresh("old_ptr")
            sz = self._fresh("sz")
            raw = self._fresh("raw")
            new_ptr = self._fresh("new_ptr")
            ep = self._fresh("ep")
            old_raw = self._fresh("old_raw")
            old_sz = self._fresh("old_sz")
            self._emit_indent(
                f"{lp} = getelementptr inbounds %{cname}, %{cname}* {obj_val}, i32 0, i32 0"
            )
            self._emit_indent(f"{old_len} = load i64, i64* {lp}")
            self._emit_indent(f"{new_len} = add i64 {old_len}, 1")
            self._emit_indent(
                f"{old_dp} = getelementptr inbounds %{cname}, %{cname}* {obj_val}, i32 0, i32 1"
            )
            self._emit_indent(f"{old_ptr} = load {inner_ll}*, {inner_ll}** {old_dp}")
            self._emit_indent(f"{sz} = mul i64 {new_len}, 8")
            self._emit_indent(f"{raw} = call i8* @malloc(i64 {sz})")
            self._emit_indent(f"{new_ptr} = bitcast i8* {raw} to {inner_ll}*")
            self._emit_indent(f"{old_raw} = bitcast {inner_ll}* {old_ptr} to i8*")
            self._emit_indent(f"{old_sz} = mul i64 {old_len}, 8")
            self._emit_indent(
                f"call i8* @memcpy(i8* {raw}, i8* {old_raw}, i64 {old_sz})"
            )
            self._emit_indent(
                f"{ep} = getelementptr inbounds {inner_ll}, {inner_ll}* {new_ptr}, i64 {old_len}"
            )
            self._emit_indent(f"store {inner_ll} {val}, {inner_ll}* {ep}")
            self._emit_indent(f"store i64 {new_len}, i64* {lp}")
            self._emit_indent(f"store {inner_ll}* {new_ptr}, {inner_ll}** {old_dp}")
            return "null"

        if method == "pop":
            lp = self._fresh("lp")
            old_len = self._fresh("old_len")
            new_len = self._fresh("new_len")
            dp = self._fresh("dp")
            ptr = self._fresh("ptr")
            ep = self._fresh("ep")
            self._emit_indent(
                f"{lp} = getelementptr inbounds %{cname}, %{cname}* {obj_val}, i32 0, i32 0"
            )
            self._emit_indent(f"{old_len} = load i64, i64* {lp}")
            self._emit_indent(f"{new_len} = sub i64 {old_len}, 1")
            self._emit_indent(
                f"{dp} = getelementptr inbounds %{cname}, %{cname}* {obj_val}, i32 0, i32 1"
            )
            self._emit_indent(f"{ptr} = load {inner_ll}*, {inner_ll}** {dp}")
            self._emit_indent(
                f"{ep} = getelementptr inbounds {inner_ll}, {inner_ll}* {ptr}, i64 {new_len}"
            )
            self._emit_indent(f"{reg} = load {inner_ll}, {inner_ll}* {ep}")
            self._emit_indent(f"store i64 {new_len}, i64* {lp}")
            return reg

        if method == "contains":
            val = args[0][0]
            lp = self._fresh("lp")
            length = self._fresh("len")
            dp = self._fresh("dp")
            ptr = self._fresh("ptr")
            idx_a = self._fresh("idx_a")
            cond_lbl = self._label("cont_cond")
            body_lbl = self._label("cont_body")
            exit_lbl = self._label("cont_exit")
            found_lbl = self._label("cont_found")
            self._emit_indent(
                f"{lp} = getelementptr inbounds %{cname}, %{cname}* {obj_val}, i32 0, i32 0"
            )
            self._emit_indent(f"{length} = load i64, i64* {lp}")
            self._emit_indent(
                f"{dp} = getelementptr inbounds %{cname}, %{cname}* {obj_val}, i32 0, i32 1"
            )
            self._emit_indent(f"{ptr} = load {inner_ll}*, {inner_ll}** {dp}")
            self._emit_indent(f"{idx_a} = alloca i64")
            self._emit_indent(f"store i64 0, i64* {idx_a}")
            self._emit_indent(f"br label %{cond_lbl}")
            self._emit(f"{cond_lbl}:")
            cur = self._fresh("cur")
            cmp = self._fresh("cmp")
            self._emit_indent(f"{cur} = load i64, i64* {idx_a}")
            self._emit_indent(f"{cmp} = icmp slt i64 {cur}, {length}")
            self._emit_indent(f"br i1 {cmp}, label %{body_lbl}, label %{exit_lbl}")
            self._emit(f"{body_lbl}:")
            ep = self._fresh("ep")
            elem = self._fresh("elem")
            eq = self._fresh("eq")
            nxt = self._fresh("nxt")
            self._emit_indent(
                f"{ep} = getelementptr inbounds {inner_ll}, {inner_ll}* {ptr}, i64 {cur}"
            )
            self._emit_indent(f"{elem} = load {inner_ll}, {inner_ll}* {ep}")
            self._emit_indent(f"{eq} = icmp eq {inner_ll} {elem}, {val}")
            self._emit_indent(f"{nxt} = add i64 {cur}, 1")
            self._emit_indent(f"store i64 {nxt}, i64* {idx_a}")
            self._emit_indent(f"br i1 {eq}, label %{found_lbl}, label %{cond_lbl}")
            self._emit(f"{found_lbl}:")
            self._emit_indent(f"br label %{exit_lbl}")
            self._emit(f"{exit_lbl}:")
            self._emit_indent(f"{reg} = phi i1 [ 0, %{cond_lbl} ], [ 1, %{found_lbl} ]")
            return reg

        if method == "slice":
            # c.slice(start, end) — allocate new crate with a subrange
            start = args[0][0]
            end_v = args[1][0]
            new_len = self._fresh("slicelen")
            sz = self._fresh("slicesz")
            raw = self._fresh("sliceraw")
            new_ptr = self._fresh("sliceptr")
            dp = self._fresh("dp")
            src_ptr = self._fresh("srcptr")
            ep = self._fresh("ep")
            self._emit_indent(f"{new_len} = sub i64 {end_v}, {start}")
            self._emit_indent(f"{sz} = mul i64 {new_len}, 8")
            self._emit_indent(f"{raw} = call i8* @malloc(i64 {sz})")
            self._emit_indent(f"{new_ptr} = bitcast i8* {raw} to {inner_ll}*")
            self._emit_indent(
                f"{dp} = getelementptr inbounds %{cname}, %{cname}* {obj_val}, i32 0, i32 1"
            )
            self._emit_indent(f"{src_ptr} = load {inner_ll}*, {inner_ll}** {dp}")
            self._emit_indent(
                f"{ep} = getelementptr inbounds {inner_ll}, {inner_ll}* {src_ptr}, i64 {start}"
            )
            copy_raw = self._fresh("copy_raw")
            self._emit_indent(f"{copy_raw} = bitcast {inner_ll}* {ep} to i8*")
            self._emit_indent(f"call i8* @memcpy(i8* {raw}, i8* {copy_raw}, i64 {sz})")
            crate_ptr = self._fresh("slicecrate")
            self._emit_indent(f"{crate_ptr} = alloca %{cname}")
            lp = self._fresh("lp")
            ddp = self._fresh("ddp")
            self._emit_indent(
                f"{lp} = getelementptr inbounds %{cname}, %{cname}* {crate_ptr}, i32 0, i32 0"
            )
            self._emit_indent(f"store i64 {new_len}, i64* {lp}")
            self._emit_indent(
                f"{ddp} = getelementptr inbounds %{cname}, %{cname}* {crate_ptr}, i32 0, i32 1"
            )
            self._emit_indent(f"store {inner_ll}* {new_ptr}, {inner_ll}** {ddp}")
            return crate_ptr

        if method == "sort":
            # Only support unit (i64) for inline sort; call C helper for the rest
            lp = self._fresh("lp")
            length = self._fresh("sortlen")
            dp = self._fresh("dp")
            ptr = self._fresh("sortptr")
            self._emit_indent(
                f"{lp} = getelementptr inbounds %{cname}, %{cname}* {obj_val}, i32 0, i32 0"
            )
            self._emit_indent(f"{length} = load i64, i64* {lp}")
            self._emit_indent(
                f"{dp} = getelementptr inbounds %{cname}, %{cname}* {obj_val}, i32 0, i32 1"
            )
            self._emit_indent(f"{ptr} = load {inner_ll}*, {inner_ll}** {dp}")
            cast_ptr = self._fresh("sortcast")
            self._emit_indent(f"{cast_ptr} = bitcast {inner_ll}* {ptr} to i8*")
            self._emit_indent(
                f"call void @rubble_crate_sort_i64(i8* {cast_ptr}, i64 {length})"
            )
            return "null"

        if method == "reverse":
            lp = self._fresh("lp")
            length = self._fresh("revlen")
            dp = self._fresh("dp")
            ptr = self._fresh("revptr")
            elem_size = self._fresh("elemsz")
            self._emit_indent(
                f"{lp} = getelementptr inbounds %{cname}, %{cname}* {obj_val}, i32 0, i32 0"
            )
            self._emit_indent(f"{length} = load i64, i64* {lp}")
            self._emit_indent(
                f"{dp} = getelementptr inbounds %{cname}, %{cname}* {obj_val}, i32 0, i32 1"
            )
            self._emit_indent(f"{ptr} = load {inner_ll}*, {inner_ll}** {dp}")
            cast_ptr = self._fresh("revcast")
            self._emit_indent(f"{cast_ptr} = bitcast {inner_ll}* {ptr} to i8*")
            self._emit_indent(
                f"call void @rubble_crate_reverse(i8* {cast_ptr}, i64 {length}, i64 8)"
            )
            return "null"

        if method == "join":
            # Only valid on crate[text]
            sep = args[0][0] if args else "null"
            lp = self._fresh("lp")
            length = self._fresh("joinlen")
            dp = self._fresh("dp")
            ptr = self._fresh("joinptr")
            cast_ptr = self._fresh("joincast")
            self._emit_indent(
                f"{lp} = getelementptr inbounds %{cname}, %{cname}* {obj_val}, i32 0, i32 0"
            )
            self._emit_indent(f"{length} = load i64, i64* {lp}")
            self._emit_indent(
                f"{dp} = getelementptr inbounds %{cname}, %{cname}* {obj_val}, i32 0, i32 1"
            )
            self._emit_indent(f"{ptr} = load {inner_ll}*, {inner_ll}** {dp}")
            self._emit_indent(f"{cast_ptr} = bitcast {inner_ll}* {ptr} to i8**")
            self._emit_indent(
                f"{reg} = call i8* @rubble_crate_join(i8** {cast_ptr}, i64 {length}, i8* {sep})"
            )
            return reg

        return "null"

    def _emit_text_builtin(self, target, method, args, reg):
        obj_val = self._emit_expr(target)

        if method == "length":
            self._emit_indent(f"{reg} = call i64 @strlen(i8* {obj_val})")
            return reg

        if method == "upper":
            self._emit_indent(f"{reg} = call i8* @rubble_text_upper(i8* {obj_val})")
            return reg

        if method == "lower":
            self._emit_indent(f"{reg} = call i8* @rubble_text_lower(i8* {obj_val})")
            return reg

        if method == "trim":
            self._emit_indent(f"{reg} = call i8* @rubble_text_trim(i8* {obj_val})")
            return reg

        if method == "replace":
            old_v = args[0][0]
            new_v = args[1][0]
            self._emit_indent(
                f"{reg} = call i8* @rubble_text_replace(i8* {obj_val}, i8* {old_v}, i8* {new_v})"
            )
            return reg

        if method == "slice":
            start = args[0][0]
            end_v = args[1][0]
            self._emit_indent(
                f"{reg} = call i8* @rubble_text_slice(i8* {obj_val}, i64 {start}, i64 {end_v})"
            )
            return reg

        if method == "index":
            sub = args[0][0]
            self._emit_indent(
                f"{reg} = call i64 @rubble_text_index(i8* {obj_val}, i8* {sub})"
            )
            return reg

        if method == "split":
            sep = args[0][0]
            count_alloca = self._fresh("split_count")
            self._emit_indent(f"{count_alloca} = alloca i64")
            self._emit_indent(f"store i64 0, i64* {count_alloca}")
            arr = self._fresh("split_arr")
            self._emit_indent(
                f"{arr} = call i8** @rubble_text_split(i8* {obj_val}, i8* {sep}, i64* {count_alloca})"
            )
            count = self._fresh("split_len")
            self._emit_indent(f"{count} = load i64, i64* {count_alloca}")
            # Build Crate_i8p struct
            inner_ll = "i8*"
            cname = "Crate_i8p"
            self._crate_types.add((cname, inner_ll))
            crate_ptr = self._fresh("split_crate")
            self._emit_indent(f"{crate_ptr} = alloca %{cname}")
            lp = self._fresh("lp")
            dp = self._fresh("dp")
            self._emit_indent(
                f"{lp} = getelementptr inbounds %{cname}, %{cname}* {crate_ptr}, i32 0, i32 0"
            )
            self._emit_indent(f"store i64 {count}, i64* {lp}")
            self._emit_indent(
                f"{dp} = getelementptr inbounds %{cname}, %{cname}* {crate_ptr}, i32 0, i32 1"
            )
            self._emit_indent(f"store i8** {arr}, i8*** {dp}")
            return crate_ptr

        if method == "contains":
            sub = args[0][0]
            found = self._fresh("strstr_r")
            self._emit_indent(f"{found} = call i8* @strstr(i8* {obj_val}, i8* {sub})")
            self._emit_indent(f"{reg} = icmp ne i8* {found}, null")
            return reg

        if method == "starts":
            sub = args[0][0]
            slen = self._fresh("slen")
            cmp_r = self._fresh("cmp_r")
            self._emit_indent(f"{slen} = call i64 @strlen(i8* {sub})")
            self._emit_indent(
                f"{cmp_r} = call i32 @strncmp(i8* {obj_val}, i8* {sub}, i64 {slen})"
            )
            self._emit_indent(f"{reg} = icmp eq i32 {cmp_r}, 0")
            return reg

        if method == "ends":
            sub = args[0][0]
            olen = self._fresh("olen")
            slen = self._fresh("slen")
            diff = self._fresh("diff")
            ep = self._fresh("ep")
            cmp_r = self._fresh("cmp_r")
            self._emit_indent(f"{olen} = call i64 @strlen(i8* {obj_val})")
            self._emit_indent(f"{slen} = call i64 @strlen(i8* {sub})")
            self._emit_indent(f"{diff} = sub i64 {olen}, {slen}")
            self._emit_indent(
                f"{ep} = getelementptr inbounds i8, i8* {obj_val}, i64 {diff}"
            )
            self._emit_indent(f"{cmp_r} = call i32 @strcmp(i8* {ep}, i8* {sub})")
            self._emit_indent(f"{reg} = icmp eq i32 {cmp_r}, 0")
            return reg

        return "null"

    def _emit_build(self, node: BuildExpr) -> str:
        bp = self._blueprints.get(node.blueprint)
        if not bp:
            return "null"
        # Heap-allocate the blueprint so it can escape functions and live in crates
        size_reg = self._fresh("bp_size")
        raw_reg = self._fresh("bp_raw")
        ptr = self._fresh("bp")
        n_fields = len(bp.fields)
        self._emit_indent(f"{size_reg} = mul i64 {n_fields}, 8")
        self._emit_indent(f"{raw_reg} = call i8* @malloc(i64 {size_reg})")
        self._emit_indent(f"{ptr} = bitcast i8* {raw_reg} to %{node.blueprint}*")
        for fname, fexpr in node.kwargs:
            for i, f in enumerate(bp.fields):
                if f.name == fname:
                    fval = self._emit_expr(fexpr)
                    fll = llvm_type(f.type_node)
                    fptr = self._fresh("fptr")
                    self._emit_indent(
                        f"{fptr} = getelementptr inbounds %{node.blueprint}, %{node.blueprint}* {ptr}, i32 0, i32 {i}"
                    )
                    self._emit_indent(f"store {fll} {fval}, {fll}* {fptr}")
        return ptr

    def _emit_crate_lit(self, node: CrateLit) -> str:
        if not node.elements:
            return "null"
        t = getattr(node, "rtype", None)
        if not t or t.name != "crate":
            return "null"
        inner_ll = llvm_type(t.inner) if t.inner else "i8"
        crate_name = f"Crate_{inner_ll.replace('*', 'p').replace(' ', '_')}"
        self._crate_types.add((crate_name, inner_ll))
        n = len(node.elements)
        arr_ptr = self._fresh("arr")
        total = self._fresh("arr_size")
        self._emit_indent(f"{total} = mul i64 {n}, 8")
        self._emit_indent(f"{arr_ptr} = call i8* @malloc(i64 {total})")
        typed_ptr = self._fresh("arr_typed")
        self._emit_indent(f"{typed_ptr} = bitcast i8* {arr_ptr} to {inner_ll}*")
        for i, elem in enumerate(node.elements):
            ev = self._emit_expr(elem)
            ep = self._fresh("ep")
            self._emit_indent(
                f"{ep} = getelementptr inbounds {inner_ll}, {inner_ll}* {typed_ptr}, i64 {i}"
            )
            self._emit_indent(f"store {inner_ll} {ev}, {inner_ll}* {ep}")
        crate_ptr = self._fresh("crate")
        self._emit_indent(f"{crate_ptr} = alloca %{crate_name}")
        lp = self._fresh("lp")
        dp = self._fresh("dp")
        self._emit_indent(
            f"{lp} = getelementptr inbounds %{crate_name}, %{crate_name}* {crate_ptr}, i32 0, i32 0"
        )
        self._emit_indent(f"store i64 {n}, i64* {lp}")
        self._emit_indent(
            f"{dp} = getelementptr inbounds %{crate_name}, %{crate_name}* {crate_ptr}, i32 0, i32 1"
        )
        self._emit_indent(f"store {inner_ll}* {typed_ptr}, {inner_ll}** {dp}")
        return crate_ptr

    def _emit_crate_type_defs(self) -> List[str]:
        lines = []
        for name, inner_ll in self._crate_types:
            lines.append(f"%{name} = type {{ i64, {inner_ll}* }}")
        return lines

    def _emit_switch(self, node: SwitchStmt) -> str:
        """Emit a switch statement (not an expression)."""
        # For now, emit as a chain of if/else statements (a simple approach)
        val_reg = self._emit_expr(node.value)
        val_t = getattr(node.value, "rtype", T_UNIT)

        # Create labels for each case and default
        case_labels = []
        for i in range(len(node.arms)):
            case_labels.append(self._label("switch_case"))

        default_label = None
        if node.default_block:
            default_label = self._label("switch_default")

        merge_label = self._label("switch_merge")

        # Generate each case
        for i, (pat, body) in enumerate(node.arms):
            # Compare value with pattern
            pat_reg = self._emit_expr(pat)

            cmp_reg = self._fresh("switch_cmp")
            if val_t.name == "decimal":
                self._emit_indent(f"{cmp_reg} = fcmp oeq double {val_reg}, {pat_reg}")
            elif val_t.name == "text":
                strcmp_res = self._fresh("strcmp")
                self._emit_indent(
                    f"{strcmp_res} = call i32 @strcmp(i8* {val_reg}, i8* {pat_reg})"
                )
                self._emit_indent(f"{cmp_reg} = icmp eq i32 {strcmp_res}, 0")
            else:
                self._emit_indent(f"{cmp_reg} = icmp eq i64 {val_reg}, {pat_reg}")

            # Branch to case body if match
            next_label = merge_label if i == len(node.arms) - 1 else case_labels[i + 1]
            self._emit_indent(
                f"br i1 {cmp_reg}, label %{case_labels[i]}, label %{next_label}"
            )

            # Emit case body
            self._emit(f"{case_labels[i]}:")
            self._emit_block(body)
            self._emit_indent(f"br label %{merge_label}")

        if node.default_block:
            self._emit(f"{default_label}:")
            self._emit_block(node.default_block)
            self._emit_indent(f"br label %{merge_label}")

        # Merge point
        self._emit(f"{merge_label}:")
        return "null"

    def _emit_match_expr(self, node: MatchExpr) -> str:
        """Emit a match expression as a chain of conditional branches."""
        val_reg = self._emit_expr(node.value)
        val_t = getattr(node.value, "rtype", T_UNIT)

        # Create labels for each case and default
        case_labels = []
        for i in range(len(node.arms)):
            case_labels.append(self._label("match_case"))

        default_label = None
        if node.default_expr:
            default_label = self._label("match_default")

        merge_label = self._label("match_merge")

        # Create a register to hold the result
        result_reg = self._fresh("match_result")

        # Generate each case
        for i, (pat, body) in enumerate(node.arms):
            # Compare value with pattern
            pat_reg = self._emit_expr(pat)

            cmp_reg = self._fresh("match_cmp")
            if val_t.name == "decimal":
                self._emit_indent(f"{cmp_reg} = fcmp oeq double {val_reg}, {pat_reg}")
            elif val_t.name == "text":
                strcmp_res = self._fresh("strcmp")
                self._emit_indent(
                    f"{strcmp_res} = call i32 @strcmp(i8* {val_reg}, i8* {pat_reg})"
                )
                self._emit_indent(f"{cmp_reg} = icmp eq i32 {strcmp_res}, 0")
            else:
                self._emit_indent(f"{cmp_reg} = icmp eq i64 {val_reg}, {pat_reg}")

            # Branch to case body if match
            next_label = merge_label if i == len(node.arms) - 1 else case_labels[i + 1]
            self._emit_indent(
                f"br i1 {cmp_reg}, label %{case_labels[i]}, label %{next_label}"
            )

            # Emit case body and store result
            self._emit(f"{case_labels[i]}:")
            body_reg = self._emit_expr(body)
            self._emit_indent(
                f"store {llvm_type(getattr(body, 'rtype', T_UNIT))} {body_reg}, {llvm_type(getattr(body, 'rtype', T_UNIT))}* {result_reg}"
            )
            self._emit_indent(f"br label %{merge_label}")

        if node.default_expr:
            self._emit(f"{default_label}:")
            default_reg = self._emit_expr(node.default_expr)
            self._emit_indent(
                f"store {llvm_type(getattr(node.default_expr, 'rtype', T_UNIT))} {default_reg}, {llvm_type(getattr(node.default_expr, 'rtype', T_UNIT))}* {result_reg}"
            )
            self._emit_indent(f"br label %{merge_label}")

        # Merge point
        self._emit(f"{merge_label}:")
        return result_reg
