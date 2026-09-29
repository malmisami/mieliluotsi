"""Synthetic pilot cohort (default 50 000 people) for the impact view and the professional's client list.

The file is generated deterministically on first use and always read in chunks on the server: the browser only
ever receives one page (max 100 rows) or aggregated figures.
"""
from __future__ import annotations

import csv
import random
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from app.config import settings
from app.support.adapters.base import iter_csv_chunks

COLUMNS = [
    'asiakas_tunnus', 'ikaryhma', 'teemat', 'suunnitelman_tila', 'omahoitotehtavat_sovittu', 'omahoitotehtavat_toteutunut',
    'muistutukset', 'mikrointerventiot', 'eskalaatiot', 'aiheelliset_eskalaatiot', 'ratkaistu_ilman_eskalaatiota',
    'viive_havainnosta_toimeen_pv', 'odottaa_ammattilaista', 'hyodyllisyys',
    # automated assessments of the need for care (>= escalations), professional-confirmed ones and human-review requests
    'automaattiset_arviot', 'vahvistetut_arviot', 'pyydetyt_ammattilaisen_arviot',
]
AGE_BANDS = [('18–34', 12), ('35–49', 24), ('50–64', 32), ('65–79', 25), ('80+', 7)]
THEMES = ['verenpaine', 'kolesteroli', 'verensokeri', 'painonhallinta', 'uni ja jaksaminen']
THEME_WEIGHTS = [34, 24, 19, 13, 10]
STATUSES = [('active', 62), ('pending_professional_review', 8), ('escalated', 5), ('paused', 5), ('completed', 15), ('rejected', 5)]
STATUS_LABELS = {
    'active': 'Käynnissä', 'pending_professional_review': 'Odottaa hyväksyntää', 'escalated': 'Arvioitu automaattisesti – ammattilainen mukana',
    'paused': 'Tauolla', 'completed': 'Päättynyt', 'rejected': 'Ei otettu käyttöön',
}
MAX_PAGE_SIZE = 100


def _weighted(rng: random.Random, options: list[tuple[str, int]]) -> str:
    return rng.choices([o for o, _ in options], weights=[w for _, w in options])[0]


def generate(path: Path, size: int, seed: int = 20260923) -> None:
    rng = random.Random(seed)
    # the assessment columns draw from their own stream so the original columns stay identical for the same seed
    assessment_rng = random.Random(f'{seed}-assessments')
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle, delimiter=';')
        writer.writerow(COLUMNS)
        for index in range(1, size + 1):
            status = _weighted(rng, STATUSES)
            themes = sorted(set(rng.choices(THEMES, weights=THEME_WEIGHTS, k=rng.choice([1, 1, 2]))), key=THEMES.index)
            agreed = rng.randint(4, 26) if status != 'pending_professional_review' else 0
            done = round(agreed * rng.betavariate(5, 2.2))
            escalations = rng.choices([0, 1, 2], weights=[80, 16, 4])[0] if status != 'pending_professional_review' else 0
            appropriate = sum(1 for _ in range(escalations) if rng.random() < 0.78)
            assessments = escalations + (assessment_rng.choices([0, 1, 2, 3], weights=[45, 30, 17, 8])[0] if status != 'pending_professional_review' else 0)
            confirmed = appropriate + sum(1 for _ in range(assessments - escalations) if assessment_rng.random() < 0.2)
            human_requests = sum(1 for _ in range(assessments) if assessment_rng.random() < 0.06)
            writer.writerow([
                f'SYN-{index:06d}', _weighted(rng, AGE_BANDS), '|'.join(themes), status, agreed, done,
                rng.randint(0, 12), rng.randint(0, 10), escalations, appropriate, rng.randint(0, 6),
                round(rng.uniform(0.0, 3.5), 1), 1 if status in ('pending_professional_review', 'escalated') else 0,
                rng.choice(['', '', '3', '4', '4', '5', '5', '2']),
                assessments, confirmed, human_requests,
            ])
    tmp.replace(path)


def cohort_path() -> Path:
    path = Path(settings.SUPPORT_COHORT_PATH)
    if not path.exists() or not _has_assessment_columns(path):
        generate(path, settings.SUPPORT_COHORT_SIZE)
    return path


def _has_assessment_columns(path: Path) -> bool:
    """An older cached cohort (without the assessment columns) is regenerated with the same seed."""
    with path.open('r', encoding='utf-8') as handle:
        header = handle.readline().strip().split(';')
    return set(COLUMNS) <= set(header)


def _matches(row: dict[str, str], status: Optional[str], theme: Optional[str], age_band: Optional[str]) -> bool:
    return ((not status or row['suunnitelman_tila'] == status) and (not theme or theme in row['teemat'].split('|'))
            and (not age_band or row['ikaryhma'] == age_band))


