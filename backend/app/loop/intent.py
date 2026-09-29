"""Intent router for the companion chat.

Safety-relevant intents (emergency, diagnosis, medication change) are always detected with deterministic
rules first; the LLM cannot override them. Then the care-need intents of the automated assessment of the need
for care and its urgency (a request for a professional's assessment, a symptom description) are detected with
deterministic rules, also before the LLM. Other intents come from the LLM when enabled, otherwise from keyword
rules.
"""
from __future__ import annotations

import re

from app.loop import family_history, llm

INTENTS = (
    'EXPLAIN_FINDING',
    'EXPLAIN_OBSERVATION',
    'GET_STATUS',
    'HEALTH_OVERVIEW',
    'ADD_CONTEXT',
    'CREATE_SUMMARY',
    'CREATE_FOLLOWUP',
    'RESOLVE_TASK',
    'GENERAL_HEALTH_QUESTION',
    'DIAGNOSIS_REQUEST',
    'MEDICATION_CHANGE_REQUEST',
    'EMERGENCY_OR_URGENT',
    'CARE_NEED_ASSESSMENT',
    'HUMAN_ASSESSMENT_REQUEST',
    'SELF_CARE_MEMORY',
    'NEXT_STEP',
    'SELF_CARE_DIRECTION',
    'WELLBEING_DATA',
)
SAFETY_INTENTS = ('EMERGENCY_OR_URGENT', 'MEDICATION_CHANGE_REQUEST', 'DIAGNOSIS_REQUEST')
# Checked with deterministic rules right after the safety intents and before the LLM: the LLM may name these
# intents, but the rules win (the urgency class itself always comes from the rule engine, never from the LLM).
DETERMINISTIC_FIRST = ('HUMAN_ASSESSMENT_REQUEST', 'CARE_NEED_ASSESSMENT')

_EMERGENCY = [
    r'rintakipu', r'kipu(a)? rinnassa', r'puristaa rinnassa', r'puristava kipu',
    r'hengitysvaike', r'hengenahdistu', r'en saa henkeä', r'vaikea hengittää',
    r'tajuton', r'menetti tajun', r'pyörry', r'pyörtyi', r'halvausoire', r'puhe puuroutu', r'toispuolei',
    r'\b112\b', r'hätätilan', r'ambulanssi',
    # same emergency vocabulary as the automation policy's TRI-EMERG-001 symptom rule
    r'tajunnan', r'halvaus', r'puhe(vaikeu|häiri)', r'toispuol', r'kouristu', r'voimakas päänsärky',
]
# 'lääk' is a medicine, 'lääkäri' is a doctor ("pitäisikö mennä lääkäriin?" is a care-need question)
_MEDICATION_TOPIC = r'lääk(?!äri)|statiin|annos|tablet|\bmg\b|resept'
_MEDICATION_CHANGE = r'aloit|lopet|muut|vaihd|nost|lisä|vähen|pitäisikö|voinko|saanko|kannattaako|tarvitsenko|otanko|jätä|jättää|puolit'
_DIAGNOSIS = [
    r'onko minulla\b.{0,40}(sairau|tauti|\bfh\b|familiaalinen|perinnöllinen|hyperkolesterolemia)',
    r'sairastanko', r'sairastunko', r'diagnoos', r'diagnosoi', r'mikä minulla on',
    r'onko tämä (sairaus|tauti)', r'familiaalinen hyperkolesterolemia',
    r'saanko (sydänkohtauksen|infarktin|sairauden)',
    r'(kuinka|miten) (suuri|todennäköi)', r'riskiprosent', r'todennäköisyy', r'monen prosentin',
]

# The user exercises the right to an assessment made by a healthcare professional.
_HUMAN_ASSESSMENT = [
    r'haluan (ammattilaisen|ammattihenkilön|ihmisen|hoitajan|lääkärin) (tekemän )?(hoidon tarpeen )?arvio',
    r'haluan puhua (hoitajan|lääkärin|ammattilaisen) kanssa',
    r'pyydän (ammattilaisen|ammattihenkilön|hoitajan|lääkärin) (tekemän )?arvio',
    r'pyydä ammattilaisen arvio',
]
# A symptom description or an explicit request for an assessment of the need for care and its urgency.
_CARE_NEED = [
    r'\boire', r'särky', r'särke', r'kipu', r'kipeä', r'kivu', r'huimau', r'tykyty', r'turvotu', r'väsy',
    r'onko (tämä|se) kiireellis',
    r'pitäisikö (minun )?(mennä|hakeutua) (lääkäri|vastaanoto|hoitoon|terveysasema)',
    r'arvioi(da)? hoidon tarve', r'hoidon tarpeen arvio',
    r'tarvitsenko (lääkäri|hoitoa)',
]

