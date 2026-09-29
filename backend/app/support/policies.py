"""Demo policies and the demo scenario, read once per process."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.config import BASE_DIR, settings


@lru_cache(maxsize=1)
def load_policies() -> dict:
    return json.loads(Path(settings.SUPPORT_POLICIES_PATH).read_text(encoding='utf-8'))


@lru_cache(maxsize=1)
def load_setup() -> dict:
    return json.loads(Path(settings.SUPPORT_SETUP_PATH).read_text(encoding='utf-8'))


def setup_path(relative: str) -> Path:
    return BASE_DIR / relative


def theme(theme_id: str) -> dict:
    return load_policies()['themes'][theme_id]


def action_label(action: str) -> str:
    return load_policies()['actions'].get(action, {}).get('label', action)


def action_level(action: str) -> int:
    return load_policies()['actions'].get(action, {}).get('level', 99)


def contacts_user(action: str) -> bool:
    return load_policies()['actions'].get(action, {}).get('contactsUser', False)


def forbidden_labels() -> dict[str, str]:
    return load_policies()['forbiddenActions']


def owner_label(role: str) -> str:
    return load_policies()['ownerRoles'].get(role, role)


def guide(guide_id: str) -> dict:
    return load_policies()['guides'][guide_id]


def service_contact(contact_id: str) -> dict:
    return load_policies()['serviceContacts'][contact_id]
