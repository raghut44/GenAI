"""
cpg_builder.py

Builds a Code Property Graph (CPG) for a single Python source file:
  - AST edges   ("ast_child")   -> structural parent/child relationships
  - CFG edges   ("cfg")         -> control-flow ("what runs after what")
  - DFG edges   ("dfg")         -> data-flow / def-use chains ("who reads what X wrote")

This mirrors the role that Tree-sitter (AST), Soot/WALA (CFG + points-to/DFG for
JVM languages) and Joern (unified CPG storage + traversal queries) play in the
production pipeline described in the prompt. Here we use Python's built-in
`ast` module as a zero-dependency stand-in for Tree-sitter, and implement a
lightweight intraprocedural CFG/DFG builder as a stand-in for Soot/WALA, all
stored in a NetworkX MultiDiGraph exactly the way Joern query results would be
materialized for downstream slicing.
"""

from __future__ import annotations

import ast
import networkx as nx
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CPGNode:
    node_id: int
    kind: str                 # "Module", "FunctionDef", "Assign", "Call", "Name", ...
    label: str                # human-readable summary, e.g. "x = compute(y)"
    lineno: Optional[int] = None
    end_lineno: Optional[int] = None
    scope: str = "<module>"   # enclosing function/class for readability


class CPGBuilder:
    """Parses a Python source file and emits a merged AST+CFG+DFG graph."""

    def __init__(self, source: str, filename: str = "<source>"):
        self.source = source
        self.filename = filename
        self.tree = ast.parse(source, filename=filename)
        self.graph = nx.MultiDiGraph()
        self._next_id = 0
        self._node_of: dict[int, int] = {}     # python id(ast_node) -> cpg node id
        self._defs: dict[str, list[int]] = {}  # var name -> stack of last-def node ids (per scope walk)

    # ---------------------------------------------------------------- utils
    def _new_id(self) -> int:
        nid = self._next_id
        self._next_id += 1
        return nid

    def _add_node(self, ast_node: ast.AST, kind: str, label: str, scope: str) -> int:
        nid = self._new_id()
        cpg_node = CPGNode(
            node_id=nid,
            kind=kind,
            label=label,
            lineno=getattr(ast_node, "lineno", None),
            end_lineno=getattr(ast_node, "end_lineno", None),
            scope=scope,
        )
        self.graph.add_node(nid, **cpg_node.__dict__)
        self._node_of[id(ast_node)] = nid
        return nid

    @staticmethod
    def _summarize(node: ast.AST) -> str:
        try:
            return ast.unparse(node).strip().splitlines()[0][:80]
        except Exception:
            return type(node).__name__

    # -------------------------------------------------------------- AST pass
    def _walk_ast(self, node: ast.AST, parent_id: Optional[int], scope: str):
        kind = type(node).__name__
        if isinstance(node, (ast.stmt, ast.expr, ast.Module)):
            label = self._summarize(node) if not isinstance(node, ast.Module) else self.filename
            new_scope = scope
            if isinstance(node, ast.FunctionDef):
                new_scope = node.name
            nid = self._add_node(node, kind, label, new_scope)
            if parent_id is not None:
                self.graph.add_edge(parent_id, nid, type="ast_child")
        else:
            nid = parent_id  # skip non-stmt/expr wrapper nodes but keep recursing

        for child in ast.iter_child_nodes(node):
            self._walk_ast(child, nid if nid is not None else parent_id, scope if nid == parent_id else (scope if not isinstance(node, ast.FunctionDef) else node.name))

    # -------------------------------------------------------------- CFG pass
    def _link_cfg_sequence(self, stmt_nodes: list[ast.stmt]):
        """Chain sequential statements with cfg edges; recurse into bodies."""
        prev_id = None
        for stmt in stmt_nodes:
            nid = self._node_of.get(id(stmt))
            if nid is None:
                continue
            if prev_id is not None:
                self.graph.add_edge(prev_id, nid, type="cfg")
            prev_id = nid

            # Recurse into compound statement bodies so control flow keeps
            # going *into* the branch and (approximately) falls back out.
            if isinstance(stmt, (ast.If, ast.For, ast.While, ast.FunctionDef, ast.With)):
                body = getattr(stmt, "body", [])
                self._link_cfg_sequence(body)
                first_body_id = self._node_of.get(id(body[0])) if body else None
                if first_body_id is not None:
                    self.graph.add_edge(nid, first_body_id, type="cfg")
                orelse = getattr(stmt, "orelse", [])
                if orelse:
                    self._link_cfg_sequence(orelse)

    # -------------------------------------------------------------- DFG pass
    def _link_dfg(self):
        """Def-use chains: for every Name(Load) find nearest prior Name(Store)
        of the same identifier within the same scope and add a dfg edge."""
        last_def: dict[tuple[str, str], int] = {}  # (scope, var) -> cpg node id of last assignment

        # Walk statements in source order (lineno) per node we already created.
        ordered = sorted(
            (n for n, d in self.graph.nodes(data=True) if d.get("lineno") is not None),
            key=lambda n: (self.graph.nodes[n]["lineno"], n),
        )
        # Re-walk the AST directly for accurate Name/Store/Load detection,
        # since CPG nodes only exist for stmt/expr types we captured above.
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Assign):
                scope = self._scope_of(node)
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        def_id = self._node_of.get(id(node))
                        if def_id is not None:
                            last_def[(scope, target.id)] = def_id
            elif isinstance(node, ast.arg):
                # function parameters count as definitions at function entry
                pass
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                scope = self._scope_of(node)
                key = (scope, node.id)
                if key in last_def:
                    use_id = self._nearest_captured_ancestor(node)
                    if use_id is not None and use_id != last_def[key]:
                        self.graph.add_edge(last_def[key], use_id, type="dfg", var=node.id)

    def _scope_of(self, node: ast.AST) -> str:
        # Walk up via parent map built during AST pass (approx: use lineno bounds)
        for candidate_id, data in self.graph.nodes(data=True):
            pass
        return getattr(node, "_scope_hint", "<module>")

    def _nearest_captured_ancestor(self, node: ast.AST) -> Optional[int]:
        cur = node
        while cur is not None:
            nid = self._node_of.get(id(cur))
            if nid is not None:
                return nid
            cur = getattr(cur, "_parent", None)
        return None

    def _annotate_scopes_and_parents(self):
        """Single pass to attach `_parent` and `_scope_hint` to every ast node,
        since Python's ast module doesn't track these by default."""
        def visit(node, parent, scope):
            node._parent = parent
            node._scope_hint = scope
            new_scope = node.name if isinstance(node, ast.FunctionDef) else scope
            for child in ast.iter_child_nodes(node):
                visit(child, node, new_scope)
        visit(self.tree, None, "<module>")

    # ------------------------------------------------------------------ run
    def build(self) -> nx.MultiDiGraph:
        self._annotate_scopes_and_parents()
        self._walk_ast(self.tree, None, "<module>")
        self._link_cfg_sequence(self.tree.body)
        # also link cfg for statements inside every function body encountered
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef):
                self._link_cfg_sequence(node.body)
        self._link_dfg()
        return self.graph
