"""Optional Claude integration for narrow, bounded text tasks.

The LLM never classifies variants, makes a diagnosis, decides on medication, invents sources, sets a
clinical threshold, sets or changes the urgency class of the automated assessment of the need for care (it only
restates the class the rule engine gave it verbatim) or changes an agent / plan state. Every LLM text in an
assessment context is checked with safety.check_text(text, allowed_urgency=<class>) by the caller. It only turns free-form text into
structured fields, classifies a message into predefined categories, rewrites already-made decisions or
approved guidance into plain Finnish, and drafts summaries for professionals from given facts.
Every failure returns None so the caller uses the predefined templates.
"""
from __future__ import annotations

import json
import logging

from app.config import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    'Olet OmaGenomi Loop -demosovelluksen tekstiavustaja. Kaikki data on synteettistä. '
    'Päätökset on jo tehty deterministisillä säännöillä; sinä et muuta niitä. '
    'Älä tee diagnoosia, älä anna lääkitys- tai hoito-ohjeita, älä nimeä lääkkeitä, '
    'älä esitä riskiprosentteja tai muita prosenttilukuja äläkä mainitse lähteitä, joita ei ole annettu syötteessä. '
    'Kiireellisyysluokka tulee aina sääntöpohjaisesta arviosta ja annetaan syötteessä; toista se sellaisenaan, älä muuta äläkä arvioi sitä itse. '
    'Kirjoita selkeää, rauhallista yleiskieltä suomeksi.'
)

_EVENT_SCHEMA = {
    'type': 'object',
    'properties': {
        'type': {'type': 'string', 'enum': ['lab_result', 'vital_sign', 'medication', 'research_update', 'free_text']},
        'code': {'type': 'string', 'description': 'LDL, BP, MED_NEW, EVIDENCE_REVIEW or OTHER'},
        'displayName': {'type': 'string'},
        'value': {'type': ['string', 'number', 'null']},
        'unit': {'type': ['string', 'null']},
    },
    'required': ['type', 'code', 'displayName', 'value', 'unit'],
    'additionalProperties': False,
}


_last_call_failed = False


def enabled() -> bool:
    return settings.LOOP_LLM_PROVIDER == 'anthropic'


def status() -> dict:
    return {
        'provider': settings.LOOP_LLM_PROVIDER,
        'enabled': enabled(),
        'model': settings.LOOP_LLM_MODEL if enabled() else None,
        'lastCallFailed': enabled() and _last_call_failed,
    }


def _mark(failed: bool) -> None:
    global _last_call_failed
    _last_call_failed = failed


def _call(prompt: str, output_schema: dict | None = None) -> str | None:
    if not enabled():
        return None
    try:
        import anthropic
    except ImportError:
        logger.warning('anthropic package not installed; using templates')
        _mark(True)
        return None

    request: dict = {
        'model': settings.LOOP_LLM_MODEL,
        'max_tokens': 2000,
        'system': _SYSTEM_PROMPT,
        'messages': [{'role': 'user', 'content': prompt}],
        'thinking': {'type': 'adaptive'},
        'betas': ['server-side-fallback-2026-07-01'],
        'fallbacks': 'default',
    }
    output_config: dict = {'effort': 'low'}
    if output_schema:
        output_config['format'] = {'type': 'json_schema', 'schema': output_schema}
    request['output_config'] = output_config

    try:
        client = anthropic.Anthropic(timeout=float(settings.LOOP_LLM_TIMEOUT_SECONDS), max_retries=1)
        response = client.beta.messages.create(**request)
    except anthropic.APIConnectionError:
        logger.warning('LLM connection failed; using templates')
        _mark(True)
        return None
    except anthropic.APIStatusError as exc:
        logger.warning('LLM API error %s; using templates', exc.status_code)
        _mark(True)
        return None
    except Exception:  # missing credentials, SDK/parameter mismatch etc. must never break the demo
        logger.exception('LLM call failed; using templates')
        _mark(True)
        return None

    if response.stop_reason in ('refusal', 'max_tokens'):
        _mark(True)
        return None
    text = ''.join(block.text for block in response.content if block.type == 'text').strip()
    _mark(not text)
    return text or None


def extract_event(raw_text: str) -> dict | None:
    text = _call(
        'Muuta seuraava synteettinen terveysteksti rakenteiseksi tapahtumaksi. '
        'Älä päättele onko arvo poikkeava. Jos kyse ei ole LDL-, verenpaine-, lääkitys- tai tutkimustiedosta, käytä code=OTHER.\n\n'
        f'Teksti: {raw_text}',
        output_schema=_EVENT_SCHEMA,
    )
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) and all(key in data for key in _EVENT_SCHEMA['required']) else None


