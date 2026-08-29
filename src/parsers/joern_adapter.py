"""
joern_adapter.py

PRODUCTION EXTENSION POINT (not used by the runnable demo, which relies on
Python's built-in `ast` module to stay dependency-free).

This module shows how the same GraphEngineeringAgent interface would be
backed by real Joern / Soot / WALA / Tree-sitter tooling for multi-language,
industrial-scale repos:

  * Tree-sitter   -> fast, language-agnostic AST for the "structural" layer
                     across many languages without needing a full compiler
                     front end (JS/TS, Python, Go, Rust, C/C++, Java, ...).

  * Soot           -> whole-program CFG + call-graph + points-to analysis for
                     JVM bytecode (Java/Kotlin/Scala). Use when you need
                     precise interprocedural data-flow, not just intraprocedural.

  * WALA           -> alternative/complementary JVM static-analysis
                     framework; strong for points-to analysis and
                     interprocedural CFGs, often used alongside or instead
                     of Soot depending on the target JDK / bytecode version.

  * Joern          -> ingests the above (or its own CPG frontends) into a
                     single unified Code Property Graph, queryable via
                     CPGQL. This is where AST + CFG + DFG + call graph get
                     merged into ONE graph so slicing queries can hop across
                     all edge kinds in one traversal, and where you'd query
                     at repo scale instead of per-file.

None of these binaries are installed in this sandbox (Joern/Soot/WALA need a
JVM + separate downloads), so this file documents the integration contract
rather than executing it. Swap CPGBuilder for JoernCPGBuilder below in
GraphEngineeringAgent to go from demo -> production.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import networkx as nx


class JoernCPGBuilder:
    """
    Wraps the Joern CLI to build a real CPG for a repo, then imports it into
    the same NetworkX MultiDiGraph shape used by cpg_builder.CPGBuilder, so
    slicer.py works unmodified regardless of which backend produced the graph.

    Expected local setup:
        1. Install Joern:  https://joern.io  (requires JVM)
        2. `joern-parse <repo_dir> -o cpg.bin`
        3. `joern-export cpg.bin --repr all --format graphml -o cpg_export/`
           (or drive it interactively via joern's `joern-cli` script + CPGQL
           queries, e.g. `cpg.method.name("compute").ast.l`)
    """

    def __init__(self, repo_dir: str, joern_home: str = "/opt/joern"):
        self.repo_dir = Path(repo_dir)
        self.joern_home = Path(joern_home)

    def run_cpgql(self, query: str) -> list[dict]:
        """Run a CPGQL query against an already-parsed CPG and return JSON results.
        Example query: 'cpg.method.name("compute").ast.isCall.l'
        """
        script = self.joern_home / "joern-cli" / "joern"
        result = subprocess.run(
            [str(script), "--script", "-"],
            input=f'importCpg("cpg.bin")\nval r = {query}\nprintln(r.toJson)\n',
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)

    def build(self) -> nx.MultiDiGraph:
        """
        1. joern-parse the repo -> cpg.bin
        2. joern-export --format graphml (Joern natively supports GraphML/DOT export)
        3. nx.read_graphml(...) to load directly into NetworkX, preserving
           Joern's AST/CFG/CDG/REACHING_DEF (data-flow) edge labels so
           slicer.py's RELEVANT_EDGE_TYPES filter (extended with "REACHING_DEF",
           "CDG") works unchanged.
        """
        subprocess.run(
            [str(self.joern_home / "joern-cli" / "joern-parse"), str(self.repo_dir), "-o", "cpg.bin"],
            check=True,
        )
        subprocess.run(
            [str(self.joern_home / "joern-cli" / "joern-export"), "cpg.bin",
             "--repr", "all", "--format", "graphml", "-o", "cpg_export"],
            check=True,
        )
        graph = nx.MultiDiGraph()
        for gml_file in Path("cpg_export").glob("*.graphml"):
            g = nx.read_graphml(gml_file)
            graph = nx.compose(graph, g)
        return graph


class SootWalaAdapter:
    """
    For Java/JVM repos where you need whole-program interprocedural
    call-graph + points-to precision beyond what Joern's default dataflow
    tracker gives you (e.g. resolving virtual dispatch, reflection heuristics).

    Typical flow:
        Soot:  `soot.Main` configured with `-cfg -w` to emit a whole-program
               call graph (CHA/SPARK) and per-method CFGs, exported as DOT.
        WALA:  build a `CallGraphBuilder` (e.g. ZeroXCFABuilder), walk the
               resulting `CallGraph` + `PointerAnalysis`, and emit edges.

    Either tool's output gets normalized into the same node/edge schema as
    CPGBuilder (kind, label, lineno, scope) + edge types ("cfg", "dfg",
    "call"), then merged with the Joern CPG (or used standalone) before
    slicer.py runs backward/forward slicing across the combined graph.
    """

    def __init__(self, classpath: str):
        self.classpath = classpath

    def build_callgraph_edges(self) -> list[tuple[str, str]]:
        raise NotImplementedError(
            "Invoke Soot's CHATransformer / SparkTransformer or WALA's "
            "CallGraphBuilder here, then map resulting call edges to CPG "
            "node ids by (class, method, lineno)."
        )
