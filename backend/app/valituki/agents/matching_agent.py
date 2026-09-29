"""MatchingAgent – triggers deterministic matching when capacity opens and explains the result in plain language.

It never re-matches on its own: negative feedback after the first sessions creates a "Matching review requested" task for
a professional.
"""
from __future__ import annotations

from app.valituki import adapters, content, matching_flow, records
from app.valituki.agents import base
from app.valituki.labels import count_word, fmt_slot
from app.valituki.models import AgentEvent, ValitukiState
from app.valituki.store import get_therapist

AGENT = 'MatchingAgent'


def on_slot_opened(state: ValitukiState, event: AgentEvent, provider) -> None:
    therapist = get_therapist(state, event.therapistId)
    created = adapters.therapist_directory.sync_calendars(state, therapist.id)
    first = min((s.start for s in created), default=None)
    records.act(state, agent=AGENT, type='detect_capacity', event=event, visibility='professional', rule_id='CAP-001',
                title=f'Havaitsi vapautuneen asiakaspaikan: {therapist.name}',
                detail=f'{event.payload.get("reason", "")} Ensimmäinen uusi aika {fmt_slot(first)}. Matching ajetaan kaikille, '
                       'joille terapeutin etsintä on käynnissä.')
    matching_flow.run(state, event, provider, therapist_id=therapist.id)


def on_matches_generated(state: ValitukiState, event: AgentEvent, provider) -> None:
    count = int(event.payload.get('candidates', 0))
    if event.payload.get('released'):
        return
    if count == 0:
        records.act(state, agent=AGENT, type='run_matching', event=event, visibility='professional', rule_id='MATCH-RUN-001',
                    title='Ajoi matchingin – kaikki ehdot täyttäviä vapaita terapeutteja ei löytynyt',
                    detail='Matching ajetaan uudelleen, kun kapasiteettia vapautuu.')
        return
    shown = min(count, int(content.matching_config()['shownCandidates']))
    top = ', '.join(event.payload.get('top', []))
    records.act(state, agent=AGENT, type='run_matching', event=event, rule_id='MATCH-RUN-001',
                title=f'Ajoi terapeuttimatchingin – löysi {count_word(shown)} sopivaa vaihtoehtoa' if shown > 1
                else 'Ajoi terapeuttimatchingin – löysi yhden sopivan vaihtoehdon',
                detail=f'{top}. Kovat ehdot (kieli, etävastaanotto, kapasiteetti, osaaminen…) ensin, sitten läpinäkyvä '
                       'painotettu sopivuus. Selitykset muotoiltiin vain matchingin perusteista.',
                ai_task='generateMatchExplanation')


def on_match_feedback(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = next(c for c in state.clients if c.id == event.clientId)
    feedback = next(f for f in state.matchFeedback if f.id == event.payload['feedbackId'])
    therapist = get_therapist(state, feedback.therapistId)
    if not feedback.negative:
        records.act(state, agent=AGENT, type='store_feedback', event=event, rule_id='MATCH-FEEDBACK-001',
                    title='Tallensi yhteistyöpalautteen', detail='Palaute auttaa arvioimaan matchingin laatua. Kiitos!')
        return
    task = base.create_task(
        state, client, agent=AGENT, type='matching_review', priority='normal', title='Matching review requested',
        reason=f'Yhteistyöpalaute (terapeutti {therapist.name}) oli kielteinen (kuulluksi tuleminen {feedback.heard}/5, tavoitteiden '
               f'ymmärtäminen {feedback.goalsUnderstood}/5, työskentelytapa {feedback.styleFit}/5).',
        suggested='Keskustele asiakkaan kanssa. Terapeuttia ei vaihdeta automaattisesti.',
        data={'feedbackId': feedback.id, 'note': feedback.note or None, 'wantContinue': feedback.wantContinue,
              'wantDiscussAlternative': feedback.wantDiscussAlternative})
    feedback.reviewTaskId = task.id
    records.notify(state, audience='coordinator', client_id=client.id, kind='review', event=event, agent=AGENT,
                   title=f'Matching review requested: {client.displayName}',
                   body='Yhteistyöpalaute oli kielteinen. Ei automaattista vaihtoa.')
    records.notify(state, audience='client', client_id=client.id, kind='contact', event=event, agent=AGENT, action_view='matching',
                   title='Kiitos palautteesta',
                   body='Terapeuttia ei vaihdeta automaattisesti. Hoitotiimi ottaa yhteyttä ja käy tilanteen kanssasi läpi.')
    records.act(state, agent=AGENT, type='request_matching_review', event=event, rule_id='MATCH-FEEDBACK-001',
                title='Pyysi ammattilaista arvioimaan matchingin uudelleen',
                detail='Kielteinen palaute ei vaihda terapeuttia automaattisesti – päätös tehdään yhdessä ammattilaisen kanssa.')
