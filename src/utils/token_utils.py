"""
token_utils.py

Token counting for measuring how much the sliced context saves versus the
full file. Uses tiktoken if available (accurate, same family of tokenizers
used by Copilot/OpenAI/Anthropic-adjacent models); falls back to a simple
whitespace/punctuation heuristic (~4 chars/token) if tiktoken isn't
installed, so the demo runs anywhere.
"""

from __future__ import annotations

try:
    import tiktoken
    _ENC = tiktoken.get_encoding("cl100k_base")
except Exception:
    _ENC = None


def count_tokens(text: str) -> int:
    if _ENC is not None:
        return len(_ENC.encode(text))
    # crude fallback heuristic
    return max(1, len(text) // 4)
