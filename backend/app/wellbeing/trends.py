"""Personal baseline, rolling averages, trends and meaningful-change detection over daily summaries.

Pure functions: no state, no I/O, no LLM. The user is compared with their own earlier level (the personal baseline),
not with population averages. Thresholds come from the metric catalog (policies.json: wellbeingData.metrics[].change)
and only flag a change for the agent; they never mean a medical conclusion.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

Series = list[tuple[str, float]]  # (ISO date, value), oldest first


def _day(iso: str) -> date:
    return date.fromisoformat(iso)


def shift(iso: str, days: int) -> str:
    return (_day(iso) + timedelta(days=days)).isoformat()


def metric_series(rows: list[dict[str, Any]], metric: str) -> Series:
    """The non-missing values of one metric, oldest first. Missing days are simply absent (no zeros are invented)."""
    return sorted(((row['date'], float(row[metric])) for row in rows if row.get(metric) is not None), key=lambda item: item[0])


def window(series: Series, end: str, days: int, gap: int = 0) -> Series:
    """Values in the `days`-day window that ends `gap` days before `end` (both ends inclusive)."""
    last = shift(end, -gap)
    first = shift(last, -(days - 1))
    return [(d, v) for d, v in series if first <= d <= last]


def _summary(values: Series) -> Optional[dict[str, Any]]:
    if not values:
        return None
    return {'value': sum(v for _, v in values) / len(values), 'n': len(values), 'from': values[0][0], 'to': values[-1][0]}


def calculate_rolling_average(series: Series, end: str, days: int, gap: int = 0, min_values: int = 1) -> Optional[dict[str, Any]]:
    """Mean of the values within the window; None when fewer than `min_values` days have data."""
    values = window(series, end, days, gap)
    return _summary(values) if len(values) >= min_values else None


def calculate_current(series: Series, end: str, windows: dict[str, int], kind: str) -> Optional[dict[str, Any]]:
    """The user's current level: the mean of the last `currentDays` days, or for a sparse metric (weight, VO2 max)
    the latest value within `sparseLookbackDays`."""
    if kind == 'sparse':
        recent = window(series, end, windows['sparseLookbackDays'])
        return {'value': recent[-1][1], 'n': 1, 'from': recent[-1][0], 'to': recent[-1][0]} if recent else None
    return calculate_rolling_average(series, end, windows['currentDays'], min_values=windows['minCurrentValues'])


def calculate_personal_baseline(series: Series, end: str, windows: dict[str, int], kind: str) -> Optional[dict[str, Any]]:
    """The user's own usual level: the mean of the `baselineDays` days before the latest `baselineGapDays` (so a recent
    change does not dilute its own reference). With a shorter history the earlier days before the current window are
    used, marked partial. None when there is too little history to say anything."""
    minimum = 2 if kind == 'sparse' else windows['minBaselineValues']
    values = window(series, end, windows['baselineDays'], gap=windows['baselineGapDays'])
    if len(values) >= minimum:
        return {**_summary(values), 'days': windows['baselineDays'], 'partial': False}
    earlier = [(d, v) for d, v in series if d <= shift(end, -windows['currentDays'])]
    if len(earlier) >= minimum:
        return {**_summary(earlier), 'days': (_day(earlier[-1][0]) - _day(earlier[0][0])).days + 1, 'partial': True}
    return None


def calculate_trend(series: Series, end: str, days: int) -> Optional[dict[str, Any]]:
    """Least-squares slope over the last `days` days, per week. None with fewer than a week of values."""
    values = window(series, end, days)
    if len(values) < 7:
        return None
    start = _day(values[0][0])
    xs = [(_day(d) - start).days for d, _ in values]
    ys = [v for _, v in values]
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    spread = sum((x - mean_x) ** 2 for x in xs)
    if spread == 0:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / spread
    return {'slopePerWeek': slope * 7, 'days': days, 'n': len(values)}


def _exceeds(delta: float, baseline: float, change: dict[str, float], factor: float = 1.0) -> bool:
    """Every threshold the metric defines must be exceeded (absolute units and / or a share of the baseline)."""
    checks = []
    if 'absolute' in change:
        checks.append(abs(delta) >= change['absolute'] * factor)
    if 'relative' in change and baseline:
        checks.append(abs(delta) / abs(baseline) >= change['relative'] * factor)
    return bool(checks) and all(checks)


def consecutive_days_beyond(series: Series, baseline: float, direction: str, change: dict[str, float]) -> int:
    """How many of the latest days in a row were on the same side of the baseline by at least half the threshold."""
    count = 0
    for _, value in reversed(series):
        delta = value - baseline
        if (delta > 0) != (direction == 'up') or not _exceeds(delta, baseline, change, factor=0.5):
            break
        count += 1
    return count


def detect_meaningful_change(metric: dict[str, Any], current: Optional[dict[str, Any]], baseline: Optional[dict[str, Any]],
                             series: Series) -> Optional[dict[str, Any]]:
    """A change of the current level against the personal baseline that exceeds the metric's thresholds, or None.

    kind: 'concern' when the change goes against the metric's favorable direction, 'positive' when with it and
    'neutral' for metrics without a favorable direction (weight). Only a signal for the agent, never a diagnosis."""
    if not current or not baseline:
        return None
    delta = current['value'] - baseline['value']
    change = metric.get('change', {})
    if not _exceeds(delta, baseline['value'], change):
        return None
    direction = 'up' if delta > 0 else 'down'
    favorable = metric.get('favorable', 'none')
    kind = 'neutral' if favorable == 'none' else ('positive' if favorable == direction else 'concern')
    consecutive = consecutive_days_beyond(series, baseline['value'], direction, change) if metric.get('kind') == 'daily' else 0
    # how far past the threshold, for ordering the signals of one observation (1.0 = exactly at the threshold)
    strength = max([abs(delta) / change['absolute'] if 'absolute' in change else 0,
                    abs(delta) / abs(baseline['value']) / change['relative'] if 'relative' in change and baseline['value'] else 0])
    return {
        'metric': metric['id'], 'direction': direction, 'kind': kind, 'delta': delta,
        'relative': delta / baseline['value'] if baseline['value'] else None, 'consecutiveDays': consecutive, 'strength': strength,
    }


def weekly_means(series: Series) -> Series:
    """Weekly means (dated by the week's last day) for long periods, so a year is ~52 points instead of 365."""
    if not series:
        return []
    last = _day(series[-1][0])
    buckets: dict[int, list[float]] = {}
    for d, v in series:
        buckets.setdefault((last - _day(d)).days // 7, []).append(v)
    return [(shift(series[-1][0], -7 * week), sum(values) / len(values)) for week, values in sorted(buckets.items(), reverse=True)]
