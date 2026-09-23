"""
TOON — Token-Oriented Object Notation
======================================
How agent output is handed to the language model.

JSON spends a large share of its tokens on punctuation and on repeating every
key for every row. A farm plan with twelve tasks repeats the same fourteen
field names twelve times. TOON writes the keys once as a header and the values
as rows, which is both shorter and easier for a model to read in order.

    JSON     {"tasks":[{"title":"Irrigate","date":"2026-06-15","priority":"critical"},
                       {"title":"Spray","date":"2026-06-16","priority":"high"}]}

    TOON     tasks[2]{title,date,priority}:
               Irrigate,2026-06-15,critical
               Spray,2026-06-16,high

Three rules make it safe to use for real decisions:

  * Numbers are never reformatted. 7.5 stays 7.5, not 7.5000001 or "7.5".
  * The row count is declared, so a truncated list is detectable rather than
    silently short.
  * Any value containing a delimiter is quoted, so a comma inside a sentence
    cannot shift a column.

Used on the prompt side only. The API response stays JSON.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence

INDENT = "  "
# Deep enough for every real FarmXpert payload (the task plan nests 7 levels),
# with room to spare. The cap exists only to stop a cyclic or pathological
# structure producing an unbounded prompt, not to trim real data.
MAX_DEPTH = 16


def encode(value: Any, *, name: Optional[str] = None) -> str:
    """Render a Python structure as TOON."""
    lines: List[str] = []
    _write(name, value, 0, lines, depth=0)
    return "\n".join(line for line in lines if line.strip())


def encode_agent_results(results: Dict[str, Any]) -> str:
    """Agent outputs as one TOON document, one block per agent."""
    blocks = [encode(payload, name=agent) for agent, payload in sorted(results.items())
              if payload is not None]
    return "\n".join(blocks)


# ── writer ──────────────────────────────────────────────────────────────────

def _write(key: Optional[str], value: Any, level: int,
           out: List[str], *, depth: int) -> None:
    pad = INDENT * level

    if depth > MAX_DEPTH:
        # Loud on purpose: a model must never be handed trimmed facts that
        # look complete. If this line appears, the payload is wrong, not the
        # budget.
        out.append(f"{pad}{key or 'value'}: <OMITTED: nested deeper than {MAX_DEPTH} levels>")
        return

    if value is None or value == "" or value == [] or value == {}:
        return                      # empty says nothing; spend no tokens on it

    if isinstance(value, dict):
        if key:
            out.append(f"{pad}{key}:")
            level += 1
            pad = INDENT * level
        for sub_key, sub_value in value.items():
            _write(str(sub_key), sub_value, level, out, depth=depth + 1)
        return

    if isinstance(value, (list, tuple)):
        _write_list(key or "items", list(value), level, out, depth=depth)
        return

    out.append(f"{pad}{key}: {_scalar(value)}" if key else f"{pad}{_scalar(value)}")


def _write_list(key: str, items: List[Any], level: int,
                out: List[str], *, depth: int) -> None:
    pad = INDENT * level
    if not items:
        return

    fields = _uniform_fields(items)
    if fields:
        # The case TOON exists for: keys once, then one line per row.
        out.append(f"{pad}{key}[{len(items)}]{{{','.join(fields)}}}:")
        for item in items:
            row = [_scalar(item.get(field)) for field in fields]
            out.append(f"{pad}{INDENT}{','.join(row)}")
        return

    if all(not isinstance(i, (dict, list, tuple)) for i in items):
        out.append(f"{pad}{key}[{len(items)}]: {','.join(_scalar(i) for i in items)}")
        return

    out.append(f"{pad}{key}[{len(items)}]:")
    for index, item in enumerate(items):
        _write(f"#{index + 1}", item, level + 1, out, depth=depth + 1)


def _uniform_fields(items: Sequence[Any]) -> Optional[List[str]]:
    """The columns of a list of rows, when the list is genuinely tabular.

    Tabular form requires every row to have the SAME keys and EVERY value to
    be scalar. Both conditions matter, and the second is the one that is easy
    to get wrong: if a row also holds a nested list - a task's `do_not`
    advice, an irrigation day's `reasons` - a table of the scalar columns
    alone would silently drop it.

    Losing a farmer's "do not spray within the pre-harvest interval" to save
    tokens is not a trade worth making, so a row with any nested value falls
    back to the verbose form.
    """
    if len(items) < 2 or not all(isinstance(i, dict) for i in items):
        return None
    first = list(items[0].keys())
    if not first or not all(_is_scalar(v) for v in items[0].values()):
        return None
    for item in items[1:]:
        if list(item.keys()) != first:
            return None
        if not all(_is_scalar(v) for v in item.values()):
            return None
    return [str(k) for k in first]


def _is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool, date, datetime)) or value is None


def _scalar(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return repr(value) if isinstance(value, float) else str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    text = str(value).replace("\n", " ").strip()
    if any(ch in text for ch in (",", ":", "{", "}", "[", "]")):
        return '"' + text.replace('"', "'") + '"'
    return text


def estimate_tokens(text: str) -> int:
    """Token count for prompt budgets; script-aware, so Hindi is not under-counted."""
    from AI_Backend.orchestration.usage import count_tokens
    return max(1, count_tokens(text))


def fit(text: str, max_tokens: int) -> str:
    """Trim to a token budget on a line boundary, and say that it was trimmed.

    Silent truncation is what makes a model confidently answer from half a
    table, so the cut is always announced in the text itself.
    """
    if estimate_tokens(text) <= max_tokens:
        return text
    budget = max_tokens * 4
    clipped = text[:budget].rsplit("\n", 1)[0]
    return clipped + "\n... (truncated to fit the context budget)"
