"""ObservationAgent – structured longitudinal change against the client's own baseline, and recurring patterns.

It creates observations and review tasks; it never diagnoses, never changes treatment and never changes clinical
urgency. A detected pattern is only a proposal ("Huomasimme jotain") until the client says it fits.
"""
from __future__ import annotations

from app.valituki import content, insights, journey, records, trends
from app.valituki.agents import base, checkin
from app.valituki.models import AgentEvent, ValitukiState, WellbeingObservation
from app.valituki.store import days_between, next_id, now

AGENT = 'ObservationAgent'
ORDINALS = {2: 'toista', 3: 'kolmatta', 4: 'neljättä', 5: 'viidettä'}


def on_checkin_completed(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = next(c for c in state.clients if c.id == event.clientId)
    item = next(c for c in state.checkIns if c.id == event.payload['checkInId'])
    trends.update_baseline(state, client)
    if not item.retained or item.id in client.baselineCheckInIds:
        return
    trend = trends.evaluate(state, client)
    policy = content.rules()['trend']
    streak = trend.below_streak
    if streak >= 1 and trends.below_streak(state, client)[-1].id == item.id:
        nth = f'{ORDINALS.get(streak, f"{streak}.")} kertaa peräkkäin ' if streak >= 2 else ''
        records.act(state, agent=AGENT, type='below_baseline', event=event, rule_id=trend.rule_id or 'TREND-WATCH',
                    title=f'Vointi oli {nth}oman lähtötason alapuolella',
                    detail=f'Check-in {item.mood}/5, oma lähtötaso {str(client.baseline).replace(".", ",")}. '
                           'Vertailu tehdään omaan tasoosi, ei muihin ihmisiin.')
    if trend.level == 2 and not any(o.clientId == client.id and o.status == 'open' and o.kind == 'trend_decline'
                                    for o in state.wellbeingObservations):
        changed = journey.apply(state, client, 'WELLBEING_TREND_CHANGED', actor=records.agent_actor(AGENT), source='rule_based',
                                payload={'ruleId': trend.rule_id, 'trend': trend.as_data(), 'clientText': trend.client_text,
                                         'professionalText': trend.professional_text})
        from app.valituki.agents import orchestrator

        orchestrator.dispatch(state, changed, provider)
    elif trend.level == 1:
        checkin.schedule_extra(state, client, event, policy['l1RuleId'],
                               'Vointi on ollut kahdessa peräkkäisessä check-inissä omaa tasoa matalampi. Lisä-check-in auttaa '
                               'näkemään, jatkuuko muutos.')
    elif trend.direction == 'improving' and not any(
            o.clientId == client.id and o.kind == 'trend_improvement'
            and days_between(o.createdAt, state.currentDate) < int(policy['improveCooldownDays']) for o in state.wellbeingObservations):
        stamp = now(state)
        state.wellbeingObservations.append(WellbeingObservation(
            id=next_id(state, 'obs'), clientId=client.id, kind='trend_improvement', agent=AGENT, ruleId=policy['improveRuleId'],
            title='Myönteinen muutos omaan lähtötasoon', reason=trend.professional_text, clientText=trend.client_text,
            requiresHumanReview=False, suggestedAction='Ei vaadi toimenpiteitä.', status='info', createdAt=stamp, updatedAt=stamp,
            createdBy=records.agent_actor(AGENT), source='rule_based'))
        records.act(state, agent=AGENT, type='note_improvement', event=event, rule_id=policy['improveRuleId'],
                    title='Kirjasi myönteisen muutoksen', detail=trend.client_text)

    pattern = trends.detect_workday_pattern(state, client)
    cooldown = int(content.rules()['patterns']['cooldownDays'])
    if pattern and not any(i.clientId == client.id and i.kind == 'pattern' and i.evidence.get('ruleId') == pattern['ruleId']
                           and days_between(i.createdAt, state.currentDate) < cooldown for i in state.insights):
        detected = journey.apply(state, client, 'PATTERN_DETECTED', actor=records.agent_actor(AGENT), source='rule_based',
                                 payload=pattern)
        from app.valituki.agents import orchestrator

        orchestrator.dispatch(state, detected, provider)


def on_trend_changed(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = next(c for c in state.clients if c.id == event.clientId)
    payload = event.payload
    trend = payload['trend']
    stamp = now(state)
    explanation = provider.generate_observation_explanation({'firstName': client.firstName, 'signals': trend['signals'],
                                                             'baseline': trend['baseline'], 'recent': trend['recent']})
    observation = WellbeingObservation(
        id=next_id(state, 'obs'), clientId=client.id, kind='trend_decline', agent=AGENT, ruleId=payload['ruleId'],
        title='Vointi oman lähtötason alapuolella', reason=payload['professionalText'], clientText=payload['clientText'],
        explanation=trend['signals'], underlyingData=trend, aiSummary=explanation.text, aiSummarySource=explanation.source,
        requiresHumanReview=True, suggestedAction='Ehdotus: ammattilaisen tarkistus.', status='open', createdAt=stamp,
        updatedAt=stamp, createdBy=records.agent_actor(AGENT), source='rule_based')
    state.wellbeingObservations.append(observation)
    task = base.create_task(state, client, agent=AGENT, type='trend_review', priority='normal',
                            title='Tarkistuspyyntö: vointi oman lähtötason alapuolella', reason=payload['professionalText'],
                            suggested='Ehdotus: ammattilaisen tarkistus. Mieliluotsi ei ole muuttanut hoidon kiireellisyyttä.',
                            data=trend, observation_id=observation.id, handling_note=base.CONTACT_HANDLING)
    observation.taskId = task.id
    records.notify(state, audience='coordinator', client_id=client.id, kind='review', event=event, agent=AGENT,
                   title=f'Tarkistuspyyntö: {client.displayName}',
                   body='Vointi oman lähtötason alapuolella. Mieliluotsi ei ole muuttanut hoidon kiireellisyyttä.')
    records.notify(state, audience='client', client_id=client.id, kind='review', event=event, agent=AGENT, action_view='today',
                   title='Mieliluotsi huomasi muutoksen',
                   body=f'{payload["clientText"]} Pyysin ammattilaista katsomaan tilannettasi. Tämä havainto odottaa ammattilaisen '
                        'tarkistusta. Mieliluotsi ei ole muuttanut hoitosi kiireellisyyttä. Jos tarvitset apua heti, soita 112 tai '
                        'Päivystysapuun 116117.')
    records.act(state, agent=AGENT, type='request_review', event=event, rule_id=payload['ruleId'],
                title='Mieliluotsi loi ammattilaiselle tarkistuspyynnön',
                detail='Tämä havainto odottaa ammattilaisen tarkistusta. Mieliluotsi ei ole muuttanut hoidon kiireellisyyttä.',
                ai_task='generateObservationExplanation', ai_source=explanation.source)


def on_pattern_detected(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = next(c for c in state.clients if c.id == event.clientId)
    pattern = event.payload
    insights.create(state, client, category='challenge', kind='pattern', title='Huomasimme jotain', text=pattern['text'],
                    origin='observed', source_label='Mieliluotsin havainto check-ineistäsi', status='proposed',
                    actor=records.agent_actor(AGENT), source='rule_based',
                    structured={'domains': pattern['domains']},
                    evidence={**pattern['evidence'], 'ruleId': pattern['ruleId']})
    records.notify(state, audience='client', client_id=client.id, kind='insight', event=event, agent=AGENT, action_view='today',
                   title='Huomasimme jotain', body=f'{pattern["text"]} Tunnistatko tämän omaksesi?')
    records.act(state, agent=AGENT, type='detect_pattern', event=event, rule_id=pattern['ruleId'],
                title='Mieliluotsi huomasi toistuvan kuvion check-ineissä',
                detail=f'{pattern["text"]} Havainto odottaa, tunnistatko sen omaksesi – ilman hyväksyntääsi sitä ei käytetä '
                       'mihinkään.')
