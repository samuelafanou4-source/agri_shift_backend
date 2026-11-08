"""Structured rotation-rule evaluator (§8.5). No eval/exec: a fixed table of operators."""

from __future__ import annotations

import operator
from collections.abc import Callable
from typing import Any

from app.schemas.engine import RuleHit
from app.schemas.reference import Crop, Rule, RuleCondition, Scenario

_MISSING = object()


def _cmp(fn: Callable[[Any, Any], bool]) -> Callable[[Any, Any], bool]:
    def wrapped(a: Any, b: Any) -> bool:
        try:
            return bool(fn(a, b))
        except TypeError:  # e.g. None < 0
            return False

    return wrapped


OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "eq": operator.eq,
    "neq": operator.ne,
    "lt": _cmp(operator.lt),
    "lte": _cmp(operator.le),
    "gt": _cmp(operator.gt),
    "gte": _cmp(operator.ge),
    "in": lambda a, b: a in b,
}


def _context(prev: Crop | None, nxt: Crop, scenario: Scenario) -> dict[str, dict | None]:
    return {
        "prev": prev.model_dump() if prev is not None else None,
        "next": nxt.model_dump(),
        "scenario": scenario.model_dump(),
    }


def _resolve(path: str, ctx: dict[str, dict | None]) -> Any:
    root, _, attr = path.partition(".")
    obj = ctx.get(root)
    if obj is None:  # e.g. prev absent (no history)
        return _MISSING
    return obj.get(attr, _MISSING)


def condition_matches(cond: RuleCondition, ctx: dict[str, dict | None]) -> bool:
    left = _resolve(cond.field, ctx)
    if left is _MISSING:
        return False
    if cond.op == "eq_field":
        right = _resolve(cond.value, ctx)
        return right is not _MISSING and left == right
    return OPERATORS[cond.op](left, cond.value)


def rule_matches(rule: Rule, prev: Crop | None, nxt: Crop, scenario: Scenario) -> bool:
    ctx = _context(prev, nxt, scenario)
    return all(condition_matches(c, ctx) for c in rule.all)


def matching_rules(
    rules: list[Rule], prev: Crop | None, nxt: Crop, scenario: Scenario
) -> list[RuleHit]:
    """Matched rules, in the order of the pack's rule list."""
    return [
        RuleHit(rule_id=r.rule_id, delta=r.delta, explanation_fr=r.explanation_fr)
        for r in rules
        if rule_matches(r, prev, nxt, scenario)
    ]