def explain_decision(decision: dict) -> str | None:
    return _call(
        'Kirjoita 2–4 virkkeen käyttäjäystävällinen selitys alla olevasta, jo tehdystä rakenteisesta päätöksestä. '
        'Kerro miksi huomio syntyi ja että tiedot kannattaa käydä läpi ammattilaisen kanssa. '
        'Palauta pelkkä teksti.\n\n' + json.dumps(decision, ensure_ascii=False)
    )


def draft_summary(summary: dict) -> str | None:
    return _call(
        'Kirjoita terveydenhuollon ammattilaiselle lyhyt (3–5 virkettä) asiallinen johdanto alla olevista synteettisistä tiedoista. '
        'Käytä vain annettuja tietoja. Palauta pelkkä teksti.\n\n' + json.dumps(summary, ensure_ascii=False)
    )


def draft_full_summary(summary: dict) -> str | None:
    """Companion to draft_summary(), but spans ALL of the user's actively monitored findings and the
    full health timeline instead of one triggered observation."""
    return _call(
        'Kirjoita terveydenhuollon ammattilaiselle lyhyt (4–6 virkettä) asiallinen johdanto alla olevista '
        'synteettisistä tiedoista. Yhdistä geneettiset löydökset ja terveystapahtumien aikajana toisiinsa: '
        'kerro lyhyesti mitkä aikajanan tapahtumat liittyvät mihinkin löydökseen ja mitkä eivät liity '
        'suoraan mihinkään niistä. Kerro kunkin löydöksen kohdalla, onko sille annetuissa tiedoissa '
        'numeerinen seurattava mittari (esim. laboratoriotulos, jolla on yksikkö) ja miten se on '
        'muuttunut ajan mittaan, jos useampia mittauksia on annettu - jos mittauksia ei ole, sano niin '
        'suoraan äläkä arvaile arvoa. Mainitse lopuksi lyhyesti, mitä lisätietoa tai -seurantaa (esim. '
        'laboratoriokoe) kannattaisi harkita annettujen puuttuvien tietojen perusteella. Käytä vain '
        'annettuja tietoja, älä keksi mitään äläkä tee diagnoosia. Palauta pelkkä teksti.\n\n'
        + json.dumps(summary, ensure_ascii=False)
    )


def answer_general_health_question(text: str) -> str | None:
    """A general, educational answer to a health question unrelated to the user's own monitoring
    context. Not personalized: does not reference the user's findings, events or history."""
    return _call(
        'Käyttäjä esitti yleisen terveyskysymyksen, joka ei liity hänen omaan seurantaansa. Vastaa siihen '
        'yleisluontoisesti ja opettavaisesti 2–5 virkkeellä. Älä viittaa käyttäjän omiin tietoihin, sillä sinulla '
        'ei ole niitä käytössä tähän vastaukseen. Muistuta lyhyesti lopussa, että kyseessä on yleistieto eikä '
        'henkilökohtainen terveysneuvonta, ja että oma tilanne kannattaa käydä läpi terveydenhuollon ammattilaisen kanssa. '
        'Palauta pelkkä teksti.\n\n' + f'Kysymys: {text}'
    )


# --- Hyvinvointikumppani ---------------------------------------------------------

