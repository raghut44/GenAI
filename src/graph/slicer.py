"""
slicer.py

Program slicing over the merged CPG (AST + CFG + DFG), using NetworkX graph
traversal. This is the piece that ultimately shrinks the LLM/Copilot context:
instead of feeding a whole file (or repo) to the model, we compute the
minimal set of statements that are *causally relevant* to a target line —
i.e. everything it depends on (backward slice) and, optionally, everything
that depends on it (forward slice).

Backward slice  = "what must be true / computed for this line to make sense"
Forward slice   = "what this line's value/effects can reach"

In a production system this traversal would run against a Joern CPG stored
in its own graph DB and queried via CPGQL; NetworkX here plays the same role
for the lightweight Python-`ast`-derived CPG built in cpg_builder.py.
"""

from __future__ import annotations

import networkx as nx
from typing import Iterable


RELEVANT_EDGE_TYPES = {"cfg", "dfg"}


def _relevant_predecessors(graph: nx.MultiDiGraph, node: int) -> Iterable[int]:
    for pred in graph.predecessors(node):
        for _, _, data in graph.in_edges(pred, data=True):
            pass
    # MultiDiGraph: inspect edge data on edges into `node`
    for u, v, data in graph.in_edges(node, data=True):
        if data.get("type") in RELEVANT_EDGE_TYPES:
            yield u


def _relevant_successors(graph: nx.MultiDiGraph, node: int) -> Iterable[int]:
    for u, v, data in graph.out_edges(node, data=True):
        if data.get("type") in RELEVANT_EDGE_TYPES:
            yield v


def backward_slice(graph: nx.MultiDiGraph, target_ids: list[int], max_hops: int = 50) -> set[int]:
    """Return the set of node ids that `target_ids` control-/data-depend on."""
    visited: set[int] = set(target_ids)
    frontier = list(target_ids)
    hops = 0
    while frontier and hops < max_hops:
        next_frontier = []
        for node in frontier:
            for pred in _relevant_predecessors(graph, node):
                if pred not in visited:
                    visited.add(pred)
                    next_frontier.append(pred)
        frontier = next_frontier
        hops += 1
    return visited


def forward_slice(graph: nx.MultiDiGraph, target_ids: list[int], max_hops: int = 50) -> set[int]:
    """Return the set of node ids that are control-/data-affected by `target_ids`."""
    visited: set[int] = set(target_ids)
    frontier = list(target_ids)
    hops = 0
    while frontier and hops < max_hops:
        next_frontier = []
        for node in frontier:
            for succ in _relevant_successors(graph, node):
                if succ not in visited:
                    visited.add(succ)
                    next_frontier.append(succ)
        frontier = next_frontier
        hops += 1
    return visited


def find_nodes_by_line(graph: nx.MultiDiGraph, lineno: int) -> list[int]:
    return [
        n for n, d in graph.nodes(data=True)
        if d.get("lineno") is not None and d.get("end_lineno") is not None
        and d["lineno"] <= lineno <= d["end_lineno"]
    ]


def find_nodes_by_function(graph: nx.MultiDiGraph, func_name: str) -> list[int]:
    return [n for n, d in graph.nodes(data=True) if d.get("scope") == func_name]


def slice_to_line_ranges(graph: nx.MultiDiGraph, node_ids: set[int]) -> list[tuple[int, int]]:
    """Collapse a set of relevant CPG nodes into merged, sorted source line ranges."""
    lines = sorted({
        d["lineno"] for n in node_ids
        if (d := graph.nodes[n]).get("lineno") is not None
    })
    if not lines:
        return []
    ranges = []
    start = prev = lines[0]
    for ln in lines[1:]:
        if ln <= prev + 1:
            prev = ln
        else:
            ranges.append((start, prev))
            start = prev = ln
    ranges.append((start, prev))
    return ranges
