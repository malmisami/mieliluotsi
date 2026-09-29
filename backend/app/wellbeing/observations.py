"""Observations: meaningful changes that concern an active monitoring area, explained ("Miksi näen tämän?") and, when
gate 3 allows, raised by the agent on its own in the chat. Relevant, infrequent, explainable and non-alarmist."""
from __future__ import annotations

from typing import Any, Optional

from app.loop.models import ChatAction, LoopState
from app.loop.store import add_days, next_id
from app.loop.templates import fi_date
from app.support import audit, consent, messages, policies
from app.wellbeing import analysis, catalog, texts
from app.wellbeing.models import HealthObservation


class ObservationError(ValueError):
    pass


def _settings() -> dict[str, Any]:
    return catalog.config().get('observations', {})


def signal_lines(item: dict[str, Any]) -> dict[str, Any]:
    """The facts of one metric for texts and the "Miksi näen tämän?" view."""
    metric = item['metric']
    change = item['change']
    phrases = catalog.PHRASES.get(metric['id'], {'subject': metric['label'], 'noun': metric['label'].lower(), 'up': 'on noussut',
                                                   'down': 'on laskenut'})
    return {
        'metric': metric['id'], 'label': metric['label'], 'unit': metric.get('unit'),
        'current': item['current']['value'], 'baseline': item['baseline']['value'],
        'currentText': catalog.format_value(metric['id'], item['current']['value']),
        'baselineText': catalog.format_value(metric['id'], item['baseline']['value']),
        'deltaText': catalog.format_delta(metric['id'], change['delta']),
        'direction': change['direction'], 'kind': change['kind'], 'consecutiveDays': change['consecutiveDays'],
        'baselineDays': item['baseline'].get('days'), 'sparse': metric.get('kind') == 'sparse',
        'subject': phrases['subject'], 'noun': phrases['noun'], 'partitive': phrases.get('partitive', phrases['noun']),
        'verb': phrases[change['direction']],
        'threshold': _threshold_text(metric, item['baseline']['value']),
    }


def _threshold_text(metric: dict[str, Any], baseline: float) -> str:
    """The rule's threshold in the metric's own unit (a relative threshold is converted with the user's baseline)."""
    change = metric.get('change', {})
    amounts = []
    if 'absolute' in change:
        amounts.append(change['absolute'])
    if 'relative' in change:
        amounts.append(change['relative'] * abs(baseline))
    amount = max(amounts) if amounts else 0
    noun = catalog.PHRASES.get(metric['id'], {}).get('noun', metric['label'].lower())
    return f"{noun} vähintään {catalog.format_delta(metric['id'], amount).lstrip('+').lstrip('−')}"


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} ja {items[-1]}"


def _summary(signals: list[dict[str, Any]]) -> str:
    main = signals[0]
    template = texts.MAIN_SIGNAL_SPARSE if main['sparse'] else texts.MAIN_SIGNAL
    text = template.format(subject=main['subject'], verb=main['verb'], current=main['currentText'], baseline=main['baselineText'],
                           days=main['baselineDays'] or 90)
    others = [texts.OTHER_SIGNAL.format(noun=s['noun'], verb=s['verb'], delta=s['deltaText']) for s in signals[1:3]]
    if others:
        text += ' ' + texts.OTHER_SIGNALS.format(items=_join(others))
    return text


def _why(area: dict[str, Any], signals: list[dict[str, Any]], result: dict[str, Any], state: LoopState) -> dict[str, Any]:
    lines = []
    for s in signals:
        lines.append({'label': s['label'], 'current': s['currentText'], 'baseline': s['baselineText'], 'delta': s['deltaText'],
                      'consecutive': texts.CONSECUTIVE.format(label=s['label'], side=texts.SIDE[s['direction']], days=s['consecutiveDays'])
                      if s['consecutiveDays'] >= 3 else None})
    return {
        'reason': area.get('reason'),
        'basis': area.get('basisLabel'),
        'lines': lines,
        'period': texts.WHY_PERIOD.format(days=signals[0]['baselineDays'] or 90),
        'rules': [texts.WHY_RULE.format(thresholds=_join([s['threshold'] for s in signals]))],
        'source': texts.WHY_SOURCE.format(source=catalog.source_label(analysis.data(state).connection.source),
                                          start=fi_date(result['from']), end=fi_date(result['end'])),
    }


