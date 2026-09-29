""""Yhteenveto ensimmäistä tapaamista varten" – the client-approved handover to the therapist.

Principles:
- Built only from approved information the client allows professionals to see (InsightSharing.professional), the
  client's own self-reports and activity ratings, and professional notes. Nothing is shared before explicit approval.
- Every section declares its information type: the client's own / approved words, measured or self-reported data, an
  AI-generated summary or a professional note – plus its sources.
- The full AI conversation is never included by default.
- The therapist sees only the frozen snapshot the client approved. Editing or withdrawing removes it from view until
  the client approves again.
"""
from __future__ import annotations

from typing import Any, Optional

from app.valituki import adapters, content, insights, journey, records, trends
from app.valituki.fit_profile import self_care_responses
from app.valituki.labels import INFO_TYPES, fmt_date, fmt_num
from app.valituki.models import Booking, ClientProfile, HandoverEdits, HandoverSection, HandoverSource, HandoverSummary, ValitukiState
from app.valituki.store import next_id, now

EDITABLE_TEXT = ('hopes',)
FIXED = ('sources', 'sharing')
SECTION_ORDER = ('hopes', 'goals', 'wellbeing', 'practice', 'tried', 'helped', 'not_helped', 'working_style', 'practical',
                 'observations', 'questions', 'professional', 'ai_summary', 'sources', 'sharing')


class HandoverError(ValueError):
    """The handover action is not possible (HTTP 409)."""


def find(state: ValitukiState, client_id: str) -> Optional[HandoverSummary]:
    return next((h for h in state.handovers if h.clientId == client_id), None)


def get_or_create(state: ValitukiState, client: ClientProfile, actor: str = records.AGENT) -> HandoverSummary:
    record = find(state, client.id)
    if record is None:
        stamp = now(state)
        record = HandoverSummary(id=next_id(state, 'hnd'), clientId=client.id, status='draft', createdAt=stamp, updatedAt=stamp,
                                 createdBy=actor, source='agent')
        state.handovers.append(record)
    return record


def active_booking(state: ValitukiState, client_id: str) -> Optional[Booking]:
    bookings = [b for b in state.bookings if b.clientId == client_id and b.status != 'cancelled']
    return sorted(bookings, key=lambda b: (b.start, b.id))[0] if bookings else None


def suggested_questions(state: ValitukiState, client: ClientProfile) -> list[str]:
    """Starting points for the first session, built from approved information. Marked as Mieliluotsi's suggestions."""
    questions: list[str] = []
    shared = [i for i in insights.for_client(state, client.id) if i.sharing.professional]
    goal = next((i for i in shared if i.kind == 'primary_goal'), None)
    topics = set(goal.structured.get('topics', [])) if goal else set()
    if {'anxiety', 'work_stress'} <= topics:
        questions.append('Miten voisin valmistautua palavereihin niin, ettei jännitys vie yöunia?')
    elif goal:
        questions.append(f'Mistä kannattaisi aloittaa, kun tavoitteeni on: {goal.text.rstrip(".").lower()}?')
    if any(i.kind == 'pattern' for i in shared):
        questions.append('Mitä voisin tehdä iltaisin ennen työpäiviä, kun jännitys nousee?')
    helpful = [row for row in self_care_responses(state, client.id) if row['helpful']]
    if helpful:
        questions.append(f'Miten voisin hyödyntää harjoitusta "{helpful[0]["title"]}" arjessa?')
    return questions[:3]


def _source(kind: str, label: str, at: Optional[str] = None, item_id: Optional[str] = None) -> HandoverSource:
    return HandoverSource(kind=kind, label=label, at=at, id=item_id)