# The self-care continuity engine: what was agreed / this week's step / is self-care enough. Recognised with rules right
# after the care-need intents, so the answer always comes from the plan's own memory and rules.
_CONTINUITY: list[tuple[str, list[str]]] = [
    ('SELF_CARE_DIRECTION', [
        r'riittää(kö)? (minun )?omahoi', r'omahoito(ni)? (ei )?riitä', r'muutetaanko suunnitelma', r'jatketaanko omahoito',
        r'(pitäisikö|pitääkö|kannattaako) (minun )?(muuttaa|päivittää) suunnitelma', r'tarvi(taanko|tsenko) ammattila',
    ]),
    ('NEXT_STEP', [
        r'seuraava (pieni )?askel', r'askeleeni', r'tämän viikon (askel|tavoite|kokeilu)', r'viikon askel', r'pieni askel',
        r'mitä (minun )?(pitäisi|kannattaa|kannattaisi) tehdä (tällä viikolla|nyt|seuraavaksi)', r'mitä teen (tällä viikolla|seuraavaksi)',
    ]),
    ('SELF_CARE_MEMORY', [
        r'mitä (me )?(olemme|olimme|ollaan|on|oli) (sovittu|sopineet)', r'mitä sovi(mme|ttiin)', r'sovitut asiat', r'mitä muistat',
        r'muistatko',
        r'mitä olen (jo )?kokeillut', r'mikä (minulla )?(on )?toimi(i|nut)', r'toimii minulla', r'tavoitteeni',
        r'milloin .{0,40}(tarkistetaan|tarkistus|kontrolli)', r'mitä (minun )?(pitää|pitäisi|kuuluu) seurata', r'mitä seuraan',
    ]),
]

# Hyvinvointidata (Apple Health): questions about the user's own trends are answered from the compact summary
_WELLBEING_DATA = [
    r'hyvinvointidat', r'apple health', r'apple watch', r'\bleposyk', r'\bhrv\b', r'sykevälivaihtelu', r'palautum',
    r'\bune(n|ni|sta)?\b.{0,40}(määrä|kehit|muuttu|trendi)', r'nukkumi', r'nukun\b', r'nukkunut', r'askelmäär', r'askeleet\b',
    r'askelia\b', r'aktiivisuu', r'vo2', r'mistä (tämä |se )?muutos (voisi |voi )?johtu',
]

_KEYWORD_RULES: list[tuple[str, list[str]]] = [
    ('RESOLVE_TASK', [
        r'(olen|olin|oon) (jo )?(puhunut|keskustellut|käynyt|kysynyt)', r'(asia|tämä) on (jo )?käsitelty',
        r'merkitse .{0,20}käsitellyksi', r'lääkäri (on )?(jo )?(katsonut|arvioinut|käynyt läpi)',
    ]),
    ('CREATE_FOLLOWUP', [r'muistuta', r'muistutus']),
    ('CREATE_SUMMARY', [r'yhteenve', r'lääkärille', r'vastaanotolle', r'ammattilaiselle']),
    ('HEALTH_OVERVIEW', [
        r'kokonaiskuva', r'kokonaisuutena', r'yleiskatsaus', r'kehittynyt', r'ajan mittaan', r'suhteessa aiemp',
        r'ennaltaehkäis', r'ennalta ehkäis',
        r'(miten|mitä) (minä )?voisin (ehkäistä|parantaa|vähentää|tehdä)', r'mitä (minun )?kannattaisi tehdä',
        # "kiinnittää huomiota" is everyday Finnish, not a question about a rule-engine observation
        r'kiinnit\w* (erityistä )?huomio', r'mihin (asioihin )?.{0,25}huomio',
    ]),
    ('EXPLAIN_OBSERVATION', [r'\bmiksi\b', r'\bhuomio', r'nousi esiin', r'relevant']),
    ('EXPLAIN_FINDING', [r'ldlr', r'löydö', r'\bgeeni', r'variant', r'mitä .{0,30}tarkoittaa']),
    ('GET_STATUS', [r'\btila\b', r'tilanne', r'tilanteeni', r'status', r'mitä uutta', r'avoim', r'seuranta', r'tehtäv', r'mitä tiedät']),
]

