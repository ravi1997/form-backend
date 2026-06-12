"""Helpers for reading and writing form access-policy payloads."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def policy_value(policy: Any, *keys: str, default: Any = None) -> Any:
    if policy is None:
        return default

    for key in keys:
        if isinstance(policy, Mapping):
            if key in policy and policy[key] is not None:
                return policy[key]
        else:
            if hasattr(policy, key):
                value = getattr(policy, key)
                if value is not None:
                    return value
    return default


def policy_list(policy: Any, *keys: str) -> list[str]:
    value = policy_value(policy, *keys, default=[])
    if not value:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return [item for item in value if item is not None]
    return [value]


def to_policy_dict(policy: Any) -> dict[str, Any]:
    if policy is None:
        return {}
    if isinstance(policy, Mapping):
        return dict(policy)
    if hasattr(policy, "to_mongo"):
        try:
            return dict(policy.to_mongo().to_dict())
        except Exception:
            return {}
    if hasattr(policy, "__dict__"):
        return {k: v for k, v in vars(policy).items() if not k.startswith("_")}
    return {}
