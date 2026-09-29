"""Deterministic interpretation used by DEMO_AI_MODE (and as the fallback of LIVE_AI_MODE) in the conversational intake.

Everything produced here is a *proposal*: it is shown to the client as "Ymmärsinkö tilanteesi oikein?" and becomes
stored information only after the client explicitly approves it. The rules only look at what the client wrote; nothing
is inferred about demographics or health status beyond the client's own words.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from app.valituki.labels import FORMATS, LANGUAGES, TIMES, WEEKDAYS, join_fi
from app.valituki.safety import normalize

OPENING_KEY = 'reason'
OPENING_QUESTION = 'Kerro omin sanoin, miksi hait apua.'

QUESTIONS: dict[str, str] = {
    'change': 'Mitä haluaisit eniten muuttaa?',
    'difficult_times': 'Milloin olo on yleensä vaikein?',
    'helped_before': 'Millainen tuki on auttanut sinua aiemmin?',
    'exercises': 'Toivotko terapialta enemmän konkreettisia harjoituksia vai tutkivaa keskustelua?',
    'challenge': 'Toivotko, että terapeutti haastaa sinua aktiivisesti, vai että hän auttaa lähinnä pohtimaan?',
    'practical': 'Mitä käytännön asioita meidän kannattaa huomioida – esimerkiksi kieli, etä- tai lähivastaanotto ja sopivat ajat?',
}
PLAN: list[str] = list(QUESTIONS)
MAX_FOLLOW_UPS = 6
MIN_ANSWERS_TO_FINISH = 2

WORK = r'\btyo|\btoi(ssa|hin|den|ta)\b|palaver|esity|toimisto'
SLEEP = r'nuku|nukk|nukah|\bun(i|en|ta|et)\b|youn|unettom|valvo'

GOAL_RULES: list[tuple[str, list[str], str, list[str]]] = [
    ('trauma', [r'onnettomu|trauma|painajai'],
     'Haluan pystyä käsittelemään vaikeaa kokemusta niin, ettei pelko rajoita arkea.', ['trauma', 'anxiety']),
    ('work_anxiety', [r'ahdist|jannit|pelk|pelo', WORK],
     'Haluan pystyä hallitsemaan työtilanteisiin liittyvää ahdistusta.', ['anxiety', 'work_stress']),
    ('burnout', [r'uupu|loppuun', WORK], 'Haluan palautua työuupumuksesta ja jaksaa työssä.', ['burnout', 'work_stress']),
    ('transition', [r'\beron\b|\bero\b|erosin|avioero|muutto|muutin|elamanmuuto'],
     'Haluan löytää suunnan elämänmuutoksen keskellä.', ['life_transitions', 'relationships']),
    ('grief', [r'kuoli|surun|\bsuru|menetys|menetin|menetyksen'], 'Haluan oppia elämään menetyksen kanssa.', ['grief', 'mood']),
    ('anxiety', [r'ahdist|jannit|paniik|pelk'], 'Haluan oppia hallitsemaan ahdistusta arjessa.', ['anxiety']),
    ('loneliness', [r'yksinai'], 'Haluan vähentää yksinäisyyden tunnetta ja löytää yhteyttä muihin.', ['loneliness']),
    ('mood', [r'mieliala|alakulo|masentu|ei mikaan|kiinnosta'], 'Haluan löytää keinoja matalan mielialan kanssa.', ['mood']),
    ('stress', [r'stress|kuormit|kiire'], 'Haluan saada kuormituksen hallintaan.', ['stress']),
    ('sleep', [SLEEP], 'Haluan nukkua paremmin.', ['sleep']),
]

SECONDARY_RULES: list[tuple[str, str, str, list[str]]] = [
    ('sleep', SLEEP, 'Haluan nukkua paremmin.', ['sleep']),
    ('loneliness', r'yksinai', 'Haluan vähentää yksinäisyyden tunnetta.', ['loneliness']),
    ('stress', r'stress|kuormit', 'Haluan saada kuormituksen hallintaan.', ['stress']),
    ('mood', r'joita odottaa|jotain mukavaa|iloa', 'Haluan löytää arkeen asioita, joita odottaa.', ['mood']),
]

CARD_TITLES = {
    'goal': 'Tavoite',
    'working_style': 'Työskentelytapa',
    'practical': 'Käytännön toiveet',
    'difficult_times': 'Vaikeimmat hetket',
    'helped_before': 'Aiemmin auttanut',
}


def question_text(key: str) -> str:
    return OPENING_QUESTION if key == OPENING_KEY else QUESTIONS[key]


def next_question_key(asked: list[str]) -> Optional[str]:
    remaining = [key for key in PLAN if key not in asked]
    if len([k for k in asked if k != OPENING_KEY]) >= MAX_FOLLOW_UPS or not remaining:
        return None
    return remaining[0]


def demo_acknowledgement(key: Optional[str], answer: str) -> str:
    """A short, neutral acknowledgement. It reflects the client's words without interpreting their health."""
    text = normalize(answer or '')
    if not text:
        return 'Selvä, ohitetaan tämä kysymys.'
    if key == OPENING_KEY:
        if re.search(WORK, text):
            return 'Kiitos, että kerroit. Vaikuttaa siltä, että työhön liittyvät tilanteet ovat tässä keskeisiä.'
        if re.search(SLEEP, text):
            return 'Kiitos, että kerroit. Vaikuttaa siltä, että myös uni on kärsinyt.'
        return 'Kiitos, että kerroit.'
    return {
        'change': 'Kiitos. Tästä voi muodostua tavoite – tarkistat sen lopuksi itse.',
        'difficult_times': 'Kiitos. Näiden hetkien tunnistaminen auttaa ajoittamaan tukea oikein.',
        'helped_before': 'Hyvä tietää, mikä on auttanut.',
        'exercises': 'Kiitos, tämä auttaa löytämään sinulle sopivan työskentelytavan.',
        'challenge': 'Selvä.',
    }.get(key or '', 'Kiitos.')