def build_sections(state: ValitukiState, client: ClientProfile, record: HandoverSummary) -> list[HandoverSection]:
    edits = record.edits
    shared = [i for i in insights.for_client(state, client.id) if i.sharing.professional]
    private_count = len([i for i in insights.for_client(state, client.id) if not i.sharing.professional])
    sections: list[HandoverSection] = []

    def add(key: str, title: str, info_type: str, *, content: Any = None, text: Optional[str] = None, available: bool = True,
            unavailable: Optional[str] = None, sources: Optional[list[HandoverSource]] = None, note: Optional[str] = None,
            removable: bool = True, editable: bool = False) -> None:
        sections.append(HandoverSection(
            key=key, title=title, infoType=info_type, removable=removable and key not in FIXED, editable=editable,
            removed=key in edits.removedSections and key not in FIXED, edited=key in edits.sectionTexts or
            (key == 'questions' and edits.questionsEdited), available=available,
            unavailableReason=None if available else unavailable, content=content, text=text, sources=sources or [], note=note))

    goal_insights = [i for i in shared if i.kind in ('primary_goal', 'secondary_goal')]
    primary = next((i for i in goal_insights if i.kind == 'primary_goal'), None)
    hope = edits.sectionTexts.get('hopes') or (primary.structured.get('hope') if primary else '') or ''
    add('hopes', 'Mitä toivon terapialta', 'user_said', text=hope, available=bool(hope), editable=True,
        unavailable='Ei kirjattu.', sources=[_source('intake', 'Alkukeskustelu – omin sanoin', primary.createdAt if primary else None)],
        note='Asiakkaan omat sanat alkukeskustelusta. Asiakas voi muokata tekstiä.')
    add('goals', 'Tavoitteeni', 'user_said',
        content=[{'id': i.id, 'text': i.text, 'priority': 'primary' if i.kind == 'primary_goal' else 'secondary',
                  'edited': i.editedByClient, 'approvedAt': i.approvedAt} for i in goal_insights],
        available=bool(goal_insights), unavailable='Ei jaettavia tavoitteita.',
        sources=[_source('insight', f'Asiakkaan hyväksymä tavoite ({fmt_date(i.approvedAt)})', i.approvedAt, i.id) for i in goal_insights])

    trend = trends.evaluate(state, client)
    points = trends.series(state, client)
    reviewed = [o for o in state.wellbeingObservations if o.clientId == client.id and o.kind == 'trend_decline'
                and o.status in ('reviewed', 'closed')]
    add('wellbeing', 'Voinnin suunta odotusaikana', 'measured', available=bool(points) and client.consent.storeHistory,
        unavailable='Check-inejä ei ole tallennettu.',
        content={'baseline': client.baseline, 'recent': trend.recent, 'direction': trend.direction,
                 'directionLabel': trends.DIRECTION_LABELS[trend.direction],
                 'points': [{'date': p['date'], 'mood': p['mood'], 'belowBaseline': p['belowBaseline']} for p in points],
                 'checkIns': len(points), 'events': [{'date': o.createdAt[:10], 'label': 'Muutos tarkistettiin ammattilaisen toimesta'}
                                                     for o in reviewed],
                 'summary': (f'Oma lähtötaso {fmt_num(client.baseline)} / 5. {trend.client_text.replace("Vointisi", "Vointi")}'
                             if client.baseline is not None else '')},
        sources=[_source('checkins', f'{len(points)} itse raportoitua check-iniä (1–5)', points[-1]['at'] if points else None)],
        note='Itse raportoitu, suuntaa antava – ei diagnoosi.')

    from app.valituki import practice

    practiced = practice.handover_facts(state, client)
    add('practice', 'Mitä olen harjoitellut', 'measured', available=practiced is not None,
        unavailable='Ohjattuja harjoituksia ei ole vielä tehty.', content=practiced,
        sources=[_source('practice', 'Ohjatut KKT-harjoitukset: määrät, tunnistetut ajatusloukut ja tunteen muutos 0–10')],
        note='Vain yhteenveto – ajatuspäiväkirjan merkintöjä ei jaeta ilman erillistä lupaasi.')

    responses = self_care_responses(state, client.id)
    tried = [r for r in responses if r['tried']]
    add('tried', 'Mitä olen kokeillut', 'measured', available=bool(tried), unavailable='Harjoituksia ei ole vielä tehty.',
        content=[{'title': r['title'], 'tried': r['tried'], 'latestRating': r['latestRating']} for r in tried],
        sources=[_source('activity', 'Harjoitusmerkinnät ja omat arviot (1–5)')])
    helped_before = next((i for i in shared if i.kind == 'helped_before'), None)
    helpful = [r for r in responses if r['helpful']]
    add('helped', 'Mikä on auttanut', 'user_said', available=bool(helpful or helped_before), unavailable='Ei kirjattu.',
        content={'activities': [{'title': r['title'], 'rating': r['latestRating']} for r in helpful],
                 'ownWords': helped_before.text if helped_before else None},
        sources=[_source('activity', 'Oma arvio harjoituksesta')]
        + ([_source('insight', 'Alkukeskustelu', helped_before.approvedAt, helped_before.id)] if helped_before else []))
    not_helpful = [r for r in responses if (r['latestRating'] or 5) <= 2 or r['skipped'] >= 2]
    add('not_helped', 'Mikä ei ole auttanut', 'measured', available=bool(not_helpful),
        unavailable='Ei harjoituksia, jotka olisi arvioitu hyödyttömiksi.',
        content=[{'title': r['title'], 'rating': r['latestRating'], 'skipped': r['skipped']} for r in not_helpful],
        sources=[_source('activity', 'Omat arviot ja ohitukset')])
    style = next((i for i in shared if i.kind == 'working_style'), None)
    add('working_style', 'Työskentelytapatoiveet', 'user_said', text=style.text if style else None, available=bool(style),
        unavailable='Ei jaettu.', sources=[_source('insight', 'Asiakkaan hyväksymä tulkinta', style.approvedAt, style.id)] if style else [])
    practical = next((i for i in shared if i.kind == 'practical'), None)
    add('practical', 'Käytännön toiveet', 'user_said', text=practical.text if practical else None, available=bool(practical),
        unavailable='Ei jaettu.',
        sources=[_source('insight', 'Asiakkaan hyväksymä tulkinta', practical.approvedAt, practical.id)] if practical else [])
    observed = [i for i in shared if i.kind in ('pattern', 'difficult_times')]
    add('observations', 'Hyväksymäni havainnot odotusajalta', 'user_said', available=bool(observed), unavailable='Ei jaettuja havaintoja.',
        content=[{'id': i.id, 'text': i.text, 'kind': i.kind, 'basis': i.evidence.get('basis') if i.kind == 'pattern' else None,
                  'approvedAt': i.approvedAt} for i in observed],
        sources=[_source('insight', 'Mieliluotsin havainto, jonka asiakas hyväksyi' if i.kind == 'pattern' else 'Alkukeskustelu',
                         i.approvedAt, i.id) for i in observed],
        note='Havainnot perustuvat asiakkaan omiin vastauksiin – eivät ole diagnooseja.')
    questions = edits.questions if edits.questionsEdited else record.suggestedQuestions
    add('questions', 'Kysymykset, joista haluaisin aloittaa', 'user_said', content={'items': questions,
                                                                                    'suggested': not edits.questionsEdited},
        available=bool(questions), unavailable='Ei kysymyksiä.', editable=True,
        sources=[_source('handover', 'Asiakkaan muokkaama' if edits.questionsEdited else 'Mieliluotsin ehdotus – asiakas hyväksyy')],
        note=None if edits.questionsEdited else 'Mieliluotsi ehdotti nämä hyväksyttyjen tietojesi pohjalta. Muokkaa tai poista.')

    professional_items = [{'date': o.reviewedAt[:10] if o.reviewedAt else o.createdAt[:10], 'title': o.title,
                           'outcome': o.reviewOutcome, 'note': o.reviewNote, 'by': o.reviewedBy}
                          for o in state.wellbeingObservations if o.clientId == client.id and o.status in ('reviewed', 'closed')
                          and o.kind != 'trend_improvement']
    professional_items += [{'date': n.createdAt[:10], 'title': 'Ammattilaisen merkintä', 'outcome': None, 'note': n.text, 'by': n.author}
                           for n in state.notes if n.clientId == client.id and n.includeInHandover]
    add('professional', 'Ammattilaisen havainnot', 'professional_note', content=professional_items, available=bool(professional_items),
        unavailable='Ei ammattilaisen merkintöjä.', sources=[_source('professional', 'Hoitotiimin tarkistukset ja merkinnät')])

    add('ai_summary', 'Tekoälyn tiivistelmä', 'ai_summary', text=record.aiDraft, available=bool(record.aiDraft),
        unavailable='Tiivistelmää ei ole vielä muodostettu.', note='Tekoälyn luonnos hyväksymistäsi tiedoista – ei kliininen arvio.')

    included = [s for s in sections if s.available and not s.removed]
    sources = [{'section': s.title, 'label': src.label, 'at': src.at, 'infoType': INFO_TYPES[s.infoType]}
               for s in included for src in s.sources]
    add('sources', 'Tietolähteet', 'system', content=sources, removable=False)
    add('sharing', 'Jakamisluvat', 'system', removable=False, content={
        'included': [s.title for s in included],
        'removed': [s.title for s in sections if s.removed],
        'privateItems': private_count,
        'chatHistoryIncluded': bool(edits.includeChatHistory),
        'statement': 'Jaetaan vain ne yhteenvedon kohdat, jotka asiakas hyväksyy. Keskusteluhistoriaa ei jaeta. Tiedot, joiden '
                     'käyttöoikeudeksi on valittu "Vain minä", eivät ole mukana.',
    })
    if edits.includeChatHistory:  # never on by default; kept for completeness of the consent model
        transcript = [m for m in state.chat if m.clientId == client.id and m.retained]
        add('chat', 'Keskusteluhistoria', 'user_said', content=[{'role': m.role, 'text': m.text} for m in transcript])
    order = {key: i for i, key in enumerate(SECTION_ORDER)}
    return sorted(sections, key=lambda s: order.get(s.key, 99))