_FAMILY_CONTEXT = r'\b(isä|isi|äiti|äid|veli|velje|sisar|sisko|poika|poja|tytär|tyttäre|isoisä|isoäiti|isovanhem|suvu|suku|lähisuvu|lähisukulai)'


def detect_safety_intent(text: str) -> str | None:
    lowered = text.lower()
    if any(re.search(p, lowered) for p in _EMERGENCY):
        return 'EMERGENCY_OR_URGENT'
    if re.search(_MEDICATION_TOPIC, lowered) and re.search(_MEDICATION_CHANGE, lowered):
        return 'MEDICATION_CHANGE_REQUEST'
    if any(re.search(p, lowered) for p in _DIAGNOSIS):
        return 'DIAGNOSIS_REQUEST'
    return None


def _looks_like_family_answer(text: str) -> bool:
    return bool(re.search(_FAMILY_CONTEXT, text.lower())) and family_history.parse(text) is not None


def detect_care_need_intent(text: str) -> str | None:
    """HUMAN_ASSESSMENT_REQUEST before CARE_NEED_ASSESSMENT; a family-history answer ("isälläni oli ...") is
    context about relatives, not the user's own symptoms."""
    lowered = text.lower()
    if any(re.search(p, lowered) for p in _HUMAN_ASSESSMENT):
        return 'HUMAN_ASSESSMENT_REQUEST'
    if _looks_like_family_answer(text):
        return None
    if any(re.search(p, lowered) for p in _CARE_NEED):
        return 'CARE_NEED_ASSESSMENT'
    return None


def detect_continuity_intent(text: str) -> str | None:
    """SELF_CARE_DIRECTION / NEXT_STEP / SELF_CARE_MEMORY: the continuity engine's own questions."""
    lowered = text.lower()
    for intent, patterns in _CONTINUITY:
        if any(re.search(p, lowered) for p in patterns):
            return intent
    return None


def detect_wellbeing_intent(text: str) -> str | None:
    lowered = text.lower()
    return 'WELLBEING_DATA' if any(re.search(p, lowered) for p in _WELLBEING_DATA) else None


def keyword_intent(text: str, awaiting_missing_info: bool) -> str:
    lowered = text.lower()
    looks_like_family_answer = _looks_like_family_answer(text)
    if looks_like_family_answer or (awaiting_missing_info and family_history.parse(text) is not None):
        return 'ADD_CONTEXT'
    if re.search(r'\bldl\b[^?]{0,20}\d', lowered) and '?' not in lowered:
        return 'ADD_CONTEXT'
    for intent, patterns in _KEYWORD_RULES:
        if any(re.search(p, lowered) for p in patterns):
            return intent
    if awaiting_missing_info and '?' not in lowered:
        return 'ADD_CONTEXT'
    return 'GENERAL_HEALTH_QUESTION'


def classify(text: str, awaiting_missing_info: bool = False) -> tuple[str, str]:
    """Returns (intent, method)."""
    safety = detect_safety_intent(text)
    if safety:
        return safety, 'deterministic_safety_rules'
    care_need = detect_care_need_intent(text)
    if care_need:
        return care_need, 'deterministic_care_need_rules'
    continuity = detect_continuity_intent(text)
    if continuity:
        return continuity, 'deterministic_continuity_rules'
    wellbeing = detect_wellbeing_intent(text)
    if wellbeing:
        return wellbeing, 'deterministic_wellbeing_rules'

    if llm.enabled():
        llm_intent = llm.classify_intent(text, INTENTS)
        if llm_intent in INTENTS:
            # A family-history answer to the agent's own question stays ADD_CONTEXT
            if awaiting_missing_info and llm_intent in ('GENERAL_HEALTH_QUESTION', 'GET_STATUS') and family_history.parse(text):
                return 'ADD_CONTEXT', 'llm + awaiting_question_rule'
            return llm_intent, 'llm'
        return keyword_intent(text, awaiting_missing_info), 'keyword_rules (LLM-fallback)'
    return keyword_intent(text, awaiting_missing_info), 'keyword_rules'