def classify_intent(text: str, intents: tuple[str, ...]) -> str | None:
    result = _call(
        'Luokittele käyttäjän viesti yhteen sallituista intenteistä. Älä vastaa viestiin.\n'
        'EXPLAIN_FINDING = pyytää selitystä geneettisestä löydöksestä; '
        'EXPLAIN_OBSERVATION = kysyy miksi huomio syntyi tai mihin asioihin kannattaa kiinnittää huomiota; '
        'GET_STATUS = kysyy seurannan tilaa; '
        'HEALTH_OVERVIEW = pyytää laajaa kokonaiskuvaa tilanteesta ajan mittaan, ei muodollista lääkäriyhteenvetoa; '
        'ADD_CONTEXT = kertoo uutta terveys- tai sukutietoa; '
        'CREATE_SUMMARY = pyytää yhteenvetoa ammattilaiselle; CREATE_FOLLOWUP = pyytää muistutusta; '
        'RESOLVE_TASK = kertoo asian olevan jo käsitelty; GENERAL_HEALTH_QUESTION = muu terveyskysymys; '
        'DIAGNOSIS_REQUEST = pyytää diagnoosia tai sairastumisen todennäköisyyttä; '
        'MEDICATION_CHANGE_REQUEST = kysyy lääkityksen aloittamisesta, lopettamisesta tai annoksesta; '
        'EMERGENCY_OR_URGENT = kuvaa akuutteja oireita; '
        'CARE_NEED_ASSESSMENT = kuvaa omia oireitaan tai kysyy, pitäisikö hakeutua hoitoon (hoidon tarpeen arvio); '
        'HUMAN_ASSESSMENT_REQUEST = pyytää ammattilaisen (hoitajan tai lääkärin) tekemää arviota; '
        'SELF_CARE_MEMORY = kysyy, mitä on sovittu, mitkä ovat tavoitteet, mitä on jo kokeiltu tai milloin asia tarkistetaan; '
        'NEXT_STEP = kysyy tämän viikon pientä askelta tai mitä tehdä seuraavaksi; '
        'SELF_CARE_DIRECTION = kysyy, riittääkö omahoito vai tarvitaanko ammattilaista; '
        'WELLBEING_DATA = kysyy omasta hyvinvointidatastaan (uni, leposyke, HRV, askeleet, aktiivisuus, Apple Health).\n\n'
        f'Viesti: {text}',
        output_schema={
            'type': 'object',
            'properties': {'intent': {'type': 'string', 'enum': list(intents)}},
            'required': ['intent'],
            'additionalProperties': False,
        },
    )
    if not result:
        return None
    try:
        intent = json.loads(result).get('intent')
    except (json.JSONDecodeError, AttributeError):
        return None
    return intent if intent in intents else None


def extract_family_history(text: str, relations: list[str], conditions: list[str]) -> dict | None:
    result = _call(
        'Muuta käyttäjän kertoma synteettinen sukuhistoriatieto rakenteiseksi. Käytä vain sallittuja arvoja. '
        'Jos käyttäjä kertoo, ettei lähisuvussa ole sairauksia, käytä condition=none_reported ja relation=null. '
        'Jos ikää ei kerrota, ageAtEvent=null. Älä päättele mitään, mitä tekstissä ei sanota.\n\n'
        f'Teksti: {text}',
        output_schema={
            'type': 'object',
            'properties': {
                'relation': {'anyOf': [{'type': 'string', 'enum': relations}, {'type': 'null'}]},
                'condition': {'type': 'string', 'enum': conditions},
                'ageAtEvent': {'type': ['integer', 'null']},
            },
            'required': ['relation', 'condition', 'ageAtEvent'],
            'additionalProperties': False,
        },
    )
    if not result:
        return None
    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def explain_for_chat(user_context: dict, focus: dict) -> str | None:
    """Rewrite an already-made structured decision for the user. Input is only the bounded UserContext."""
    return _call(
        'Alla on käyttäjän rajattu UserContext ja kohta, joka pitää selittää. Kirjoita 2–4 lyhyttä virkettä '
        'selkeää suomea. Käytä vain UserContextin tietoja. Älä muuta tiloja, älä tee diagnoosia, älä anna '
        'lääkitys- tai hoito-ohjeita, älä arvioi kiireellisyyttä äläkä keksi lähteitä. Palauta pelkkä teksti.\n\n'
        + json.dumps({'userContext': user_context, 'focus': focus}, ensure_ascii=False)
    )


