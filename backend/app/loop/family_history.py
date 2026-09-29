"""Free text about family history -> validated structured data.

Only these enum values are accepted, whether the data came from the LLM or from the rule-based parser.
"""
from __future__ import annotations

import re

RELATIONS_FI = {
    'father': 'isä',
    'mother': 'äiti',
    'brother': 'veli',
    'sister': 'sisar',
    'son': 'poika',
    'daughter': 'tytär',
    'grandparent': 'isovanhempi',
    'other_relative': 'muu sukulainen',
}

CONDITIONS_FI = {
    'myocardial_infarction': 'sydäninfarkti',
    'coronary_artery_disease': 'sepelvaltimotauti',
    'coronary_procedure': 'sepelvaltimotoimenpide (esim. pallolaajennus tai ohitusleikkaus)',
    'stroke': 'aivoinfarkti tai aivohalvaus',
    'high_cholesterol': 'korkea kolesteroli',
    'none_reported': 'ei tiedossa olevia sydän- ja verisuonisairauksia',
}

CONDITION_CATEGORY = {
    'myocardial_infarction': 'cardiovascular_disease',
    'coronary_artery_disease': 'cardiovascular_disease',
    'coronary_procedure': 'cardiovascular_disease',
    'stroke': 'cardiovascular_disease',
    'high_cholesterol': 'high_cholesterol',
    'none_reported': 'none_reported',
}

_RELATION_PATTERNS = [
    (r'\bisovanhemp|\bisoisä|\bisoäiti|\bpappa|\bmummo|\bmummi|\bukki', 'grandparent'),
    (r'\bisä|\bisi\b|\bfaija', 'father'),
    (r'\bäiti|\bäid|\bmutsi', 'mother'),
    (r'\bveli|\bveljeni|\bveljellä', 'brother'),
    (r'\bsisar|\bsisko', 'sister'),
    (r'\bpoika|\bpoikani|\bpojalla', 'son'),
    (r'\btytär|\btyttäre', 'daughter'),
    (r'\bsetä|\beno\b|\btäti|\bserkku', 'other_relative'),
]

_CONDITION_PATTERNS = [
    (r'infarkt|sydänkohtau', 'myocardial_infarction'),
    (r'aivoinfarkt|aivohalvau', 'stroke'),
    (r'sepelvaltimotau|rintakipukohtau|angina', 'coronary_artery_disease'),
    (r'pallolaajennu|ohitusleikkau|stentti', 'coronary_procedure'),
    (r'kolesterol|hyperkolesterol', 'high_cholesterol'),
]

_NEGATIVE = r'\b(ei ole ollut|ei ollut|ei ole|eikä|ei kenelläkään|ei tiedossa|ei mitään)\b'


def parse(text: str) -> dict | None:
    lowered = text.lower()
    # "aivoinfarkti" must not be read as a heart attack
    condition = None
    if re.search(r'aivoinfarkt|aivohalvau', lowered):
        condition = 'stroke'
    else:
        condition = next((code for pattern, code in _CONDITION_PATTERNS if re.search(pattern, lowered)), None)

    if re.search(_NEGATIVE, lowered) and (condition is None or re.search(r'\bei\b[^.]{0,40}(sairau|infarkt|kolesterol)', lowered)):
        return {
            'eventType': 'family_history',
            'relation': None,
            'condition': 'none_reported',
            'conditionCategory': 'none_reported',
            'ageAtEvent': None,
            'source': 'user_reported',
        }

    relation = next((code for pattern, code in _RELATION_PATTERNS if re.search(pattern, lowered)), None)
    if not relation or not condition:
        return None
    age_match = re.search(r'(\d{1,3})\s*-?\s*(?:vuotiaana|v\.?\b|vuoden iässä|vuotta vanhana)', lowered)
    return {
        'eventType': 'family_history',
        'relation': relation,
        'condition': condition,
        'conditionCategory': CONDITION_CATEGORY[condition],
        'ageAtEvent': int(age_match.group(1)) if age_match else None,
        'source': 'user_reported',
    }


def validate(data: dict | None) -> dict | None:
    """Accept only known enum values and a plausible age. Returns normalised data or None."""
    if not isinstance(data, dict):
        return None
    condition = data.get('condition')
    if condition not in CONDITIONS_FI:
        return None
    relation = data.get('relation')
    if condition != 'none_reported' and relation not in RELATIONS_FI:
        return None
    age = data.get('ageAtEvent')
    if age is not None:
        try:
            age = int(age)
        except (TypeError, ValueError):
            return None
        if not 0 < age < 120:
            return None
    return {
        'eventType': 'family_history',
        'relation': relation if condition != 'none_reported' else None,
        'condition': condition,
        'conditionCategory': CONDITION_CATEGORY[condition],
        'ageAtEvent': age,
        'source': 'user_reported',
    }


def describe(data: dict) -> list[str]:
    if data['condition'] == 'none_reported':
        return ['lähisukulaisilla ei tiedossa olevia sydän- ja verisuonisairauksia tai korkeaa kolesterolia']
    lines = [f"lähisukulainen: {RELATIONS_FI[data['relation']]}", f"tapahtuma: {CONDITIONS_FI[data['condition']]}"]
    lines.append(f"ikä tapahtumahetkellä: {data['ageAtEvent']} vuotta" if data.get('ageAtEvent') else 'ikä tapahtumahetkellä: ei kerrottu')
    return lines


def display_value(data: dict) -> str:
    if data['condition'] == 'none_reported':
        return 'Ei tiedossa olevia sairauksia lähisuvussa'
    age = f", {data['ageAtEvent']} v" if data.get('ageAtEvent') else ''
    return f"{RELATIONS_FI[data['relation']]}: {CONDITIONS_FI[data['condition']]}{age}"
