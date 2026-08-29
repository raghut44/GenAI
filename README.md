# Graph Engineering Agent

A working sample of a **Graph Engineering Agent**: it builds a **Code
Property Graph** (AST + Control-Flow Graph + Data-Flow Graph) for a source
file and performs **program slicing** to select only the code that is
*causally relevant* to a target line or function — so a Copilot-style
coding assistant can send a minimal, dependency-complete context instead of
a whole file or repo.

## Why this shrinks the context window

Naively, "give the LLM more context" means pasting the whole file. Most of
that file is irrelevant to any given completion request. A CPG lets you ask
a much sharper question:

> "Of everything in this repo, what does line 26 actually **depend on**
> (backward slice), or what does it **affect** (forward slice)?"

Only those statements — pulled via control-flow and data-flow edges, not
proximity in the file — get sent to the model.

## Architecture

```
source file(s)
     │
     ▼
┌─────────────────┐   AST layer        (Tree-sitter in prod / Python `ast` here)
│  CPGBuilder      │   CFG layer        (Soot/WALA in prod / lightweight builder here)
│  (cpg_builder.py)│   DFG layer        (def-use chains, same idea as Soot/WALA dataflow)
└────────┬─────────┘
         │  merged into one NetworkX MultiDiGraph
         ▼
┌─────────────────┐
│  Slicer          │   backward_slice() / forward_slice()
│  (slicer.py)     │   NetworkX graph traversal over cfg+dfg edges
└────────┬─────────┘   (Joern CPGQL queries play this role at repo scale)
         ▼
┌─────────────────┐
│ GraphEngineering │   assembles minimal line ranges into a context block,
│ Agent            │   reports token savings vs. the full file
└─────────────────┘
```

### Mapping to the tools named in the spec

| Tool | Role | In this project |
|---|---|---|
| **Tree-sitter** | fast, language-agnostic AST parsing | stubbed out with Python's built-in `ast` module for a zero-dependency demo; swap in `tree_sitter` + `tree-sitter-languages` for multi-language support (see `src/parsers/`) |
| **Soot / WALA** | JVM CFG, call-graph, points-to analysis | represented by the lightweight intraprocedural CFG/DFG pass in `cpg_builder.py`; `src/parsers/joern_adapter.py::SootWalaAdapter` documents how to wire in real Soot (CHA/SPARK) or WALA call-graph builders for precise interprocedural Java analysis |
| **Joern** | unified CPG storage + CPGQL queries | `src/parsers/joern_adapter.py::JoernCPGBuilder` shows how to `joern-parse` a repo, export as GraphML, and load it into the *same* NetworkX graph shape so `slicer.py` runs unmodified against a real CPG |
| **NetworkX** | graph traversal & slicing | used directly and fully — `slicer.py` does real backward/forward slicing over `cfg`/`dfg` edge types |

This means you can develop and test slicing logic entirely on the
lightweight Python backend, then point `GraphEngineeringAgent` at
`JoernCPGBuilder` for production/multi-language repos without touching
`slicer.py` or the agent's public API.

## Project layout

```
graph-engineering-agent/
├── src/
│   ├── graph/
│   │   ├── cpg_builder.py     # AST + CFG + DFG -> NetworkX MultiDiGraph
│   │   └── slicer.py          # backward_slice / forward_slice
│   ├── parsers/
│   │   └── joern_adapter.py   # production extension points (Joern/Soot/WALA)
│   ├── agent/
│   │   └── graph_engineering_agent.py   # orchestration + minimal-context assembly
│   └── utils/
│       └── token_utils.py     # tiktoken-based (or heuristic) token counting
├── examples/sample_repo/billing.py   # sample file with relevant + irrelevant functions
├── run_demo.py                       # end-to-end CLI demo
└── requirements.txt
```

## Running it

```bash
pip install -r requirements.txt
python run_demo.py
```

## Sample results (from `run_demo.py`)

Slicing on the `apply_discount` function pulls in only its real
dependencies (`TAX_RATE`, `LOYALTY_THRESHOLD`, `get_base_price`,
`get_loyalty_discount`) and correctly **excludes** unrelated functions like
`format_receipt`, `send_welcome_email`, `log_audit_event`, and
`unrelated_math_helper`:

```
Full file tokens:   382
Sliced context:     138
Tokens saved:       244 (63.9% reduction)
```

Slicing on a single target line inside that function is even tighter:

```
Full file tokens:   382
Sliced context:     79
Tokens saved:       303 (79.3% reduction)
```

## Known limitation of the demo CFG (and how production fixes it)

The demo's `_link_cfg_sequence` chains **module-level statements
sequentially**, which is how Python actually executes top-level code — but
it means a *forward* slice from a module-level constant (e.g. `TAX_RATE`)
will walk into every function defined after it via `cfg` edges, even
functions that don't reference it, because "runs after" and "is affected
by" get conflated at module scope. This shows up in `run_demo.py`'s Slice 3
(only 17% reduction, vs. 64–79% for the other two slices).

This is exactly the gap that **Soot/WALA's interprocedural call-graph +
points-to analysis** and **Joern's `REACHING_DEF`/`CDG` edges** are built to
close: real data-flow edges only connect a definition to its actual uses,
regardless of lexical position, so forward slices stay precise even across
many functions. `JoernCPGBuilder` in `src/parsers/joern_adapter.py` is the
drop-in path to that precision — swap it for `CPGBuilder` in
`GraphEngineeringAgent.index_file` and `slicer.py` needs no changes, since
it only cares about edge `type` ("cfg", "dfg"), not which backend produced
them.

## Extending

- **Multi-language**: replace `ast.parse` in `cpg_builder.py` with
  Tree-sitter parsers per language; the rest of the pipeline (CFG/DFG
  construction shape, node schema, slicing) stays the same in spirit.
- **Interprocedural slicing**: add `call` edges (caller stmt -> callee
  `FunctionDef` node) and extend `RELEVANT_EDGE_TYPES` in `slicer.py` to hop
  across function boundaries — this is where Soot/WALA call-graphs matter
  most.
- **Repo-scale**: swap `CPGBuilder` for `JoernCPGBuilder` and index a whole
  repo instead of one file at a time.
- **Copilot integration**: `GraphEngineeringAgent.get_context_for_line`
  is the shape of function you'd call from an editor extension right before
  constructing the completion prompt, using the cursor's file+line as the
  slicing target.