def ai_facts(state: ValitukiState, client: ClientProfile, sections: list[HandoverSection]) -> dict[str, Any]:
    """Structured facts for the AI summary: included sections only, never the conversation."""
    by_key = {s.key: s for s in sections if s.available and not s.removed}
    facts: dict[str, Any] = {'professionalReviewExists': 'professional' in by_key}
    if 'goals' in by_key:
        facts['goals'] = [g['text'] for g in by_key['goals'].content]
    if 'wellbeing' in by_key:
        facts['trend'] = by_key['wellbeing'].content['summary']
    if 'helped' in by_key:
        facts['helpful'] = [f'{a["title"]} ({a["rating"]}/5)' for a in by_key['helped'].content['activities']]
    if 'working_style' in by_key:
        facts['workingStyle'] = by_key['working_style'].text
    if 'observations' in by_key:
        facts['patterns'] = [o['text'] for o in by_key['observations'].content if o['kind'] == 'pattern']
    if 'practice' in by_key:
        facts['practice'] = by_key['practice'].content['text']
    return facts


def refresh_draft(state: ValitukiState, client: ClientProfile, record: HandoverSummary, provider, *,
                  agent: str = 'NavigationAgent') -> None:
    record.suggestedQuestions = suggested_questions(state, client)
    sections = [s for s in build_sections(state, client, record) if s.key != 'ai_summary']
    result = provider.generate_handover_draft(ai_facts(state, client, sections))
    record.aiDraft, record.aiDraftSource = result.text, result.source
    record.updatedAt = now(state)
    records.act(state, agent=agent, type='draft_handover', client_id=client.id, rule_id='HANDOVER-001',
                title='Kokosi yhteenvedon ensimmäistä tapaamista varten',
                detail='Vain hyväksymistäsi tiedoista – ei keskusteluhistoriaa. Mitään ei jaeta ennen kuin hyväksyt sen.',
                ai_task='generateHandoverDraft', ai_source=result.source)


