"""The metric catalog, windows and monitoring areas from the demo policy, and Finnish formatting of the values.

User-facing numbers are always absolute (bpm, ms, min, steps): no percentages, the same rule as every other text of
the agent (safety.check_text rejects percentage figures)."""
from __future__ import annotations

from typing import Any, Optional

from app.support import policies

# how each metric is spoken of: the possessive subject of a sentence, a plain noun, and the verbs for up / down
PHRASES: dict[str, dict[str, str]] = {
    'steps': {'subject': 'Askelmääräsi', 'noun': 'askelmäärä', 'partitive': 'askelmäärää', 'up': 'on kasvanut', 'down': 'on vähentynyt'},
    'sleepMinutes': {'subject': 'Unesi määrä', 'noun': 'unen määrä', 'partitive': 'unen määrää', 'up': 'on lisääntynyt', 'down': 'on vähentynyt'},
    'restingHeartRate': {'subject': 'Leposykkeesi', 'noun': 'leposyke', 'partitive': 'leposykettä', 'up': 'on noussut', 'down': 'on laskenut'},
    'hrvMs': {'subject': 'Sykevälivaihtelusi (HRV)', 'noun': 'HRV', 'partitive': 'HRV:tä', 'up': 'on noussut', 'down': 'on laskenut'},
    'activeEnergyKcal': {'subject': 'Aktiivinen energiankulutuksesi', 'noun': 'aktiivinen energiankulutus', 'partitive': 'aktiivista energiankulutusta', 'up': 'on kasvanut',
                         'down': 'on vähentynyt'},
    'workoutMinutes': {'subject': 'Liikuntasuoritustesi määrä', 'noun': 'liikuntasuoritusten määrä', 'partitive': 'liikuntasuorituksia', 'up': 'on kasvanut',
                       'down': 'on vähentynyt'},
    'weightKg': {'subject': 'Painosi', 'noun': 'paino', 'partitive': 'painoa', 'up': 'on noussut', 'down': 'on laskenut'},
    'vo2Max': {'subject': 'VO2 max -arvosi', 'noun': 'VO2 max', 'partitive': 'VO2 max -arvoa', 'up': 'on noussut', 'down': 'on laskenut'},
}
PER_DAY = {'steps': '/päivä', 'sleepMinutes': '/yö', 'activeEnergyKcal': '/päivä', 'workoutMinutes': '/päivä'}


def config() -> dict[str, Any]:
    return policies.load_policies().get('wellbeingData', {})


def metrics() -> list[dict[str, Any]]:
    return list(config().get('metrics', []))


def metric(metric_id: str) -> Optional[dict[str, Any]]:
    return next((m for m in metrics() if m['id'] == metric_id), None)


def windows() -> dict[str, int]:
    return dict(config().get('windows', {}))


def areas() -> list[dict[str, Any]]:
    return list(config().get('monitoringAreas', []))


def source_label(source: Optional[str]) -> str:
    return config().get('sources', {}).get(source or '', 'Apple Health')


def _thousands(value: float) -> str:
    return f'{int(round(value)):,}'.replace(',', ' ')


def format_value(metric_id: str, value: Optional[float], with_unit: bool = True) -> str:
    """'8 421', '7 h 18 min', '49 bpm', '62,1 kg' - Finnish formatting, no percentages."""
    if value is None:
        return '–'
    definition = metric(metric_id) or {}
    style = definition.get('format', 'integer')
    if style == 'duration':
        minutes = int(round(value))
        return f'{minutes // 60} h {minutes % 60:02d} min'
    text = f'{value:.1f}'.replace('.', ',') if style == 'decimal1' else _thousands(value)
    unit = definition.get('unit', '')
    if not with_unit or not unit or metric_id == 'steps':
        return text
    return f'{text} {unit}'


def format_delta(metric_id: str, delta: float) -> str:
    """A signed change in the metric's own unit: '+6 bpm', '−41 min/yö', '−2 200 askelta/päivä'."""
    definition = metric(metric_id) or {}
    sign = '+' if delta > 0 else '−'
    magnitude = abs(delta)
    if definition.get('format') == 'duration' or metric_id == 'sleepMinutes':
        text = f'{int(round(magnitude))} min'
    elif definition.get('format') == 'decimal1':
        text = f'{magnitude:.1f}'.replace('.', ',') + f" {definition.get('unit', '')}".rstrip()
    else:
        text = f"{_thousands(magnitude)} {definition.get('unit', '')}".rstrip()
    return f'{sign}{text}{PER_DAY.get(metric_id, "")}'
