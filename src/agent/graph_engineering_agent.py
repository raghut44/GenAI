"""
graph_engineering_agent.py

The Graph Engineering Agent itself. Orchestrates:

    source file(s)
        -> CPGBuilder            (AST + CFG + DFG, via Tree-sitter/ast + Soot/WALA-style pass)
        -> program slicing       (NetworkX backward/forward traversal, or Joern CPGQL in prod)
        -> minimal context block (only causally-relevant lines, ready for Copilot/LLM prompt)

The agent's `get_context_for` method is the main entry point a coding
assistant would call before sending a prompt: instead of stuffing the whole
file (or worse, the whole repo) into the context window, it returns only the
statements the target line actually depends on / affects, plus a token
savings report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.graph.cpg_builder import CPGBuilder
from src.graph import slicer
from src.utils.token_utils import count_tokens


@dataclass
class SliceResult:
    filename: str
    target_description: str
    line_ranges: list[tuple[int, int]]
    context: str
    full_file_tokens: int
    sliced_tokens: int

    @property
    def tokens_saved(self) -> int:
        return self.full_file_tokens - self.sliced_tokens

    @property
    def reduction_pct(self) -> float:
        if self.full_file_tokens == 0:
            return 0.0
        return 100.0 * self.tokens_saved / self.full_file_tokens


class GraphEngineeringAgent:
    def __init__(self):
        self._cache: dict[str, tuple[str, "nx.MultiDiGraph"]] = {}

    # ---------------------------------------------------------------- build
    def index_file(self, path: str) -> None:
        """Parse a file and build/cache its CPG."""
        source = Path(path).read_text()
        graph = CPGBuilder(source, filename=path).build()
        self._cache[path] = (source, graph)

    # ---------------------------------------------------------------- query
    def get_context_for_line(
        self, path: str, lineno: int, direction: str = "backward", context_lines: int = 0
    ) -> SliceResult:
        if path not in self._cache:
            self.index_file(path)
        source, graph = self._cache[path]

        target_ids = slicer.find_nodes_by_line(graph, lineno)
        if not target_ids:
            raise ValueError(f"No CPG node found at line {lineno} in {path}")

        relevant = self._compute_slice(graph, target_ids, direction)
        return self._materialize(path, source, graph, relevant, f"line {lineno} ({direction} slice)", context_lines)

    def get_context_for_function(
        self, path: str, func_name: str, direction: str = "backward", context_lines: int = 0
    ) -> SliceResult:
        if path not in self._cache:
            self.index_file(path)
        source, graph = self._cache[path]

        target_ids = slicer.find_nodes_by_function(graph, func_name)
        if not target_ids:
            raise ValueError(f"No function named '{func_name}' found in {path}")

        relevant = self._compute_slice(graph, target_ids, direction)
        return self._materialize(path, source, graph, relevant, f"function '{func_name}' ({direction} slice)", context_lines)

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _compute_slice(graph, target_ids, direction):
        if direction == "backward":
            return slicer.backward_slice(graph, target_ids)
        elif direction == "forward":
            return slicer.forward_slice(graph, target_ids)
        elif direction == "both":
            return slicer.backward_slice(graph, target_ids) | slicer.forward_slice(graph, target_ids)
        raise ValueError("direction must be 'backward', 'forward', or 'both'")

    @staticmethod
    def _materialize(path, source, graph, relevant_ids, description, context_lines):
        ranges = slicer.slice_to_line_ranges(graph, relevant_ids)
        # expand each range slightly for human/LLM readability if requested
        if context_lines:
            ranges = [(max(1, s - context_lines), e + context_lines) for s, e in ranges]

        src_lines = source.splitlines()
        blocks = []
        for start, end in ranges:
            snippet = "\n".join(src_lines[start - 1:end])
            blocks.append(f"# lines {start}-{end}\n{snippet}")
        context = "\n\n".join(blocks)

        full_tokens = count_tokens(source)
        sliced_tokens = count_tokens(context)

        return SliceResult(
            filename=path,
            target_description=description,
            line_ranges=ranges,
            context=context,
            full_file_tokens=full_tokens,
            sliced_tokens=sliced_tokens,
        )