def _invalidate(state: ValitukiState, client: ClientProfile, record: HandoverSummary, actor: str, reason: str) -> None:
    if record.status == 'approved':
        record.status = 'draft'
        record.approvedSnapshot = None
        record.approvedAt = None
        records.audit(state, actor=actor, action='handover_approval_reset', client_id=client.id,
                      detail=f'Yhteenvedon hyväksyntä nollattiin: {reason}. Terapeutti ei näe yhteenvetoa ennen uutta hyväksyntää.')


def update(state: ValitukiState, client: ClientProfile, change: dict[str, Any], actor: str) -> HandoverSummary:
    record = get_or_create(state, client, actor)
    action = change.get('action')
    section = str(change.get('section', ''))
    edits: HandoverEdits = record.edits
    if action == 'remove':
        if section in FIXED:
            raise HandoverError('Tätä kohtaa ei voi poistaa.')
        if section not in edits.removedSections:
            edits.removedSections.append(section)
    elif action == 'restore':
        edits.removedSections = [s for s in edits.removedSections if s != section]
    elif action == 'edit' and section in EDITABLE_TEXT:
        text = str(change.get('text', '')).strip()[:800]
        if not text:
            raise HandoverError('Kirjoita teksti tai poista kohta.')
        edits.sectionTexts[section] = text
    elif action == 'edit' and section == 'questions':
        items = [str(q).strip()[:200] for q in change.get('questions', []) if str(q).strip()][:5]
        edits.questions = items
        edits.questionsEdited = True
    else:
        raise HandoverError('Tuntematon muokkaus.')
    record.updatedAt = now(state)
    _invalidate(state, client, record, actor, 'asiakas muokkasi yhteenvetoa')
    records.audit(state, actor=actor, action='handover_edited', client_id=client.id,
                  detail=f'Yhteenveto: {action} – {section}')
    return record


