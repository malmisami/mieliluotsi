from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from threading import RLock
from typing import Iterator

from app.config import settings
from app.loop.evidence import evidence_entry, finding_from_evidence, load_profile
from app.loop.models import STATE_VERSION, HealthEvent, LoopState

_lock = RLock()


def add_days(iso_date: str, days: int) -> str:
    return (date.fromisoformat(iso_date) + timedelta(days=days)).isoformat()


def next_id(state: LoopState, prefix: str) -> str:
    state.counters[prefix] = state.counters.get(prefix, 0) + 1
    return f'{prefix}-{state.counters[prefix]:04d}'


def initial_state() -> LoopState:
    profile = load_profile()
    state = LoopState(profile=profile['profile'], currentDate=profile['startDate'])
    for finding_id in profile['findingIds']:
        entry = evidence_entry(finding_id)
        if entry:
            state.findings.append(finding_from_evidence(entry))
    for raw in profile['initialEvents']:
        state.events.append(HealthEvent(id=next_id(state, 'evt'), extractedData={}, **raw))

    from app.loop.agent import start_monitoring  # local import: agent depends on this module
    from app.support.bootstrap import bootstrap_support  # local import: support depends on this module

    for finding_id in profile.get('initialMonitoringFindingIds', []):
        start_monitoring(state, finding_id, preset=True)
    bootstrap_support(state)
    return state


def _path() -> Path:
    return Path(settings.LOOP_STATE_PATH)


def load_state() -> LoopState:
    with _lock:
        path = _path()
        if path.exists():
            try:
                loaded = LoopState.model_validate_json(path.read_text(encoding='utf-8'))
                if loaded.version == STATE_VERSION:
                    return loaded
            except ValueError:
                pass  # corrupt demo state: start over
            # outdated layout (e.g. the earlier single-finding demo): rebuild from the demo data
        state = initial_state()
        save_state(state)
        return state


def save_state(state: LoopState) -> None:
    with _lock:
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(state.model_dump(), ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(path)


@contextmanager
def transaction() -> Iterator[LoopState]:
    """Load, mutate and save the demo state under one lock."""
    with _lock:
        state = load_state()
        yield state
        save_state(state)


def reset_state() -> LoopState:
    with _lock:
        state = initial_state()
        save_state(state)
        return state


def clear_state() -> LoopState:
    """Remove everything the app stored (the user's DNA analysis results, monitorings started from it, own entries,
    chat, survey answers, links). The health care records are not the app's data: they are read again from the
    source systems, so Terveystiedot always shows them."""
    with _lock:
        state = initial_state()
        save_state(state)
        return state
