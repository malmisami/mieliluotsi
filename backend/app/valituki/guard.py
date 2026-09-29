"""Deterministic output guard for every text a language model produces for Mieliluotsi.

A text that fails is never shown: the caller uses the approved template instead and records why. The guard checks for
diagnoses and clinical claims ("Sinulla on…", "Tilasi on…"), medication advice, treatment changes, clinical urgency
decisions, invented professional reviews, dependency or anthropomorphic claims, minimising emergencies, fake precision,
more than one question and excessive length.
"""
from __future__ import annotations

import re

from app.valituki.safety import normalize

# Patterns run on the normalised text (lower case, ä → a, ö → o, å → a).
_PATTERNS: list[tuple[str, str]] = [
    (r'\bdiagno', 'diagnoosi'),
    (r'\bsinulla on (masennus|ahdistuneisuushairio|paniikkihairio|kaksisuuntainen|adhd|ptsd|traumaperainen|unettomuus|sairaus'
     r'|mielenterveyden hairio|hairio|uupumusoireyhtyma)', 'diagnoosiväite'),
    (r'\bsairastat\b', 'diagnoosiväite'),
    (r'\btilasi on\b', 'kliininen väite'),
    (r'\btilasi (on )?(pahentunut|heikentynyt|huonontunut)', 'kliininen väite'),
    (r'\b(you have|du har) (depression|anxiety disorder|ptsd|adhd|bipolar)', 'diagnoosiväite'),
    (r'\blaak(?!ar)', 'lääkitys'),
    (r'\b(annos|annost|milligramm|mg\b|tabletti|pilleri|resepti)', 'lääkitys'),
    (r'\b(medication|medicine|dose|pills?|medicin|dos)\b', 'lääkitys'),
    (r'\b(sertralii|essitalopraam|escitalopram|fluoksetii|venlafaksii|melatonii|bentso|diapam|ketiapii|mirtatsapii)',
     'lääkkeen nimi'),
    (r'\b(lopeta|lopettaa|keskeyta|keskeyttaa|jata valiin|peru|peruuta)\b[^.!?]{0,40}\b(terapia|hoito|hoidon|hoitoa|kaynti|ajan)',
     'hoidon muutos'),
    (r'\b(et tarvitse|ei tarvitse|ei kannata)\b[^.!?]{0,30}\b(terapia|hoito|hoitoa|ammattilai|apua)', 'hoidon vähättely'),
    (r'\b(vaihda|vaihtaa) (terapeuttia|hoitoa)', 'hoidon muutos'),
    (r'\b(nostin|nostan|nostanut|laskin|laskenut|muutin|muuttanut) [^.!?]{0,30}kiireellisyy', 'kiireellisyyspäätös'),
    (r'\bkiireellisyyttasi on (nostettu|muutettu)', 'kiireellisyyspäätös'),
    (r'\baina (taalla|tukenasi|sinua varten|kaytettavissa)', 'riippuvuutta lisäävä lupaus'),
    (r'\bolen aina\b', 'riippuvuutta lisäävä lupaus'),
    (r'\b(always here|here for you always|i am always)', 'riippuvuutta lisäävä lupaus'),
    (r'\bvain mina\b|\bet tarvitse muita\b|\bparempi kuin (ihmiset|terapeutti)', 'yksinoikeutta korostava'),
    (r'\b(valitan|rakastan|kaipaan) (sinua|sinusta)', 'inhimillisiä tunteita koskeva väite'),
    (r'\b(tunnen|koen) (itseni|samoin|surua|iloa)|\bminakin olen (surullinen|ahdistunut|huolissani)|\bolen huolissani\b',
     'inhimillisiä tunteita koskeva väite'),
    (r'\bymmarran (sinua )?(taysin|paremmin|kaiken)', 'liioiteltu ymmärrys'),
    (r'\b(ystavasi|kaverisi)\b', 'inhimillinen suhde'),
    (r'\b(ala soita|ei tarvitse soittaa|ei ole hataa|ei ole mitaan hataa)', 'hätätilanteen vähättely'),
    (r'\d+\s*prosent', 'näennäinen tarkkuus'),
    (r'\btodennakoisyy', 'näennäinen tarkkuus'),
    # Guided CBT: the model may help the client look at a thought, never tell them their thought or feeling is wrong.
    (r'\b(ajatuksesi|ajatus|tunteesi|tunne) on (vaara|virheellinen|jarjeton|tyhma|turha|naurettava)', 'mitätöivä ilmaus'),
    (r'\bolet vaarassa\b', 'mitätöivä ilmaus'),
    (r'\b(ala|lakkaa) (ajattele|ajattelemasta|murehdi|murehtimasta|jannita|jannittamasta)', 'mitätöivä ilmaus'),
    (r'\bsinun (taytyy|pitaa) vain\b', 'mitätöivä ilmaus'),
    (r'\bei ole (mitaan )?syyta (jannittaa|pelata|pelkaa|ahdistua)', 'mitätöivä ilmaus'),
]
_REVIEW_CLAIM = re.compile(r'\b(ammattilainen|koordinaattori|terapeutti) on (jo )?(tarkistanut|kaynyt lapi|arvioinut|nahnyt)')
_COMPILED = [(re.compile(pattern), label) for pattern, label in _PATTERNS]
# Checked on the raw text: normalisation removes symbols such as "%".
_RAW = [(re.compile(r'\d+\s*%'), 'näennäinen tarkkuus')]

MAX_LENGTH = 700


def check(text: str | None, *, max_questions: int = 1, max_length: int = MAX_LENGTH,
          review_exists: bool = False) -> list[str]:
    """Return the list of violations (empty when the text may be shown)."""
    if not text or not text.strip():
        return ['tyhjä vastaus']
    violations: list[str] = []
    normalized = normalize(text)
    for pattern, label in _COMPILED:
        if pattern.search(normalized) and label not in violations:
            violations.append(label)
    for pattern, label in _RAW:
        if pattern.search(text) and label not in violations:
            violations.append(label)
    if not review_exists and _REVIEW_CLAIM.search(normalized):
        violations.append('väite ammattilaisen tarkistuksesta, jota ei ole')
    if text.count('?') > max_questions:
        violations.append('useampi kuin yksi kysymys')
    if len(text) > max_length:
        violations.append('liian pitkä')
    return violations