# --- extraction -------------------------------------------------------------------------------------------------------

def _match_all(patterns: list[str], text: str) -> bool:
    return all(re.search(pattern, text) for pattern in patterns)


def _sentences(text: str, limit: int = 2, max_chars: int = 200) -> str:
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    short = ' '.join(parts[:limit]).strip()
    return short if len(short) <= max_chars else short[: max_chars - 1].rstrip() + '…'


def extract_goals(answers: dict[str, str]) -> Optional[dict[str, Any]]:
    stated = normalize(' '.join(answers.get(k, '') for k in ('reason', 'change')))
    if not stated:
        return None
    primary = None
    for key, patterns, sentence, topics in GOAL_RULES:
        if _match_all(patterns, stated):
            primary = {'rule': key, 'text': sentence, 'topics': topics}
            break
    if primary is None:
        own = _sentences(answers.get('change') or answers.get('reason') or '', 1, 140)
        primary = {'rule': 'own_words', 'text': own, 'topics': []}
    everything = normalize(' '.join(answers.get(k, '') for k in ('reason', 'change', 'difficult_times')))
    secondary = []
    for key, pattern, sentence, topics in SECONDARY_RULES:
        if set(topics) & set(primary['topics']) or not re.search(pattern, everything):
            continue
        if key == 'sleep' and primary['rule'] == 'work_anxiety':
            sentence = 'Haluan, ettei ahdistus vie yöunia ennen työpäiviä.'
        secondary.append({'rule': key, 'text': sentence, 'topics': topics})
        if len(secondary) == 2:
            break
    return {'primary': primary, 'secondary': secondary}