def summarize_health_overview(context: dict) -> str | None:
    """A proactive, holistic synthesis of the user's genetic monitoring, health timeline and basic
    profile, ending in general preventive suggestions. Used for both the GET_STATUS and HEALTH_OVERVIEW
    intents in companion._overview() - reads as a companion connecting the pieces over time, not a bare
    monitoring-status readout. Input is the bounded UserContext plus a small profile block."""
    return _call(
        'Olet ennakoiva terveyskumppani. Alla on käyttäjän koko synteettinen tilanne: geneettinen seuranta, '
        'terveystapahtumien aikajana ja perustiedot (ikä, pituus, paino). Kirjoita lyhyt vastaus kahdessa '
        'osassa, yhteensä enintään noin 8 virkettä.\n\n'
        '1) Yhteenveto (2–4 virkettä): yhdistä seuranta ja aikajana lyhyesti toisiinsa - esimerkiksi miten '
        'aiemmat mittaukset tai tapahtumat suhteutuvat geneettiseen löydökseen ja sen seurantaan, ja nosta '
        'esiin havaittavissa olevat muutokset tai trendit ajan mittaan, jos niitä on annetuissa tiedoissa.\n\n'
        '2) Ehdotukset (2–3 lyhyttä kohtaa): ehdota näiden tietojen pohjalta yleisellä tasolla pysyviä '
        'ennaltaehkäiseviä toimia, esimerkiksi ruokavalioon, liikuntaan tai kotimittausten jatkamiseen '
        'liittyen. Ehdotusten tulee olla yleisiä elämäntapavinkkejä, ei henkilökohtaista hoito-ohjetta: älä '
        'anna lääkitysohjeita, älä tee diagnoosia äläkä arvioi kiireellisyyttä.\n\n'
        'Älä keksi tietoja, joita alla ei ole. Päätä lyhyeen muistutukseen, että tarkempi, henkilökohtainen '
        'arvio ja ehdotusten sovittaminen omaan tilanteeseen kuuluu terveydenhuollon ammattilaiselle. '
        'Palauta pelkkä teksti, ei otsikoita eikä markdown-muotoilua.\n\n' + json.dumps(context, ensure_ascii=False)
    )


def explain_wellbeing_trends(context: dict) -> str | None:
    """Hyvinvointidata in plain words from the bounded UserContext (its wellbeingData block is a compact summary against
    the personal baseline, never the daily history). Data, interpretation and the next step apart; no diagnosis."""
    return _call(
        'Alla on käyttäjän rajattu konteksti. Sen wellbeingData-osa on hyvinvointidatan (Apple Health tai synteettinen testidata) '
        'tiivis yhteenveto: viimeisten 7 päivän taso, oma perustaso ja muutokset sekä seuranta-alueet. Kirjoita enintään 5 virkettä: '
        '1) mitä datassa näkyy annetuilla luvuilla ja yksiköillä, 2) että muutokselle voi olla monta selitystä eikä data kerro syytä, '
        '3) ehdota, että muutosta katsotaan yhdessä tai seurataan viikon ajan. Älä tee diagnoosia, älä nimeä sairauksia, älä arvioi '
        'kiireellisyyttä, älä anna hoito- tai lääkitysohjeita äläkä käytä prosentteja. Palauta pelkkä teksti.\n\n'
        + json.dumps(context, ensure_ascii=False)
    )


# --- Agenttinen hyvinvointikumppani (support plans) -------------------------------------------------------

def draft_escalation_summary(facts: dict) -> str | None:
    """Draft the narrative part of a structured escalation for the responsible professional. The facts are
    bounded (plan, rule, observed change, agent actions, the user's answers, the rule-based urgency class) - no name,
    no raw records, no DNA. The draft must restate facts['urgencyLabel'] verbatim; the caller (support.escalation)
    rejects a draft that does not contain it or fails check_text(text, allowed_urgency=<class>)."""
    label = facts.get('urgencyLabel')
    restate = (f'Automaattisen hoidon tarpeen arvion kiireellisyysluokka on "{label}". Mainitse se tiivistelmässä täsmälleen '
               'tässä muodossa (sanasta sanaan), älä muuta, tulkitse tai arvioi sitä itse. ') if label else \
        'Älä arvioi kiireellisyyttä (se on annettu säännöstä). '
    return _call(
        'Kirjoita vastuuammattilaiselle 3–5 virkkeen asiallinen tiivistelmä alla olevasta synteettisestä '
        'seurantatilanteesta. Kerro miksi tilanne ohjattiin ammattilaiselle, mitä on havaittu, mitä agentti on jo '
        'tehnyt ja mitä käyttäjä on vastannut. Käytä vain annettuja tietoja. Älä tee diagnoosia, älä ehdota hoitoa '
        'tai lääkitystä äläkä keksi arvoja. ' + restate + 'Palauta pelkkä teksti.\n\n'
        + json.dumps(facts, ensure_ascii=False)
    )


def plain_language(approved_text: str) -> str | None:
    """Rewrite a professional-approved self-care guide into plain Finnish without adding or removing advice."""
    return _call(
        'Muokkaa alla oleva ammattilaisen hyväksymä omahoito-ohje selkokieliseksi. Älä lisää uusia ohjeita, '
        'älä poista mitään ohjeen sisällöstä äläkä lisää lääketieteellisiä väitteitä. Palauta pelkkä teksti.\n\n'
        f'Ohje: {approved_text}'
    )