def _recent(state: LoopState, area_id: str, kind: str, days: int, end: str) -> bool:
    return any(o.areaId == area_id and o.kind == kind and o.periodEnd > add_days(end, -days) for o in analysis.data(state).observations)


def refresh(state: LoopState, notify: bool = True) -> list[HealthObservation]:
    """Match the detected changes with the active monitoring areas. A concern in an area becomes one observation (high
    priority), a clearly positive development another (normal). Changes outside the areas stay in the list of changes."""
    if not analysis.usable(state):
        return []
    result = analysis.analyze(state)
    end = result['end']
    if not end:
        return []
    cooldown = _settings().get('cooldownDays', 14)
    created: list[HealthObservation] = []
    for area in analysis.active_areas(state):
        if not area['active']:
            continue
        items = [result['metrics'][m] for m in area['metrics'] if m in result['metrics'] and result['metrics'][m]['change']]
        for kind in ('change', 'positive'):
            wanted = 'concern' if kind == 'change' else 'positive'
            chosen = sorted((i for i in items if i['change']['kind'] == wanted), key=lambda i: -i['change']['strength'])
            if not chosen or _recent(state, area['id'], kind, cooldown, end):
                continue
            signals = [signal_lines(i) for i in chosen]
            note = (texts.AREA_NOTE if len(signals) > 1 else texts.AREA_NOTE_ONE).format(area=area.get('noteGenitive', area['label'].lower()))
            observation = HealthObservation(
                id=next_id(state, 'hobs'), kind=kind, areaId=area['id'], areaLabel=area['label'],
                title=texts.TITLE_CHANGE if kind == 'change' else texts.TITLE_POSITIVE, summary=_summary(signals), areaNote=note,
                signals=signals, why=_why(area, signals, result, state), priority='high' if kind == 'change' else 'normal',
                createdAt=state.currentDate, periodEnd=end,
            )
            analysis.data(state).observations.append(observation)
            created.append(observation)
            audit.record(state, stage='detect', actor='agent', action='health_observation', outcome=kind,
                         signal={'metrics': [s['metric'] for s in signals], 'area': area['id']},
                         # names only: health values stay out of the audit log
                         detail=f"Hyvinvointidata: {observation.title.lower()} ({area['label']}). Muutos omaan tasoon: "
                                + ', '.join(s['noun'] for s in signals) + '.')
    if notify:
        for observation in created:
            _raise_in_chat(state, observation)
    return created


def _raise_in_chat(state: LoopState, observation: HealthObservation) -> None:
    """The agent's own contact about an observation - only for an active monitoring area, only when gate 3 allows and
    at most once in `proactiveCooldownDays`."""
    if observation.priority != 'high' and observation.kind != 'positive':
        return
    limit = _settings().get('proactiveCooldownDays', 7)
    if any(c['kind'] == 'health_observation' and c['date'] > add_days(state.currentDate, -limit) for c in state.support.contacts):
        return
    blocked = consent.contact_block_reason(state, None)
    if blocked:
        audit.record(state, stage='decide', actor='agent', action='deferred', outcome='deferred',
                     detail=f'Hyvinvointidatan havainnosta ei otettu yhteyttä (portti 3): {blocked}')
        return
    label = texts.ACTION_DISCUSS if observation.kind == 'change' else texts.ACTION_CONTINUE
    actions = [messages.action(state, label, 'discuss_health_observation', observationId=observation.id),
               messages.action(state, texts.ACTION_LATER, 'dismiss_health_observation', style='secondary', observationId=observation.id)]
    message = messages.post(state, texts.PROACTIVE.format(title=observation.title, summary=observation.summary, area_note=observation.areaNote),
                            kind='health_observation', actions=actions, basis_data=_basis(state, observation))
    observation.messageId = message.id
    state.support.contacts.append({'date': state.currentDate, 'planId': None, 'kind': 'health_observation', 'urgent': False,
                                   'label': f'{observation.title}: {observation.areaLabel}', 'channel': state.support.consent.channel,
                                   'deliveredAt': consent.delivery_time(state)})
    audit.record(state, stage='act', actor='agent', action='health_observation',
                 detail=f'Agentti otti itse yhteyttä hyvinvointidatan havainnosta ({observation.areaLabel}).')