def approve(state: ValitukiState, client: ClientProfile, actor: str) -> HandoverSummary:
    booking = active_booking(state, client.id)
    if booking is None:
        raise HandoverError('Yhteenvedon voi hyväksyä jaettavaksi, kun terapeutti on valittu.')
    record = get_or_create(state, client, actor)
    sections = build_sections(state, client, record)
    record.approvedSnapshot = [s for s in sections if s.available and not s.removed]
    record.status = 'approved'
    record.therapistId = booking.therapistId
    record.approvedAt = now(state)
    record.version += 1
    record.withdrawnAt = None
    event = journey.apply(state, client, 'HANDOVER_APPROVED', actor=actor, source='client', therapist_id=booking.therapistId,
                          payload={'handoverId': record.id, 'therapistId': booking.therapistId,
                                   'sections': [s.key for s in record.approvedSnapshot]})
    publish = adapters.health_records.publish_handover(state, record)
    records.audit(state, actor=records.SYSTEM, action='health_record_adapter', client_id=client.id, event_id=event.id,
                  detail=publish['note'])
    from app.valituki.agents import orchestrator  # local import: agents import this module

    orchestrator.dispatch(state, event)
    _tick_checklist(client, 'handover')
    return record


def withdraw(state: ValitukiState, client: ClientProfile, actor: str, reason: str = 'asiakas perui jakamisen') -> HandoverSummary:
    record = find(state, client.id)
    if record is None or record.status != 'approved':
        raise HandoverError('Yhteenvetoa ei ole jaettu.')
    record.status = 'withdrawn'
    record.approvedSnapshot = None
    record.withdrawnAt = now(state)
    event = journey.apply(state, client, 'HANDOVER_WITHDRAWN', actor=actor, source='client', payload={'reason': reason})
    if record.therapistId:
        records.notify(state, audience='therapist', therapist_id=record.therapistId, client_id=client.id, kind='handover',
                       title='Yhteenvedon jakaminen peruttu', event=event,
                       body=f'{client.displayName} perui yhteenvedon jakamisen. Se ei ole enää nähtävissä.')
    records.act(state, agent='NavigationAgent', type='withdraw_handover', event=event, title='Perui yhteenvedon jakamisen',
                detail=f'Terapeutti ei enää näe yhteenvetoa ({reason}).')
    return record


def _tick_checklist(client: ClientProfile, item_id: str) -> None:
    for item in client.preparationChecklist:
        if item['id'] == item_id:
            item['done'] = True


def therapist_clients(state: ValitukiState, therapist_id: str) -> list[dict[str, Any]]:
    rows = []
    for booking in sorted((b for b in state.bookings if b.therapistId == therapist_id and b.status != 'cancelled'),
                          key=lambda b: b.start):
        client = next(c for c in state.clients if c.id == booking.clientId)
        record = find(state, client.id)
        rows.append({'clientId': client.id, 'clientName': client.displayName, 'firstName': client.firstName, 'age': client.age,
                     'firstSession': booking.start, 'format': booking.format, 'bookingStatus': booking.status,
                     'handoverStatus': record.status if record else 'none', 'approvedAt': record.approvedAt if record else None,
                     'sections': _therapist_sections(state, client, record)})
    return rows


def _therapist_sections(state: ValitukiState, client: ClientProfile, record: Optional[HandoverSummary]) -> Optional[list[dict]]:
    """Approved: exactly the snapshot the client shared. Draft: the current draft as the client sees it (without the parts they
    removed), marked as a draft in the therapist view. Withdrawn: nothing."""
    if record is None or record.status == 'withdrawn':
        return None
    if record.status == 'approved' and record.approvedSnapshot:
        return [s.model_dump() for s in record.approvedSnapshot]
    return [s.model_dump() for s in build_sections(state, client, record) if s.available and not s.removed]


def summary_line(record: Optional[HandoverSummary]) -> str:
    if record is None:
        return 'Ei yhteenvetoa'
    return {'draft': 'Luonnos – odottaa asiakkaan hyväksyntää', 'approved': f'Asiakas hyväksyi {fmt_date(record.approvedAt)}',
            'withdrawn': f'Jakaminen peruttu {fmt_date(record.withdrawnAt)}'}[record.status]


def library_titles(ids: list[str]) -> list[str]:
    return [a.title for a in content.activities() if a.id in ids]