def page(page_number: int = 1, page_size: int = 25, status: Optional[str] = None, theme: Optional[str] = None,
         age_band: Optional[str] = None) -> dict[str, Any]:
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    page_number = max(1, page_number)
    start = (page_number - 1) * page_size
    rows: list[dict[str, Any]] = []
    total = 0
    for chunk in iter_csv_chunks(cohort_path(), chunk_size=2000):
        for row in chunk:
            if not _matches(row, status, theme, age_band):
                continue
            if start <= total < start + page_size:
                rows.append({
                    'id': row['asiakas_tunnus'], 'ageBand': row['ikaryhma'], 'themes': row['teemat'].split('|'),
                    'status': row['suunnitelman_tila'], 'statusLabel': STATUS_LABELS.get(row['suunnitelman_tila'], row['suunnitelman_tila']),
                    'tasksAgreed': int(row['omahoitotehtavat_sovittu']), 'tasksDone': int(row['omahoitotehtavat_toteutunut']),
                    'escalations': int(row['eskalaatiot']), 'waitingForProfessional': row['odottaa_ammattilaista'] == '1',
                    'assessments': int(row.get('automaattiset_arviot') or 0),
                    'humanReviewRequests': int(row.get('pyydetyt_ammattilaisen_arviot') or 0),
                })
            total += 1
    return {'total': total, 'page': page_number, 'pageSize': page_size, 'pages': max(1, -(-total // page_size)), 'rows': rows,
            'filters': {'statuses': STATUS_LABELS, 'themes': THEMES, 'ageBands': [a for a, _ in AGE_BANDS]}, 'synthetic': True}


@lru_cache(maxsize=4)
def _aggregate_cached(path: str, mtime: float, size: int) -> dict[str, Any]:
    totals = {key: 0 for key in ('people', 'active', 'tasksAgreed', 'tasksDone', 'reminders', 'micro', 'escalations',
                                 'appropriate', 'resolvedWithout', 'waiting', 'ratingCount', 'ratingSum',
                                 'assessments', 'assessmentsConfirmed', 'humanReviewRequests')}
    delay_sum = 0.0
    by_status: dict[str, int] = {}
    by_theme: dict[str, int] = {}
    for chunk in iter_csv_chunks(Path(path), chunk_size=5000):
        for row in chunk:
            totals['people'] += 1
            by_status[row['suunnitelman_tila']] = by_status.get(row['suunnitelman_tila'], 0) + 1
            for theme in row['teemat'].split('|'):
                by_theme[theme] = by_theme.get(theme, 0) + 1
            totals['active'] += row['suunnitelman_tila'] == 'active'
            totals['tasksAgreed'] += int(row['omahoitotehtavat_sovittu'])
            totals['tasksDone'] += int(row['omahoitotehtavat_toteutunut'])
            totals['reminders'] += int(row['muistutukset'])
            totals['micro'] += int(row['mikrointerventiot'])
            totals['escalations'] += int(row['eskalaatiot'])
            totals['appropriate'] += int(row['aiheelliset_eskalaatiot'])
            totals['resolvedWithout'] += int(row['ratkaistu_ilman_eskalaatiota'])
            totals['waiting'] += int(row['odottaa_ammattilaista'])
            totals['assessments'] += int(row.get('automaattiset_arviot') or 0)
            totals['assessmentsConfirmed'] += int(row.get('vahvistetut_arviot') or 0)
            totals['humanReviewRequests'] += int(row.get('pyydetyt_ammattilaisen_arviot') or 0)
            delay_sum += float(row['viive_havainnosta_toimeen_pv'])
            if row['hyodyllisyys']:
                totals['ratingCount'] += 1
                totals['ratingSum'] += int(row['hyodyllisyys'])
    people = totals['people'] or 1
    return {
        'synthetic': True,
        'people': totals['people'],
        'activePlans': totals['active'],
        'selfCareTasksAgreed': totals['tasksAgreed'],
        'selfCareTasksDone': totals['tasksDone'],
        'reminders': totals['reminders'],
        'microInterventions': totals['micro'],
        'escalations': totals['escalations'],
        'escalationsAppropriate': totals['appropriate'],
        'resolvedWithoutEscalation': totals['resolvedWithout'],
        'avgDaysSignalToAction': round(delay_sum / people, 1),
        'waitingForProfessional': totals['waiting'],
        'usefulnessAvg': round(totals['ratingSum'] / totals['ratingCount'], 1) if totals['ratingCount'] else None,
        'usefulnessAnswers': totals['ratingCount'],
        'assessments': totals['assessments'],
        'assessmentsConfirmed': totals['assessmentsConfirmed'],
        'assessmentsConfirmedShare': round(totals['assessmentsConfirmed'] / totals['assessments'], 3) if totals['assessments'] else None,
        'humanReviewRequests': totals['humanReviewRequests'],
        'byStatus': [{'status': k, 'label': STATUS_LABELS.get(k, k), 'count': v} for k, v in sorted(by_status.items(), key=lambda i: -i[1])],
        'byTheme': [{'theme': k, 'count': v} for k, v in sorted(by_theme.items(), key=lambda i: -i[1])],
    }


def aggregate() -> dict[str, Any]:
    path = cohort_path()
    stat = path.stat()
    return _aggregate_cached(str(path), stat.st_mtime, stat.st_size)