def extract_working_style(answers: dict[str, str]) -> dict[str, Optional[str]]:
    exercises_text = normalize(answers.get('exercises', ''))
    challenge_text = normalize(answers.get('challenge', ''))
    context = normalize(' '.join(answers.get(k, '') for k in ('exercises', 'helped_before', 'change')))

    concrete = bool(re.search(r'konkreett|harjoit|kaytannon|keino|vinkk|tyokalu|lista|ohje', exercises_text))
    talk = bool(re.search(r'keskust|pohti|puhu|tutki', exercises_text))
    if re.search(r'molemmat|kumpikin|seka ', exercises_text):
        exercises = 'both'
    elif concrete and talk:
        exercises = 'conversation' if re.search(r'enemman (keskust|pohti|puhu)', exercises_text) else \
            'concrete' if re.search(r'enemman (konkreet|harjoit)', exercises_text) else 'both'
    elif concrete:
        exercises = 'concrete'
    elif talk:
        exercises = 'conversation'
    else:
        exercises = None

    if re.search(r'selke|struktur|jarjest|etenemi|suunnitelm|rutiin|lista', context):
        structure = 'structured'
    elif re.search(r'vapaa|tutkiv|pohti', context):
        structure = 'exploratory'
    else:
        structure = None

    if re.search(r'pohti|kuuntel|rauhalli|lempe|ei liikaa haast|mieluummin auttaa', challenge_text):
        approach = 'reflective'
    elif re.search(r'haast', challenge_text):
        approach = 'directive'
    else:
        approach = None

    if re.search(r'ei (valitehtav|kotitehtav|tehtav)|en halua (valitehtav|kotitehtav|tehtav)', context):
        homework = 'no'
    elif re.search(r'valitehtav|kotitehtav|tehtavat(kin)? sopi', context):
        homework = 'yes'
    else:
        homework = None
    return {'structure': structure, 'exercises': exercises, 'approach': approach, 'homework': homework}


def working_style_text(style: dict[str, Optional[str]]) -> str:
    parts = []
    exercises, structure = style.get('exercises'), style.get('structure')
    if exercises == 'concrete' and structure == 'structured':
        parts.append('Pidät konkreettisista harjoitteista ja selkeästä etenemisestä.')
    elif exercises == 'concrete':
        parts.append('Pidät konkreettisista harjoitteista.')
    elif exercises == 'conversation' and structure == 'exploratory':
        parts.append('Toivot enemmän keskustelua ja yhteistä pohtimista kuin valmiita harjoituksia.')
    elif exercises == 'conversation':
        parts.append('Toivot enemmän keskustelua kuin harjoituksia.')
    elif exercises == 'both':
        parts.append('Sinulle sopivat sekä harjoitukset että keskustelu.')
    elif structure == 'structured':
        parts.append('Pidät selkeästä etenemisestä.')
    elif structure == 'exploratory':
        parts.append('Pidät vapaammasta, tutkivasta etenemisestä.')
    if style.get('approach') == 'directive':
        parts.append('Terapeutti saa myös haastaa sinua.')
    elif style.get('approach') == 'reflective':
        parts.append('Toivot rauhallista otetta, jossa terapeutti auttaa ennemmin pohtimaan kuin haastaa.')
    if style.get('homework') == 'yes':
        parts.append('Välitehtävät sopivat sinulle.')
    elif style.get('homework') == 'no':
        parts.append('Et toivo välitehtäviä.')
    return ' '.join(parts)


WEEKDAY_PATTERNS = [r'maanantai', r'tiistai', r'keskiviikko', r'torstai', r'perjantai', r'lauantai', r'sunnuntai']


