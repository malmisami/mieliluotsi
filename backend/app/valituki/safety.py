"""Deterministic Safety Engine.

Levels:
  0 – normal support
  1 – additional check-in suggested
  2 – human review recommended
  3 – immediate safety information displayed

Signals: deterministic phrase rules (data/valituki/safety_rules.json), structured answers (a very low 1/5 mood), the
explicit "Tarvitsen apua nyt" action. An optional language-model hint is an *additional* signal only: the final level
is the maximum of the deterministic level and the hint, so a model can raise a level but never lower a deterministic
trigger.

The phrase rules are intentionally conservative (negations are not interpreted): a false alarm shows help contacts, a
missed signal could hide a risk. The rules are a demo policy and require clinical validation.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

from app.valituki import content
from app.valituki.models import SafetyTrigger

LEVEL_LABELS = {
    0: 'Tavallinen tuki',
    1: 'Lisä-check-in ehdotettu',
    2: 'Ammattilaisen tarkistus suositeltu',
    3: 'Välittömät turvallisuusohjeet näytetty',
}

# A model's advisory hint mapped onto the same scale. Used only to raise a level.
AI_HINT_LEVELS = {'NONE': 0, 'REVIEW': 2, 'URGENT': 3}

EXPLICIT_HELP_RULE = 'SAF-L3-EXPLICIT-HELP'

SAFETY_CONTACTS = [
    {'id': 'emergency', 'label': 'Välitön hätätilanne', 'action': 'soita 112', 'number': '112', 'tel': '112',
     'when': 'Jos olet välittömässä vaarassa tai hengenvaara uhkaa.'},
    {'id': 'paivystysapu', 'label': 'Kiireellinen terveysongelma', 'action': 'Päivystysapu 116117', 'number': '116117',
     'tel': '116117', 'when': 'Kiireellinen terveysneuvonta ja ohjaus oikeaan hoitopaikkaan.'},
    {'id': 'mieli', 'label': 'MIELI Kriisipuhelin', 'action': '09 2525 0111', 'number': '09 2525 0111', 'tel': '0925250111',
     'when': 'Keskusteluapua kriisissä.'},
]

SAFETY_SCREEN = {
    'title': 'Tarvitsetko apua juuri nyt?',
    'notEmergency': 'Mieliluotsi ei ole päivystyspalvelu eikä tätä keskustelua seurata jatkuvasti.',
    'intro': 'Jos olet vaarassa tai tarvitset apua heti, ota yhteyttä suoraan:',
    'demoNote': 'Demo: ammattilaisen työjonoon syntyi synteettinen hälytys. Mieliluotsi ei ole ottanut yhteyttä hätäkeskukseen '
                'tai muihin palveluihin.',
    'dismiss': 'Olen lukenut ohjeet – palaa Mieliluotsiin',
}

SAFETY_REPLY = ('Haluan varmistaa, että saat apua heti. Mieliluotsi ei ole päivystyspalvelu eikä tätä keskustelua seurata '
                'jatkuvasti. Välittömässä hätätilanteessa soita 112. Kiireellisessä terveysongelmassa Päivystysapu 116117. '
                'MIELI Kriisipuhelin 09 2525 0111.')

LEVEL2_CLIENT_TEXT = ('Kiitos, että kerroit. Pyysin ammattilaista katsomaan tilannettasi. Tämä havainto odottaa ammattilaisen '
                      'tarkistusta. Jos tarvitset apua heti, soita 112 tai Päivystysapuun 116117.')


@dataclass
class SafetyResult:
    deterministic_level: int
    ai_hint: Optional[str]
    ai_level: int
    final_level: int
    triggers: list[SafetyTrigger] = field(default_factory=list)

    @property
    def label(self) -> str:
        return LEVEL_LABELS[self.final_level]


def normalize(text: str) -> str:
    """Lower case, strip diacritics (ä → a, ö → o, å → a) and punctuation, collapse whitespace."""
    decomposed = unicodedata.normalize('NFKD', text.lower())
    ascii_text = ''.join(ch for ch in decomposed if not unicodedata.combining(ch))
    ascii_text = re.sub(r"[^a-z0-9' -]+", ' ', ascii_text)
    return re.sub(r'\s+', ' ', ascii_text).strip()


@lru_cache(maxsize=4)
def _compiled(version: str) -> list[tuple[dict, list[re.Pattern]]]:
    rules = content.safety_rules()
    return [(rule, [re.compile(pattern) for pattern in rule['patterns']]) for rule in rules['phraseRules']]


def evaluate_text(text: Optional[str]) -> list[SafetyTrigger]:
    """Phrase rules. The trigger stores the rule and category, never the client's full text."""
    if not text or not text.strip():
        return []
    normalized = normalize(text)
    triggers: list[SafetyTrigger] = []
    for rule, patterns in _compiled(content.safety_rules()['version']):
        if any(pattern.search(normalized) for pattern in patterns):
            triggers.append(SafetyTrigger(source='phrase_rule', ruleId=rule['id'], level=int(rule['level']),
                                          category=rule['category'], detail='Tunnistettu ilmaus tekstissä'))
    return triggers


def evaluate_structured(*, mood: Optional[int] = None) -> list[SafetyTrigger]:
    floor = content.safety_rules()['structured']['moodFloor']
    if mood is not None and mood <= int(floor['threshold']):
        return [SafetyTrigger(source='structured_answer', ruleId=floor['ruleId'], level=int(floor['level']),
                              category='Erittäin matala vointi', detail=f'Vointi {mood}/5')]
    return []


def explicit_help_trigger() -> SafetyTrigger:
    return SafetyTrigger(source='explicit_action', ruleId=EXPLICIT_HELP_RULE, level=3, category='Asiakas pyysi apua heti',
                         detail='Painike "Tarvitsen apua nyt"')


def assess(triggers: list[SafetyTrigger], ai_hint: Optional[str] = None,
           ai_next_action: Optional[str] = None) -> SafetyResult:
    """Combine deterministic triggers with the optional model hint. The model can only raise the level."""
    deterministic = max((t.level for t in triggers if t.source != 'ai_hint'), default=0)
    ai_level = AI_HINT_LEVELS.get((ai_hint or 'NONE').upper(), 0)
    if ai_next_action == 'SAFETY_FLOW':
        ai_level = max(ai_level, 3)
    final = max(deterministic, ai_level)
    all_triggers = [t for t in triggers if t.source != 'ai_hint']
    if ai_level > 0:
        all_triggers.append(SafetyTrigger(source='ai_hint', ruleId='AI-HINT', level=ai_level,
                                          category='Kielimallin lisäsignaali (neuvoa-antava)',
                                          detail=f'safetyHint={ai_hint or "NONE"}, suggestedNextAction={ai_next_action or "NONE"}'))
    return SafetyResult(deterministic_level=deterministic, ai_hint=ai_hint, ai_level=ai_level, final_level=final,
                        triggers=all_triggers)