def _basis(state: LoopState, observation: HealthObservation) -> dict[str, Any]:
    return {
        'monitorings': [{'id': observation.areaId, 'finding': f'Seuranta-alue: {observation.areaLabel}',
                         'status': observation.why.get('basis') or ''}],
        'events': [f"{line['label']}: viimeiset 7 päivää {line['current']}, oma tasosi {line['baseline']} ({line['delta']})"
                   for line in observation.why.get('lines', [])],
        'userProvided': [],
        'evidenceSource': 'Synteettiset demo-policyt (data/support/policies.json: wellbeingData)',
        'rules': [{'id': 'WB-CHANGE', 'name': rule, 'demoNotice': 'Synteettinen demosääntö, ei hoitosuositus.'} for rule in observation.why.get('rules', [])],
        'decisionBy': 'Sääntömoottori: muutos omaan tasoon verrattuna ja aktiivinen seuranta-alue (ei kielimallia)',
        'textBy': 'Valmis tekstipohja',
        'statement': 'Havainto perustuu päivittäisiin yhteenvetoihin ja omaan tasoosi. Se ei ole diagnoosi. Kielimalli ei tehnyt päätöstä.',
    }


def find(state: LoopState, observation_id: str) -> HealthObservation:
    observation = next((o for o in analysis.data(state).observations if o.id == observation_id), None)
    if not observation:
        raise ObservationError('Havaintoa ei löytynyt.')
    return observation


def _area(observation: HealthObservation) -> dict[str, Any]:
    return next((a for a in catalog.areas() if a['id'] == observation.areaId), {'label': observation.areaLabel})


def discuss(state: LoopState, observation_id: str, via: str = 'tab') -> HealthObservation:
    """Open the conversation: the data, the interpretation and the possible next actions - kept apart."""
    observation = find(state, observation_id)
    if not analysis.usable(state):
        raise ObservationError('Hyvinvointidata ei ole käytössä, joten havaintoa ei voi käsitellä.')
    if via != 'chat':
        messages.user_choice(state, f"{texts.ACTION_DISCUSS if observation.kind == 'change' else texts.ACTION_CONTINUE}: {observation.title.lower()}")
    observation.status = 'discussed'
    analysis.data(state).activeObservationId = observation.id
    area = _area(observation)
    intro = (texts.DISCUSS_INTRO if observation.kind == 'change' else texts.DISCUSS_INTRO_POSITIVE).format(
        area=area.get('noteGenitive', observation.areaLabel.lower()))
    lines = [f"• {line['label']}: viimeiset 7 päivää {line['current']}, oma tasosi {line['baseline']} ({line['delta']})"
             for line in observation.why.get('lines', [])]
    interpretation = texts.INTERPRETATION if observation.kind == 'change' else texts.INTERPRETATION_POSITIVE
    text = '\n'.join([intro, *lines, '', interpretation, '', texts.DISCUSS_QUESTION])
    actions: list[ChatAction] = []
    if observation.kind == 'change':
        actions.append(messages.action(state, texts.ACTION_REASONS, 'health_reasons', observationId=observation.id))
    actions.append(messages.action(state, texts.ACTION_FOLLOW, 'health_follow', style='secondary', observationId=observation.id))
    if observation.kind == 'change':
        actions.append(messages.action(state, texts.ACTION_PROFESSIONAL, 'request_human_assessment', style='secondary'))
    messages.post(state, text, kind='health_discussion', actions=actions, basis_data=_basis(state, observation), initiated_by_agent=False)
    _mark_used(state, observation)
    audit.record(state, stage='evaluate', actor='user', action='answer:health_observation', user_response='Selvitetään yhdessä',
                 detail=f'Käyttäjä halusi käydä läpi hyvinvointidatan havainnon ({observation.areaLabel}).')
    return observation


