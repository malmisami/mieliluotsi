"""Loads the curated, versioned demo content and policies from data/valituki/*.json.

Rules, thresholds and weights live in data files (not in code) so they can be reviewed and changed by the people who
own them. Every value in these files is a demo policy that still needs clinical validation.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from app.config import settings
from app.valituki.models import ApprovedActivity


@lru_cache(maxsize=None)
def _load(name: str, data_dir: str) -> Any:
    return json.loads((Path(data_dir) / name).read_text(encoding='utf-8'))


def load(name: str) -> Any:
    return _load(name, settings.VALITUKI_DATA_DIR)


@lru_cache(maxsize=4)
def _activities(data_dir: str) -> tuple[ApprovedActivity, ...]:
    return tuple(ApprovedActivity(**item) for item in _load('activities.json', data_dir)['activities'])


def activities() -> list[ApprovedActivity]:
    return list(_activities(settings.VALITUKI_DATA_DIR))


def activity(activity_id: Optional[str]) -> Optional[ApprovedActivity]:
    return next((a for a in activities() if a.id == activity_id), None)


def activity_library_meta() -> dict[str, Any]:
    data = load('activities.json')
    return {'version': data['version'], 'approvalNote': data['approvalNote']}


def cbt() -> dict[str, Any]:
    return load('cbt.json')


def cbt_tool(tool_id: Optional[str]) -> Optional[dict[str, Any]]:
    return next((t for t in cbt()['tools'] if t['id'] == tool_id), None)


def matching_config() -> dict[str, Any]:
    return load('matching_config.json')


def safety_rules() -> dict[str, Any]:
    return load('safety_rules.json')


def rules() -> dict[str, Any]:
    return load('rules.json')


def seed_clients() -> dict[str, Any]:
    return load('clients.json')


def seed_therapists() -> dict[str, Any]:
    return load('therapists.json')


def cohort() -> dict[str, Any]:
    return load('cohort.json')


def client_spec(client_id: str) -> dict[str, Any]:
    return next((c for c in seed_clients()['clients'] if c['id'] == client_id), {})