def extract_practical(answers: dict[str, str], municipality: str) -> dict[str, Any]:
    text = normalize(answers.get('practical', ''))
    languages = [code for code, pattern in (('fi', r'suome|suomi'), ('sv', r'ruotsi|svenska|pa svenska'),
                                             ('en', r'englanti|english')) if re.search(pattern, text)]
    language_stated = bool(languages)
    if not languages:
        languages = ['fi']
    remote = bool(re.search(r'\beta|etavastaanot|etana|video|verkossa|kotoa', text))
    in_person = bool(re.search(r'lahivastaanot|lahella|paikan paalla|vastaanotolla|kasvokkain', text))
    fmt = 'either' if remote == in_person else 'remote' if remote else 'in_person'
    days = [index for index, pattern in enumerate(WEEKDAY_PATTERNS) if re.search(pattern, text)]
    times = [key for key, pattern in (('morning', r'aamupai|aamuisin|aamulla|\baamu'),
                                      ('daytime', r'iltapai|paivalla|paivaisin|paivasaikaan|\bpaiva'),
                                      ('evening', r'ilta(?!pai)|\billa|illoin|iltaisin')) if re.search(pattern, text)]
    return {'languages': languages, 'languageStated': language_stated, 'format': fmt, 'location': municipality,
            'days': days, 'times': times, 'accessibilityNeeds': []}


def practical_text(practical: dict[str, Any]) -> str:
    place = f' ({practical["location"]})' if practical['format'] != 'remote' and practical.get('location') else ''
    parts = [FORMATS[practical['format']] + place]
    parts.append(join_fi([LANGUAGES[code] for code in practical['languages']], 'tai'))
    if practical.get('times'):
        times = join_fi([f'{TIMES[t]}ajat' if t != 'evening' else 'ilta-ajat' for t in practical['times']], 'tai')
        if practical.get('days'):
            times += f' ({join_fi([WEEKDAYS[d] for d in practical["days"]], "tai")})'
        parts.append(times)
    elif practical.get('days'):
        parts.append(join_fi([WEEKDAYS[d] for d in practical['days']], 'tai'))
    return ', '.join(parts) + '.'


def extract(answers: dict[str, str], municipality: str) -> list[dict[str, Any]]:
    """Deterministic proposals ("Ymmärsinkö tilanteesi oikein?")."""
    proposals: list[dict[str, Any]] = []
    goals = extract_goals(answers)
    if goals:
        text = goals['primary']['text']
        proposals.append({
            'category': 'goal', 'title': CARD_TITLES['goal'], 'text': text,
            'structured': {'primary': {'text': text, 'topics': goals['primary']['topics']},
                           'secondary': [{'text': g['text'], 'topics': g['topics']} for g in goals['secondary']],
                           'hope': answers.get('change', '').strip()},
            'derivedFrom': [k for k in ('reason', 'change') if answers.get(k)],
            'userWords': [answers[k].strip() for k in ('change',) if answers.get(k)],
        })
    style = extract_working_style(answers)
    if any(style.values()):
        proposals.append({'category': 'working_style', 'title': CARD_TITLES['working_style'], 'text': working_style_text(style),
                          'structured': style, 'derivedFrom': [k for k in ('exercises', 'challenge', 'helped_before') if answers.get(k)],
                          'userWords': [answers[k].strip() for k in ('exercises', 'challenge') if answers.get(k)]})
    practical = extract_practical(answers, municipality)
    proposals.append({'category': 'practical', 'title': CARD_TITLES['practical'], 'text': practical_text(practical),
                      'structured': practical, 'derivedFrom': ['practical'] if answers.get('practical') else [],
                      'userWords': [answers['practical'].strip()] if answers.get('practical') else []})
    if answers.get('difficult_times', '').strip():
        proposals.append({'category': 'difficult_times', 'title': CARD_TITLES['difficult_times'],
                          'text': 'Olo on usein vaikein: ' + _lower_first(_sentences(answers['difficult_times'], 1, 160)),
                          'structured': {}, 'derivedFrom': ['difficult_times'],
                          'userWords': [answers['difficult_times'].strip()]})
    if answers.get('helped_before', '').strip():
        proposals.append({'category': 'helped_before', 'title': CARD_TITLES['helped_before'],
                          'text': 'Aiemmin on auttanut: ' + _lower_first(_sentences(answers['helped_before'], 2, 180)),
                          'structured': {}, 'derivedFrom': ['helped_before'], 'userWords': [answers['helped_before'].strip()]})
    return proposals


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text and not text[:2].isupper() else text
