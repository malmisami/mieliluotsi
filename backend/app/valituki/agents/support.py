"""SupportAgent – conversational support, approved activity introduction and reflection.

It may select an approved activity, personalise the introduction and connect it to a user-approved goal. It never
invents exercises or treatment instructions, and in therapy mode it stays inside the therapist's configuration.
"""
from __future__ import annotations

from typing import Any, Optional

from app.valituki import activities, content, fit_profile, insights, practice, records, therapy, trends
from app.valituki.agents import base
from app.valituki.labels import fmt_date, relative_label
from app.valituki.models import AgentEvent, ClientProfile, TodayActivity, ValitukiState
from app.valituki.store import add_days

AGENT = 'SupportAgent'


def choose_today_activity(state: ValitukiState, client: ClientProfile, provider, event: Optional[AgentEvent] = None, *,
                          elevated: bool = False) -> None:
    current = client.todayActivity
    if current and current.date == state.currentDate:
        return  # one suggested step per day; a completed or skipped one is not replaced the same day
    activity, reason = activities.select(state, client, elevated=elevated)
    if activity is None:
        client.todayActivity = None
        return
    goal_text = activities.goal_text_for(state, client, activity)
    intro = provider.personalise_approved_activity({'activity': activity.model_dump(), 'goalText': goal_text})
    client.todayActivity = TodayActivity(activityId=activity.id, date=state.currentDate, intro=intro.text, introSource=intro.source,
                                         reason=reason)
    client.recentSuggestions = (client.recentSuggestions + [activity.id])[-6:]
    records.act(state, agent=AGENT, type='select_activity', event=event, client_id=client.id, rule_id='ACT-SEL-001',
                title=f'Valitsi tämän päivän askeleen: {activity.title}', detail=reason,
                ai_task='personaliseApprovedActivity', ai_source=intro.source)