def dismiss(state: LoopState, observation_id: str, via: str = 'tab') -> HealthObservation:
    observation = find(state, observation_id)
    if via != 'chat':
        messages.user_choice(state, texts.ACTION_LATER)
    observation.status = 'dismissed'
    messages.post(state, texts.DISMISSED, kind='health_discussion', initiated_by_agent=False)
    _mark_used(state, observation)
    return observation


def ask_reasons(state: LoopState, observation_id: str) -> None:
    observation = find(state, observation_id)
    actions = [messages.action(state, label, 'health_reason', style='secondary' if key == 'unknown' else 'primary',
                               observationId=observation.id, reason=key) for key, label in texts.REASON_OPTIONS]
    messages.post(state, texts.REASON_QUESTION, kind='health_discussion', actions=actions, initiated_by_agent=False)


def _metric_nouns(observation: HealthObservation) -> str:
    """'leposykettä, HRV:tä ja unen määrää' (partitive, as the object of 'Seuraan')."""
    nouns = [s.get('partitive', s['noun']) for s in observation.signals]
    return _join(nouns) if nouns else 'hyvinvointidataasi'


def follow_up(state: LoopState, observation_id: str, reason: Optional[str] = None) -> HealthObservation:
    """The outcome of the discussion: self-monitoring for a week, optionally with an approved guide (never an invented
    instruction). A reason that suggests illness points to the symptom assessment and the professional instead."""
    observation = find(state, observation_id)
    parts = []
    if reason:
        parts.append(texts.REASON_REPLIES.get(reason, texts.REASON_REPLIES['unknown']))
        guide_ids = _area(observation).get('guides', [])
        guide_id = {'load': 'GUIDE-RECOVERY-LOAD', 'sleep': 'GUIDE-SLEEP-ROUTINE', 'activity': 'GUIDE-WALK-SMALL'}.get(reason)
        if guide_id and (guide_id in guide_ids or reason == 'activity'):
            guide = policies.guide(guide_id)
            parts.append(texts.GUIDE_LINE.format(title=guide['title'], text=guide['text']))
    if reason == 'ill':
        observation.outcome = 'symptoms_to_assessment'
    else:
        observation.followUpAt = add_days(state.currentDate, _settings().get('followUpDays', 7))
        observation.outcome = {'load': 'approved_guide', 'sleep': 'small_step', 'activity': 'small_step'}.get(reason or '', 'self_monitoring')
        template = texts.FOLLOW_UP if observation.kind == 'change' else texts.FOLLOW_UP_POSITIVE
        parts.append(template.format(metrics=_metric_nouns(observation), date=fi_date(observation.followUpAt)))
    messages.post(state, '\n\n'.join(parts), kind='health_discussion', basis_data=_basis(state, observation), initiated_by_agent=False)
    audit.record(state, stage='update', actor='agent', action='health_follow_up', outcome=observation.outcome,
                 detail=f'Hyvinvointidatan havainto ({observation.areaLabel}): jatko sovittu käyttäjän kanssa'
                        + (f', seuranta {fi_date(observation.followUpAt)} asti.' if observation.followUpAt else '; oireista hoidon tarpeen arvio.'))
    return observation


def _mark_used(state: LoopState, observation: HealthObservation) -> None:
    for message in state.chatMessages:
        for chat_action in message.actions:
            if chat_action.args.get('observationId') == observation.id and chat_action.type in (
                    'discuss_health_observation', 'dismiss_health_observation'):
                chat_action.used = True
