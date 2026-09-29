"""Clearly SYNTHETIC Apple-Health-like daily data for the demo (source 'synthetic_demo', never shown as the user's
real Apple Health data).

Scenario over a year that ends on the demo date: about nine months of a stable everyday rhythm, then during the last
two months activity decreases, sleep shortens, the resting heart rate rises and HRV decreases slightly. Deterministic
(fixed seed), so the demo and the tests always see the same data."""
from __future__ import annotations

import math
import random
from typing import Any

from app.wellbeing.trends import shift

SEED = 46
CHANGE_DAYS = 60  # the change builds up over the last two months


def _ramp(index: int, days: int) -> float:
    """0 before the change, rising to 1 at the end; most of the change in the last month."""
    start = days - CHANGE_DAYS
    if index < start:
        return 0.0
    return min(1.0, ((index - start) / CHANGE_DAYS) ** 1.6)


def generate(end: str, days: int = 365, seed: int = SEED) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    result = []
    for index in range(days):
        day = shift(end, -(days - 1 - index))
        weekday = (index + 3) % 7  # arbitrary but fixed weekly rhythm
        weekend = weekday >= 5
        r = _ramp(index, days)
        season = math.sin(index / 365 * 2 * math.pi) * 0.04  # a little summer / winter variation
        steps = rng.gauss(9100 - 2200 * r, 1250) * (1 + season) + (900 if weekday == 5 else -600 if weekday == 6 else 0)
        sleep = rng.gauss(442 - 56 * r, 22) + (28 if weekend else 0)
        resting = rng.gauss(47.0 + 6.0 * r, 1.0)
        hrv = rng.gauss(55.0 - 11.0 * r, 4.0)
        workout = rng.random() < (0.43 - 0.29 * r)
        workout_minutes = max(15, int(rng.gauss(38, 9))) if workout else 0
        energy = 330 + steps * 0.019 + workout_minutes * 4.2 + rng.gauss(0, 35)
        row: dict[str, Any] = {
            'date': day,
            'steps': max(800, int(round(steps))),
            'sleepMinutes': int(round(min(560, max(300, sleep)))),
            'restingHeartRate': round(resting),
            'hrvMs': round(max(18.0, hrv)),
            'activeEnergyKcal': int(round(max(120, energy))),
            'workoutMinutes': workout_minutes,
            'workoutCount': 1 if workout else 0,
        }
        if rng.random() < 0.3:  # weighed about twice a week
            row['weightKg'] = round(62.0 + 0.7 * r + rng.gauss(0, 0.2), 1)
        if workout and rng.random() < 0.45:  # the watch estimates VO2 max after outdoor workouts
            row['vo2Max'] = round(46.2 - 1.1 * r + rng.gauss(0, 0.25), 1)
        result.append(row)
    return result
