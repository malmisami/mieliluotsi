from __future__ import annotations

import re
from typing import Optional

DISCLAIMER_FI = (
    'Tämä ei ole diagnoosi tai hoitosuositus. '
    'Älä muuta lääkitystä ilman terveydenhuollon ammattilaisen arviota.'
)

# Deterministic guard for any user-facing text produced by an LLM or a template.
# The fixed disclaimer is shown separately and is not passed through this check.
_URGENCY_PATTERN = r'\b(?:kiireellis(?!yy)|kiireesti|heti lääkäriin|välittömästi|päivystykseen|hätä)'
# With an allowed urgency class the text may name the emergency number, but must not invent urgency otherwise.
_URGENCY_PATTERN_WITH_CLASS = r'\b(?:kiireellis(?!yy)|kiireesti|heti lääkäriin|välittömästi|päivystykseen|hätä(?!numero))'
_FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
    (r'\d+(?:[.,]\d+)?\s*(?:%|prosent)', 'riskiprosentti tai prosenttiluku'),
    (r'\bsinulla\s+on\s+(?:todettu|diagnosoitu|sairaus|tauti|familiaalinen|perinnöllinen)', 'diagnoosiväite'),
    (r'\bsairastat\b', 'diagnoosiväite'),
    (r'\bdiagnosoi', 'diagnosointi'),
    (r'\b(?:aloita|aloittakaa|lopeta|lopettakaa|vaihda|nosta|laske|lisää|vähennä|muuta)\b[^.]{0,60}\b(?:lääk|annos|statiin|tablet|valmiste)', 'lääkitysohje'),
    (r'\bstatiini', 'lääkkeen nimeäminen'),
    (r'\bannost', 'annostelu'),
    (r'\bsinun\s+(?:pitää|täytyy|kannattaa)\s+(?:aloittaa|lopettaa|muuttaa)', 'hoito-ohje'),
    (_URGENCY_PATTERN, 'kiireellisyysarvio'),
]

# Fixed phrases every automated assessment text may use regardless of the allowed class (112 is always allowed).
_FIXED_ASSESSMENT_PHRASES = ('soita hätänumeroon 112', 'Päivystysapu 116 117', 'samana päivänä')
# Inflected forms of a class label that the rule engine's own texts use (e.g. "hätätilanteeseen" for "Hätätilanne").
_CLASS_LABEL_STEMS = {'emergency': (r'hätätilan\w*',)}


def _allowed_phrases(allowed_urgency: str) -> list[str]:
    """The allowed class's label, care need and handling time from the automation policy (rules decide, never the LLM)."""
    from app.support.policies import load_policies  # local import: the loop package stays free of file IO at import time

    for item in load_policies().get('automation', {}).get('urgencyClasses', []):
        if item['id'] == allowed_urgency:
            return [item['label'], item['careNeedLabel'], item['handlingTime']]
    raise ValueError(f'Tuntematon kiireellisyysluokka: {allowed_urgency}')


def _strip_allowed(text: str, allowed_urgency: str) -> str:
    """Remove the phrases the allowed class may legitimately use before the urgency pattern is applied."""
    phrases = _allowed_phrases(allowed_urgency) + list(_FIXED_ASSESSMENT_PHRASES)
    for phrase in sorted(phrases, key=len, reverse=True):
        text = re.sub(re.escape(phrase), ' ', text, flags=re.IGNORECASE)
    for stem in _CLASS_LABEL_STEMS.get(allowed_urgency, ()):
        text = re.sub(stem, ' ', text, flags=re.IGNORECASE)
    return text


def check_text(text: str, allowed_urgency: Optional[str] = None) -> dict:
    """Deterministic safety check. With `allowed_urgency` (an automated-assessment class id) the class's own label,
    care-need and handling-time phrases and the fixed '112' / 'Päivystysapu 116 117' phrases are allowed; any other
    urgency wording is still blocked. Without it the behaviour is unchanged."""
    violations = []
    urgency_text = _strip_allowed(text, allowed_urgency) if allowed_urgency else text
    for pattern, label in _FORBIDDEN_PATTERNS:
        if pattern == _URGENCY_PATTERN:
            if re.search(_URGENCY_PATTERN_WITH_CLASS if allowed_urgency else pattern, urgency_text, flags=re.IGNORECASE):
                violations.append(label)
        elif re.search(pattern, text, flags=re.IGNORECASE):
            violations.append(label)
    return {'passed': not violations, 'violations': violations}