def on_baseline(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = next(c for c in state.clients if c.id == event.clientId)
    choose_today_activity(state, client, provider, event)


def on_checkin_due(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = next(c for c in state.clients if c.id == event.clientId)
    choose_today_activity(state, client, provider, event)


def on_checkin_completed(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = next(c for c in state.clients if c.id == event.clientId)
    trend = trends.evaluate(state, client)
    choose_today_activity(state, client, provider, event, elevated=trend.level >= 1)
    today = client.todayActivity
    activity = content.activity(today.activityId) if today and today.status == 'suggested' else None
    summary = provider.summarise_checkin({
        'firstName': client.firstName,
        'trendText': trend.client_text if trend.direction != 'insufficient' else '',
        'activityTitle': activity.title if activity else None,
        'nextCheckIn': relative_label(client.nextCheckInDate, state.currentDate) if client.nextCheckInDate else None,
    })
    records.notify(state, audience='client', client_id=client.id, kind='checkin', event=event, agent=AGENT, action_view='today',
                   title='Kiitos check-inistä', body=summary.text)
    records.act(state, agent=AGENT, type='acknowledge_checkin', event=event, rule_id='CHK-ACK-001',
                title='Mieliluotsi kuittasi check-inin', detail=summary.text, ai_task='summariseCheckIn', ai_source=summary.source)
    checkin = next((c for c in state.checkIns if c.id == event.payload.get('checkInId')), None)
    practice.say(state, client, summary.text, textSource=summary.source)
    if checkin is not None and checkin.mood is not None:
        practice.offer_after_checkin(state, client, checkin.mood, checkin.anxiety, checkin.note)


def _upsert_activity_insight(state: ValitukiState, client: ClientProfile, activity_id: str, rating: int, actor: str) -> None:
    activity = content.activity(activity_id)
    if activity is None:
        return
    helpful = rating >= 4
    kind = 'activity_helpful' if helpful else 'activity_not_helpful'
    existing = next((i for i in state.insights if i.clientId == client.id and i.kind in ('activity_helpful', 'activity_not_helpful')
                     and i.structured.get('activityId') == activity_id and i.status == 'approved'), None)
    text = (f'{activity.title} tuntui hyödylliseltä ({rating}/5).' if helpful
            else f'{activity.title} ei tuntunut hyödylliseltä ({rating}/5).')
    if existing and existing.kind == kind:
        existing.text = text
        existing.structured = {**existing.structured, 'rating': rating}
        existing.version += 1
        return
    if existing:
        insights.remove(state, client, existing, actor)
    insights.create(state, client, category='helpful', kind=kind, title='Toimiva keino' if helpful else 'Ei tuntunut hyödylliseltä',
                    text=text, origin='measured', source_label=f'Oma arviosi harjoituksesta ({fmt_date(state.currentDate)})',
                    status='approved', actor=actor, source='client_rating', structured={'activityId': activity_id, 'rating': rating})


def on_activity_completed(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = next(c for c in state.clients if c.id == event.clientId)
    rating = event.payload.get('rating')
    activity = content.activity(event.payload['activityId'])
    title = activity.title if activity else event.payload['activityId']
    if rating:
        _upsert_activity_insight(state, client, event.payload['activityId'], int(rating), event.actor)
    fit_profile.rebuild(state, client, agent=AGENT,
                        reason=f'Omahoidon kokemukset päivittyivät: {title}' + (f' ({rating}/5)' if rating else ''))
    if rating and int(rating) >= 4:
        records.act(state, agent=AGENT, type='note_helpful', event=event, rule_id='ACT-HELP-001',
                    title=f'Kirjasi toimivan keinon: {title} ({rating}/5)',
                    detail='Mieliluotsi ehdottaa hyödylliseksi koettuja harjoituksia jatkossa useammin. '
                           'Tieto näkyy ammattilaiselle vain, '
                           'jos sallit sen.')


def on_activity_skipped(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = next(c for c in state.clients if c.id == event.clientId)
    fit_profile.rebuild(state, client, agent=AGENT, reason='Ohitettu harjoitus kirjattiin', visible=False)
    records.act(state, agent=AGENT, type='note_skip', event=event, rule_id='ACT-SKIP-001', visibility='client',
                title='Kirjasi ohituksen', detail='Harjoituksen ohittaminen on aina sallittua. Samaa ei ehdoteta heti uudelleen.')


def _assign_homework(state: ValitukiState, client: ClientProfile, config, due: str) -> None:
    tool = config.homeworkTool
    if not tool:
        return
    practice.create_task(state, client, kind='homework', title_text=practice.title(tool), detail=config.homeworkNote,
                         due=due, tool=tool, assigned_by=f'therapist:{config.therapistId}')


def on_plan_configured(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = next(c for c in state.clients if c.id == event.clientId)
    summary = therapy.mode_summary(state, client)
    first_name = summary.get('therapistFirstName', 'Terapeutti')
    client.todayActivity = None
    choose_today_activity(state, client, provider, event)
    config = therapy.active_config(state, client.id)
    if config is not None:
        for task in [t for t in state.practiceTasks if t.clientId == client.id and t.kind == 'homework' and t.status == 'open']:
            task.status = 'skipped'  # the previous plan's homework is replaced by the new one
        _assign_homework(state, client, config, client.nextCheckInDate or state.currentDate)
        if config.homeworkTool:
            practice.say(state, client, f'Terapeutti {first_name} antoi välitehtävän: {practice.title(config.homeworkTool)}. '
                                        + (f'{config.homeworkNote} ' if config.homeworkNote else '')
                                        + 'Löydät sen Harjoitukset-sivulta, ja muistutan sovittuna päivänä.')
    records.notify(state, audience='client', client_id=client.id, kind='therapy', event=event, agent=AGENT, action_view='plan',
                   title=f'Terapeutti {first_name} määritti Mieliluotsin tapaamisten välille',
                   body=f'Päätavoite: {summary.get("primaryGoal")}. Check-in {summary.get("checkIns")}. Mieliluotsi käyttää vain '
                        'terapeuttisi sallimia harjoituksia.')
    records.act(state, agent=AGENT, type='apply_therapist_plan', event=event, rule_id='THERAPY-002',
                title='Siirtyi terapeutin määrittämään suunnitelmaan',
                detail=f'Sallitut harjoitukset: {", ".join(a["title"] for a in summary.get("allowedActivities", []))}. '
                       f'Seurataan: {summary.get("track")}.'
                       + (f' Ei käsitellä: {summary.get("doNotAddress")}.' if summary.get('doNotAddress') else ''))


PRACTICE_TITLES = {
    'THOUGHT_RECORD_COMPLETED': 'Ajatusten tutkiminen tallentui ajatuspäiväkirjaan',
    'EXPERIMENT_PLANNED': 'Käyttäytymiskoe suunniteltiin ja lisättiin tehtäviin',
    'EXPERIMENT_REVIEWED': 'Käyttäytymiskokeen tulos kirjattiin',
    'EXPOSURE_LADDER_CREATED': 'Altistusporras koottiin – ensimmäinen askel tehtävissä',
    'EXPOSURE_STEP_COMPLETED': 'Altistusaskel kirjattiin portaaseen',
    'PRACTICE_TASK_COMPLETED': 'Sovittu harjoitus merkittiin tehdyksi',
}


def on_practice_completed(state: ValitukiState, event: AgentEvent, provider) -> None:
    """The client's own practice: recorded privately (never on a professional timeline); weekly homework is renewed."""
    client = next(c for c in state.clients if c.id == event.clientId)
    payload = event.payload
    detail = 'Merkintä näkyy vain sinulle, ellet itse jaa sitä.'
    if isinstance(payload.get('before'), int) and isinstance(payload.get('after'), int):
        detail = f'Muutos {payload["before"]}/10 → {payload["after"]}/10. ' + detail
    records.act(state, agent=AGENT, type='practice_recorded', event=event, rule_id='PRACTICE-001', visibility='private',
                title=PRACTICE_TITLES.get(event.type, 'Harjoitus kirjattiin'), detail=detail)
    task = next((t for t in state.practiceTasks if t.id == payload.get('taskId')), None)
    config = therapy.active_config(state, client.id) if client.mode == 'therapy_support' else None
    if task is not None and task.kind == 'homework' and config is not None and config.homeworkTool == task.tool:
        _assign_homework(state, client, config, add_days(max(task.dueDate or state.currentDate, state.currentDate), 7))
        records.act(state, agent=AGENT, type='renew_homework', event=event, rule_id='THERAPY-HW-001', visibility='private',
                    title='Välitehtävä tehty – seuraava on viikon päästä', detail=f'Terapeutin välitehtävä: {task.title}.')


def remind_tasks(state: ValitukiState, client: ClientProfile, at: Optional[str] = None) -> None:
    practice.remind_due_tasks(state, client, at)


# --- the support conversation -------------------------------------------------------------------------------------------

def conversation_context(state: ValitukiState, client: ClientProfile, text: str, deterministic_level: int) -> dict[str, Any]:
    allowed = activities.allowed_library(state, client)
    latest = next(iter(sorted(trends.completed_checkins(state, client.id), key=lambda c: c.completedAt or '', reverse=True)), None)
    # The conversation so far: today's messages (they are on the screen) and, with the storeHistory consent, earlier ones.
    # The message being answered is passed separately.
    history = [m for m in state.chat if m.clientId == client.id and m.text
               and (m.createdAt[:10] >= state.currentDate or (client.consent.storeHistory and m.retained))]
    if history and history[-1].role == 'client' and history[-1].text == text:
        history = history[:-1]
    config = therapy.active_config(state, client.id) if client.mode == 'therapy_support' else None
    return {
        'serviceLanguage': 'fi',
        'mode': client.mode,
        'approvedGoals': [g.text for g in insights.active_goals(state, client.id)],
        'therapistPlan': {'primaryGoal': config.primaryGoal, 'track': config.track} if config else None,
        'doNotAddress': config.doNotAddress if config else '',
        'latestCheckIn': {'mood': latest.mood, 'changes': latest.changes} if latest else None,
        'trend': trends.evaluate(state, client).direction,
        'deterministicSafetyLevel': deterministic_level,
        'professionalReviewExists': any(o.clientId == client.id and o.status in ('reviewed', 'closed')
                                        for o in state.wellbeingObservations),
        'approvedActivities': [{'id': a.id, 'title': a.title, 'purpose': a.purpose} for a in allowed],
        'allowedActivityIds': [a.id for a in allowed],
        'allowedTools': practice.allowed_tools(state, client),
        'recentConversation': [{'role': m.role, 'text': m.text} for m in history[-12:]],
        'message': text,
    }


def respond(state: ValitukiState, client: ClientProfile, text: str, provider, deterministic_level: int):
    return provider.generate_support_response(conversation_context(state, client, text, deterministic_level))


def locked(client: ClientProfile) -> bool:
    return base.safety_locked(client)
