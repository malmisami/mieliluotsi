"""NavigationAgent – guides the next service step and manages the hand-offs of the journey.

Invitation → intake → support plan → therapist search → matches → booking → user-approved handover → therapy →
therapist-guided between-session support. It also handles the client's own requests for a human.
"""
from __future__ import annotations

from app.valituki import fit_profile, handover, journey, matching_flow, records, therapy
from app.valituki.agents import base
from app.valituki.ai import DemoAIProvider
from app.valituki.labels import CONTACT_REASONS, count_word, fmt_slot_title, genitive
from app.valituki.models import AgentEvent, ClientProfile, ValitukiState
from app.valituki.store import get_therapist, now

AGENT = 'NavigationAgent'


def _client(state: ValitukiState, event: AgentEvent) -> ClientProfile:
    return next(c for c in state.clients if c.id == event.clientId)


def on_enrolled(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = _client(state, event)
    records.notify(state, audience='client', client_id=client.id, kind='info', event=event, agent=AGENT, action_view='intake',
                   title='Tuki alkaa heti, vaikka terapia ei vielä ala',
                   body='Olet terapian jonossa. Mieliluotsi kulkee rinnallasi odotuksen ajan – aloitus on lyhyt keskustelu.')
    records.act(state, agent=AGENT, type='send_invitation', event=event, rule_id='NAV-001',
                title='Mieliluotsi lähetti kutsun heti jonoon liittämisen jälkeen',
                detail='Käyttö on vapaaehtoista. Mieliluotsi ei ole terapeutti eikä päivystyspalvelu.')


def on_insights_approved(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = _client(state, event)
    fit_profile.rebuild(state, client, agent=AGENT, create=True, reason=event.payload.get('reason', 'Hyväksytyt tiedot päivittyivät'))


def on_baseline(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = _client(state, event)
    records.notify(state, audience='client', client_id=client.id, kind='info', event=event, agent=AGENT, action_view='today',
                   title='Mieliluotsi on nyt käytössä',
                   body='Ensimmäistä terapia-aikaa odottaessasi Mieliluotsi kulkee rinnallasi. Sinä päätät, mitä tietoja jaetaan.')
    evaluate_readiness(state, client, provider)


def on_user_requested_human(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = _client(state, event)
    reason_label = CONTACT_REASONS.get(event.payload.get('reason', 'other'), 'Muu asia')
    task = base.create_task(state, client, agent=AGENT, type='contact_request',
                            priority='high' if event.payload.get('reason') == 'wellbeing' else 'normal',
                            title='Asiakas pyysi keskustelua ammattilaisen kanssa', reason=reason_label,
                            suggested='Ota yhteyttä asiakkaaseen ja kirjaa yhteydenotto.',
                            data={'reason': event.payload.get('reason'), 'clientMessage': event.payload.get('message') or None},
                            handling_note=base.CONTACT_HANDLING)
    records.notify(state, audience='coordinator', client_id=client.id, kind='contact', event=event, agent=AGENT,
                   title=f'Yhteydenottopyyntö: {client.displayName}', body=reason_label)
    records.notify(state, audience='client', client_id=client.id, kind='contact', event=event, agent=AGENT, action_view='messages',
                   title='Pyyntösi on välitetty hoitotiimille', body=base.CONTACT_HANDLING)
    records.act(state, agent=AGENT, type='forward_contact_request', event=event, rule_id='HUMAN-REQ-001',
                title='Välitti yhteydenottopyynnön hoitotiimille heti', detail=f'Tehtävä {task.id}: {reason_label}.')


def on_review_completed(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = _client(state, event)
    outcome = event.payload.get('outcome') or 'Tarkistettu'
    records.notify(state, audience='client', client_id=client.id, kind='review', event=event, agent=AGENT, action_view='today',
                   title='Ammattilainen on tarkistanut tilanteesi',
                   body=f'{outcome}. Tuki jatkuu. Voit aina pyytää keskustelua ammattilaisen kanssa.')
    records.act(state, agent=AGENT, type='resume_support', event=event, rule_id='NAV-REVIEW-001',
                title='Jatkoi tukea ammattilaisen tarkistuksen jälkeen', detail=f'Ammattilaisen päätös: {outcome}.')
    matching_flow.release_held(state, client, provider)


def on_matching_ready(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = _client(state, event)
    records.notify(state, audience='client', client_id=client.id, kind='matching', event=event, agent=AGENT, action_view='matching',
                   title='Etsimme tilanteeseesi sopivaa terapeuttia',
                   body='Therapy Fit Profilesi on valmis. Kun sopivalta terapeutilta vapautuu aika, näet vaihtoehdot perusteluineen.')
    records.act(state, agent=AGENT, type='enter_matching', event=event, rule_id='MATCH-READY-001',
                title='Mieliluotsi käynnisti terapeutin etsinnän',
                detail='Valmiusehdot täyttyivät (hyväksytty profiili, matching-lupa, check-init, jonotilanne). Matching ajetaan, kun '
                       'kapasiteettia vapautuu.')


def on_matches_generated(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = _client(state, event)
    count = int(event.payload.get('candidates', 0))
    if count == 0:
        return
    if event.payload.get('held'):
        records.act(state, agent=AGENT, type='hold_matches', event=event, rule_id='NAV-HOLD-001',
                    title='Terapeuttiehdotukset odottavat ammattilaisen tarkistusta',
                    detail='Ehdotukset näytetään, kun avoin tarkistuspyyntö on käsitelty.')
        return
    shown = min(count, 3)
    headline = 'Löysimme yhden tilanteeseesi sopivan terapeutin.' if shown == 1 else \
        f'Löysimme {count_word(shown)} tilanteeseesi sopivaa terapeuttia.'
    records.notify(state, audience='client', client_id=client.id, kind='matching', event=event, agent=AGENT, action_view='matching',
                   title=headline,
                   body='Näet jokaisesta, miksi häntä ehdotetaan ja mitä toiveita ei pystytty täyttämään. Valinta on sinun.')
    records.notify(state, audience='coordinator', client_id=client.id, kind='matching', event=event, agent=AGENT,
                   title=f'Matching valmis: {client.displayName}', body=f'{shown} vaihtoehtoa näytettiin asiakkaalle.')


def on_match_selected(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = _client(state, event)
    therapist = get_therapist(state, event.payload['therapistId'])
    records.notify(state, audience='coordinator', client_id=client.id, kind='matching', event=event, agent=AGENT,
                   title=f'{client.displayName} valitsi terapeutin', body=f'Valinta: {therapist.name}. Aika varattiin automaattisesti.')
    records.act(state, agent=AGENT, type='forward_selection', event=event, rule_id='NAV-MATCH-001',
                title=f'Välitti valintasi ajanvaraukseen: {therapist.name}', detail='Ensimmäinen sopiva aika varattiin.')


def on_first_session_booked(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = _client(state, event)
    therapist = get_therapist(state, event.payload['therapistId'])
    when = event.payload.get('startText') or fmt_slot_title(event.payload['start'])
    client.preparationChecklist = [
        {'id': 'handover', 'text': 'Tarkista ja hyväksy yhteenveto ensimmäistä tapaamista varten', 'done': False},
        {'id': 'topics', 'text': 'Valitse 1–3 asiaa, joista haluat aloittaa', 'done': False},
        {'id': 'practical', 'text': 'Tarkista aika ja etäyhteyden linkki', 'done': False},
    ]
    client.matchingNotificationsPaused = True
    records.act(state, agent=AGENT, type='book_first_session', event=event, rule_id='NAV-BOOK-001',
                title=f'Varasi ensimmäisen tapaamisen: {when}', detail=f'{therapist.name}. AppointmentAdapter (demo).')
    record = handover.get_or_create(state, client, records.agent_actor(AGENT))
    handover.refresh_draft(state, client, record, provider or DemoAIProvider(), agent=AGENT)
    records.notify(state, audience='client', client_id=client.id, kind='handover', event=event, agent=AGENT, action_view='matching',
                   title='Ensimmäinen tapaaminen on varattu',
                   body=f'{therapist.name}, {when}. Yhteenveto ensimmäistä tapaamista varten odottaa – mitään ei jaeta ennen kuin '
                        'hyväksyt sen.')
    records.notify(state, audience='therapist', therapist_id=therapist.id, client_id=client.id, kind='matching', event=event,
                   agent=AGENT, title=f'Uusi asiakas: {client.displayName}',
                   body=f'Ensimmäinen tapaaminen {when}. Yhteenveto näkyy, kun asiakas on hyväksynyt sen.')


def on_handover_approved(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = _client(state, event)
    therapist = get_therapist(state, event.payload['therapistId'])
    sections = len(event.payload.get('sections', []))
    records.notify(state, audience='therapist', therapist_id=therapist.id, client_id=client.id, kind='handover', event=event,
                   agent=AGENT, title=f'{genitive(client.firstName)} hyväksymä yhteenveto',
                   body=f'{client.displayName} hyväksyi yhteenvedon jaettavaksi ennen ensimmäistä tapaamista.')
    records.act(state, agent=AGENT, type='share_handover', event=event, rule_id='HANDOVER-002',
                title=f'Jakoi hyväksymäsi yhteenvedon terapeutille ({therapist.name})',
                detail=f'Mukana vain hyväksymäsi kohdat ({sections}). Keskusteluhistoriaa ei jaettu. Voit perua jakamisen.')


def on_therapy_started(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = _client(state, event)
    therapist = get_therapist(state, event.payload['therapistId'])
    episode = therapy.episode(state, client.id)
    if episode:
        episode.status = 'active'
        episode.startedAt = event.occurredAt
        episode.sessionsHeld = max(1, episode.sessionsHeld)
    client.mode = 'therapy_support'
    client.todayActivity = None
    if client.journeyState == 'HUMAN_REVIEW_NEEDED':
        journey.set_resume_state(client, 'THERAPY_ACTIVE')
    first = therapist.name.split()[0]
    records.act(state, agent=AGENT, type='switch_mode', event=event, rule_id='THERAPY-001',
                title='Siirtyi terapian välitueksi',
                detail=f'Terapeutti {first} määrittää, miten Mieliluotsi tukee sinua tapaamisten välillä. Siihen asti '
                       'Mieliluotsi jatkaa '
                       'vain check-inejä ja turvallisuusohjeita.')
    records.notify(state, audience='client', client_id=client.id, kind='therapy', event=event, agent=AGENT, action_view='plan',
                   title='Terapia alkoi',
                   body='Terapeutti määrittää, miten Mieliluotsi tukee sinua tapaamisten välillä. Mieliluotsi ei korvaa terapeuttia – '
                        'se toimii terapeutin asettamissa rajoissa.')
    records.notify(state, audience='client', client_id=client.id, kind='review', event=event, agent=AGENT, action_view='matching',
                   title='Miltä yhteistyö terapeutin kanssa tuntuu?',
                   body='Lyhyt palaute auttaa varmistamaan, että yhteistyö tuntuu sopivalta. Vastaukset eivät vaihda terapeuttia '
                        'automaattisesti.')
    records.notify(state, audience='therapist', therapist_id=therapist.id, client_id=client.id, kind='therapy', event=event,
                   agent=AGENT, title=f'Määritä välituki: {client.displayName}',
                   body='Voit määrittää päätavoitteen, sallitut harjoitukset, check-in-tiheyden, seurattavan asian ja aiheet, '
                        'joita Mieliluotsi ei käsittele.')


def on_therapy_ended(state: ValitukiState, event: AgentEvent, provider) -> None:
    from app.valituki import practice

    client = _client(state, event)
    plan = therapy.aftercare_plan(state, client.id)
    therapist = get_therapist(state, event.therapistId or (plan.therapistId if plan else ''))
    client.mode = 'aftercare_support'
    client.todayActivity = None
    if client.journeyState == 'HUMAN_REVIEW_NEEDED':
        journey.set_resume_state(client, 'AFTERCARE')
    first = therapist.name.split()[0]
    records.act(state, agent=AGENT, type='switch_mode', event=event, rule_id='AFTERCARE-001',
                title='Siirtyi seurantaan terapian jälkeen',
                detail=f'Terapeutti {first} laati ylläpitosuunnitelman. Mieliala ja ahdistus seurataan jatkossa sovitussa rytmissä; '
                       'jos vointi laskee, hoitotiimi saa tarkistuspyynnön.')
    records.notify(state, audience='client', client_id=client.id, kind='therapy', event=event, agent=AGENT, action_view='path',
                   title='Terapia päättyi – seuranta jatkuu',
                   body='Mieliluotsi seuraa mielialaa ja ahdistusta sovitussa rytmissä, ja harjoitukset ovat edelleen käytössäsi.')
    practice.say(state, client, f'Terapia terapeutti {genitive(first)} kanssa on päättynyt – hienoa työtä. Seuranta jatkuu: kysyn '
                                'mielialaa ja ahdistusta sovitussa rytmissä, ja harjoitukset ovat edelleen käytössäsi. '
                                'Ylläpitosuunnitelmasi löytyy Hoitopolku-sivulta.')


# --- daily rules ---------------------------------------------------------------------------------------------------------

def evaluate_readiness(state: ValitukiState, client: ClientProfile, provider) -> None:
    if client.journeyState != 'WAITING_ACTIVE':
        return
    criteria = matching_flow.readiness(state, client)
    if all(item['passed'] for item in criteria):
        event = journey.apply(state, client, 'MATCHING_READINESS_MET', actor=records.agent_actor(AGENT), source='rule_based',
                              payload={'ruleId': 'MATCH-READY-001', 'criteria': criteria})
        from app.valituki.agents import orchestrator

        orchestrator.dispatch(state, event, provider)


def hold_first_session(state: ValitukiState, client: ClientProfile, provider, at: str = '18:50') -> bool:
    """AppointmentAdapter signal: the first session was held → THERAPY_STARTED."""
    waiting = client.journeyState == 'MATCH_ACCEPTED' or (client.journeyState == 'HUMAN_REVIEW_NEEDED'
                                                           and client.resumeState == 'MATCH_ACCEPTED')
    booking = handover.active_booking(state, client.id)
    if not waiting or booking is None or booking.status != 'booked':
        return False
    booking.status = 'completed'
    booking.updatedAt = now(state, at)
    event = journey.apply(state, client, 'THERAPY_STARTED', actor='appointment_adapter', source='appointment_adapter',
                          therapist_id=booking.therapistId, payload={'bookingId': booking.id, 'therapistId': booking.therapistId})
    from app.valituki.agents import orchestrator

    orchestrator.dispatch(state, event, provider)
    return True


def therapy_progress(state: ValitukiState, client: ClientProfile, provider) -> None:
    booking = handover.active_booking(state, client.id)
    if booking and booking.status == 'booked' and booking.start[:10] < state.currentDate:
        hold_first_session(state, client, provider, at='09:00')
