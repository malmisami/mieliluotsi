"""Unit tests for the rule layer: plan state machine, gate 1 relevance, gate 3 consent, adapters, texts and the
automated assessment of the need for care and its urgency (rules decide, the LLM never sets the class)."""
from __future__ import annotations

from collections import Counter

import pytest

from app.config import BASE_DIR
from app.loop.safety import check_text
from app.loop.store import initial_state
from app.support import assessment, consent, cycle, escalation, interventions, plan_state, policies, professional, relevance, texts
from app.support.adapters import AdapterError, load_person_directory, preview
from app.support.adapters.base import parse_date
from app.support.adapters.csv_adapter import CsvAdapter
from app.support.adapters.projection import profile_events
from app.support.models import Approval, Goal, Owner, SupportPlan, UserConsent

AINO_DIR = BASE_DIR / 'data' / 'luvn' / 'aino'


@pytest.fixture
def state(monkeypatch, tmp_path):
    from app.config import settings
    monkeypatch.setattr(settings, 'LOOP_LLM_PROVIDER', 'off')
    return initial_state()


def _plan(status: str = 'pending_professional_review', approved: bool = False, consented: bool = True) -> SupportPlan:
    return SupportPlan(
        id='plan-x', theme='blood_pressure', name='Testisuunnitelma', status=status, rationale='r', objective='o',
        owner=Owner(role='nurse', label='Sairaanhoitaja'), createdAt='2026-09-01',
        approval=Approval(status='approved' if approved else 'not_reviewed'), userConsent=UserConsent(given=consented),
        goal=Goal(id='g', label='kaksi 30 minuutin kävelyä viikossa', activity='kävely', timesPerWeek=2, minutes=30,
                  minTimesPerWeek=1, maxTimesPerWeek=3, setAt='2026-09-01'),
    )


def _bp_plan(state) -> SupportPlan:
    return next(p for p in state.support.plans if p.theme == 'blood_pressure')


def _activate_bp(state) -> SupportPlan:
    plan = _bp_plan(state)
    professional.decide(state, plan.id, 'approve', role='nurse')
    return plan


# --- plan state machine ---------------------------------------------------------------------------------------

@pytest.mark.parametrize('source, target', [
    ('candidate', 'pending_professional_review'), ('pending_professional_review', 'rejected'), ('active', 'paused'),
    ('active', 'escalated'), ('paused', 'active'), ('escalated', 'active'), ('escalated', 'completed'), ('active', 'completed'),
])
def test_allowed_transitions(state, source, target):
    plan = _plan(source, approved=True)
    plan_state.transition(state, plan, target)
    assert plan.status == target


@pytest.mark.parametrize('source, target', [
    ('pending_professional_review', 'paused'), ('pending_professional_review', 'escalated'), ('completed', 'active'),
    ('rejected', 'active'), ('candidate', 'active'), ('paused', 'escalated'),
])
def test_forbidden_transitions(state, source, target):
    with pytest.raises(plan_state.PlanStateError):
        plan_state.transition(state, _plan(source, approved=True), target)


def test_plan_cannot_become_active_without_professional_approval_or_user_consent(state):
    with pytest.raises(plan_state.PlanStateError, match='ammattilaisen hyväksyntää'):
        plan_state.transition(state, _plan('pending_professional_review', approved=False), 'active')
    with pytest.raises(plan_state.PlanStateError, match='suostumusta'):
        plan_state.transition(state, _plan('pending_professional_review', approved=True, consented=False), 'active')


def test_version_bumps_only_when_requested(state):
    plan = _plan()
    plan_state.add_history(state, plan, actor='agent', summary='Tavoite sovitettiin')
    assert plan.version == 1
    plan_state.add_history(state, plan, actor='professional', summary='Muokattu', bump=True)
    assert plan.version == 2 and plan.history[-1].version == 2


# --- gate 1: relevance --------------------------------------------------------------------------------------------

@pytest.mark.parametrize('significance, category, visible', [
    ('Uncertain significance', 'uncertain_or_conflicting', False),
    ('Conflicting classifications of pathogenicity', 'uncertain_or_conflicting', False),
    ('risk factor', 'no_practical_significance', False),
    ('Benign', 'no_practical_significance', False),
    ('Likely pathogenic', 'needs_professional_check', True),
    ('Pathogenic', 'needs_professional_check', True),
    ('drug response', 'needs_professional_check', True),
    (None, 'no_practical_significance', False),
])
def test_genetic_relevance_categories(significance, category, visible):
    result = relevance.classify_genetic(significance)
    assert result['category'] == category and result['userVisible'] is visible


def test_only_professional_approval_makes_a_variant_usable_and_it_stays_marked_unconfirmed():
    approved = relevance.classify_genetic('Likely pathogenic', 'unconfirmed', approved=True)
    assert approved['category'] == 'professionally_approved'
    assert 'vahvistamattomaksi' in approved['reason']


def test_user_facing_genetic_wording_is_neutral():
    assert relevance.genetic_user_title('LDLR', show_details=False) == 'Mahdollinen perimään liittyvä tekijä'
    assert 'LDLR' in relevance.genetic_user_title('LDLR', show_details=True)
    for category in texts.CATEGORY_LABELS.values():
        assert 'virhe' not in category.lower()


def test_health_data_without_a_diagnosis_does_not_form_a_theme():
    profile = load_person_directory(AINO_DIR)
    from app.support.policies import load_policies
    results = {r['themeId']: r for r in relevance.health_data_themes(profile, load_policies()['themes'])}
    assert results['blood_pressure']['category'] == 'potentially_actionable'
    assert results['lipids']['category'] == 'potentially_actionable'
    assert results['glucose']['category'] == 'no_practical_significance'  # a lone glucose value, no diagnosis
    kinds = {s.kind for s in results['blood_pressure']['sources']}
    assert {'diagnoses', 'medications', 'professionalNotes', 'measurements', 'interactionEvents'} <= kinds


# --- gate 3: consent -------------------------------------------------------------------------------------------------

def test_quiet_hours_move_the_delivery_time(state):
    assert consent.delivery_time(state) == '09:00'
    state.support.consent.quietHours.start, state.support.consent.quietHours.end = '22:00', '10:00'
    assert consent.in_quiet_hours(state, '09:00') and consent.delivery_time(state) == '10:00'


def test_contact_block_reasons(state):
    plan = state.support.plans[0]
    assert consent.contact_block_reason(state, plan) is None
    state.support.consent.proactiveContact = False
    assert 'oma-aloitteisia' in consent.contact_block_reason(state, plan)
    assert consent.contact_block_reason(state, plan, urgent=True) is None  # safety messages always go through
    state.support.consent.proactiveContact = True
    state.support.consent.maxContactsPerWeek = 1
    state.support.contacts.append({'date': state.currentDate, 'planId': plan.id, 'kind': 'reminder', 'urgent': False})
    assert 'yhteydenottoraja' in consent.contact_block_reason(state, plan)


def test_gene_names_are_masked_unless_the_user_allows_details(state):
    assert consent.mask_genes(state, 'LDLR-geeni liittyy LDL-kolesteroliin.') == 'Perimätiedon havainto liittyy LDL-kolesteroliin.'
    # an audit line that already says "havainto" does not end up repeating the phrase
    assert consent.mask_genes(state, 'Portti 1: perimätiedon havainto (LDLR) – hyväksytty.') == 'Portti 1: perimätiedon havainto – hyväksytty.'
    state.support.consent.showGeneticDetails = True
    assert consent.mask_genes(state, 'LDLR-geeni') == 'LDLR-geeni'


def test_explicit_consent_to_the_automated_assessment_is_part_of_the_initial_state(state):
    settings = state.support.consent
    assert settings.automatedAssessment is True and settings.automatedAssessmentInformedAt == state.currentDate
    record = next(r for r in state.support.person.consents if r['target'].startswith('Automaattinen hoidon tarpeen arvio'))
    assert record['status'] == 'annettu' and record['date'] == '2026-08-20' and record['channel'] == 'hoitajan vastaanotto'
    assert 'terveydenhuoltolaki 51 § 3 mom.' in record['target']
    assert any('Nimenomainen suostumus automaattiseen hoidon tarpeen arvioon' in h['change'] for h in settings.history)


# --- adapters ---------------------------------------------------------------------------------------------------------

def test_csv_adapter_maps_codes_decimals_and_filters_other_people():
    target, items, stats = CsvAdapter(chunk_size=2).load_table(AINO_DIR / 'mittaukset.csv', 'mittaukset.csv', person_id='SYN-AINO-0046')
    assert target == 'measurements'
    assert stats['rowsRead'] == 11 and stats['rowsForPerson'] == 10 and stats['chunks'] == 6  # streamed in chunks of two rows
    bp = [m for m in items if m.code == 'BP']
    assert bp and bp[0].value == f'{bp[0].systolic}/{bp[0].diastolic}' and {m.context for m in bp} == {'home', 'clinic'}


def test_lab_export_groups_results_by_order_like_omakanta():
    target, items, stats = CsvAdapter().load_table(AINO_DIR / 'laboratoriotulokset.csv', 'laboratoriotulokset.csv',
                                                   person_id='SYN-AINO-0046')
    assert target == 'measurements' and stats['rowsRead'] == 83 and stats['rowsForPerson'] == 81
    assert all(m.context == 'lab' and m.panelId and m.panelName and m.abbreviation and m.referenceRange for m in items)
    blood_count = [m for m in items if m.panelName == 'B -Perusverenkuva, minidiff, vieritutkimus']
    assert len(blood_count) == 17 and len({m.panelId for m in blood_count}) == 1
    lipids = Counter(m.panelId for m in items if m.panelName == 'Lipidit')
    assert lipids == {'LAB-20141118-1': 5, 'LAB-20180412-2': 5, 'LAB-20220510-1': 5, 'LAB-20250304-1': 7, 'LAB-20260512-1': 7}
    # LDL rises slowly over the years; the latest values the rules use are unchanged (3,4 H and 2,9)
    assert [(m.date, m.value, m.flag) for m in items if m.code == 'LDL'] == [
        ('2014-11-18', 2.9, None), ('2018-04-12', 3.2, 'H'), ('2022-05-10', 3.3, 'H'), ('2025-03-04', 3.4, 'H'), ('2026-05-12', 2.9, None)]
    assert any(m.code == 'GLU' and m.date == '2026-05-12' and m.value == 5.9 for m in items)
    hematocrit = next(m for m in items if m.code == 'HKR' and m.date == '2018-04-12')
    assert hematocrit.value == 0.4 and hematocrit.resultText == '0,40' and hematocrit.unit is None  # the reported form is kept
    protein = next(m for m in items if m.code == 'U_PROT')
    assert protein.value == 'Negatiivinen' and protein.resultText == 'Negatiivinen'


def test_text_results_are_rejected_outside_the_lab_export():
    with pytest.raises(AdapterError, match='numeroarvo'):
        preview('csv', 'asiakas_tunnus;pvm;mittaus;arvo;yksikko;systolinen;diastolinen;ymparisto;viite_lippu;lahde\n'
                       'X;2026-09-01;PAINO;paljon;kg;;;koti;;L', 'mittaukset.csv')


def test_adapter_rejects_invalid_rows():
    with pytest.raises(AdapterError, match='päivämäärä'):
        preview('csv', 'asiakas_tunnus;pvm;mittaus;arvo;yksikko;systolinen;diastolinen;ymparisto;viite_lippu;lahde\nX;32.13.2026;LDL;3;mmol/l;;;laboratorio;;L', 'mittaukset.csv')
    with pytest.raises(AdapterError, match='ylä- tai alapaine'):
        preview('csv', 'asiakas_tunnus;pvm;mittaus;arvo;yksikko;systolinen;diastolinen;ymparisto;viite_lippu;lahde\nX;2026-09-01;RR;;mmHg;130;;koti;;L', 'mittaukset.csv')


def test_finnish_and_iso_dates():
    assert parse_date('30.8.2026', 'pvm') == parse_date('2026-08-30', 'pvm') == '2026-08-30'


def test_person_directory_and_projection_cover_every_source():
    profile = load_person_directory(AINO_DIR)
    assert profile.demographics.displayName == 'Aino Demo'
    assert len(profile.geneticInsights) == 3 and profile.consents
    events = profile_events(profile)
    assert {e['type'] for e in events} >= {'diagnosis', 'medication', 'care_episode', 'professional_note', 'contact', 'vital_sign', 'lab_result'}
    assert all(e['extractedData']['sourceKind'] for e in events)
    # Aino's demo data has no self-reports; lab results keep their order so the timeline can group them
    assert not profile.selfReportedData and 'self_report' not in {e['type'] for e in events}
    labs = [e for e in events if e['type'] == 'lab_result']
    assert len(labs) == 81 and all(e['structuredData']['panelId'] and e['structuredData']['abbreviation'] for e in labs)


def test_genetic_report_must_belong_to_the_person():
    import json
    data = json.loads((AINO_DIR / 'perimatieto.json').read_text(encoding='utf-8'))
    with pytest.raises(AdapterError):
        preview('json', json.dumps(data), person_id='SOMEONE-ELSE')


def test_dna_is_optional(tmp_path):
    for name in ('asiakas.json', 'diagnoosit.csv', 'mittaukset.csv'):
        (tmp_path / name).write_text((AINO_DIR / name).read_text(encoding='utf-8'), encoding='utf-8')
    profile = load_person_directory(tmp_path)
    assert profile.geneticInsights == [] and profile.diagnoses and profile.measurements


# --- micro-interventions and texts ------------------------------------------------------------------------------------

def test_smaller_goal_stays_inside_the_professional_range():
    plan = _plan('active', approved=True)
    proposal = interventions.propose_goal(plan, 'time')
    assert proposal['timesPerWeek'] == 1 and proposal['label'] == 'yksi 20 minuutin kävely viikossa'
    plan.goal.timesPerWeek, plan.goal.minutes, plan.goal.label = 1, 20, 'yksi 20 minuutin kävely viikossa'
    assert interventions.propose_goal(plan, 'time') is None  # already at the approved minimum
    assert interventions.propose_goal(plan, 'weather')['activity'] == 'sisäliikunta'


def test_finnish_count_phrases():
    assert texts.count_phrase(1, 'kotimittaus', 'kotimittausta') == 'yksi kotimittaus'
    assert texts.count_phrase(2, 'kotimittaus', 'kotimittausta') == 'kaksi kotimittausta'
    assert texts.goal_label('kävely', 1, 20) == 'yksi 20 minuutin kävely viikossa'
    assert texts.goal_label('taukoliikunta', 3, 10) == 'kolme 10 minuutin taukoliikuntahetkeä viikossa'


def test_agent_templates_pass_the_safety_check():
    samples = [
        texts.plan_activated('Verenpaineen omaseuranta', 'hoitajasi', 'kaksi kotimittausta viikossa', '2026-09-08',
                             '30 minuutin kävely kaksi kertaa'),
        texts.plan_activated('Kolesteroliarvojen seuranta', 'lääkärisi', None, '2026-11-12'),
        texts.reminder_measurements(0, 2, '2026-09-01'),
        texts.reminder_review('Kolesteroliarvojen seuranta', '2026-11-12', 'Laboratorion ajanvaraus'),
        texts.checkin_intro('Verenpaineen omaseuranta', 3),
        texts.ESCALATION_NOTICE.format(urgency_label='Kiireetön', owner_cap='Hoitajasi', handling='5 arkipäivän kuluessa',
                                       reason_short=texts.ESCALATION_REASON_SHORT['goal_failures_and_above_target']),
        texts.GOAL_QUESTION, texts.GOAL_WHY, texts.MEASUREMENT_QUESTION, texts.BARRIER_QUESTION, texts.SMALLER_GOAL_QUESTION,
        texts.STEP_UP_QUESTION, texts.STEP_UP_WHY, texts.WELLBEING_QUESTION, texts.CLOSING_NEW_GOAL, texts.CLOSING_KEEP_GOAL,
        texts.CONTACT_QUESTION, texts.CONTACT_WHY, texts.USEFULNESS_QUESTION, texts.CLOSING_GOAL_MET, texts.CLOSING_NO_TIME, texts.PLAN_PAUSED,
        *texts.DECISION_NOTICES.values(), *texts.GOAL_HINTS.values(), *texts.ESCALATION_REASON_SHORT.values(), *texts.ASSESSMENT_REASONS.values(),
        texts.HUMAN_REVIEW_REASON, texts.RIGHTS_SENTENCE, texts.HUMAN_REVIEW_REQUESTED, texts.SYMPTOM_FOLLOW_UP_SELF_CARE,
    ]
    for sample in samples:
        assert check_text(sample)['passed'], sample
    joined = ' '.join(samples).lower()
    for forbidden in ('diagnoosi', 'sairastat', 'riski', 'dna-virhe'):
        assert forbidden not in joined


# --- automated assessment of the need for care and its urgency: policy vocabulary -------------------------------------

def test_urgency_classes_use_the_statutory_vocabulary():
    classes = {c['id']: c for c in assessment.urgency_classes()}
    assert list(classes) == ['emergency', 'same_day', 'within_3_days', 'routine', 'self_care']
    assert classes['routine']['label'] == 'Kiireetön' and classes['routine']['handlingTime'] == '5 arkipäivän kuluessa'
    assert classes['same_day']['label'] == 'Kiireellinen – samana päivänä'
    assert classes['within_3_days']['label'] == 'Kiirevastaanotto 3 arkipäivän kuluessa'
    assert classes['emergency']['careNeedLabel'] == 'Soita hätänumeroon 112' and classes['emergency']['handlingTime'] == 'heti'
    assert classes['self_care']['label'] == 'Omahoito riittää' and classes['self_care']['handlingTime'] == 'ei yhteydenottoa'
    assert assessment.from_rule_urgency('soon') == 'within_3_days' and assessment.from_rule_urgency('routine') == 'routine'
    assert assessment.from_rule_urgency('same_day') == 'same_day'
    assert assessment.to_rule_urgency('within_3_days') == 'soon' and assessment.to_rule_urgency('self_care') == 'routine'
    assert assessment.higher('routine', 'same_day') == 'same_day' and assessment.higher('within_3_days', 'self_care') == 'within_3_days'
    with pytest.raises(assessment.AssessmentError):
        assessment.urgency_class('immediately')


def test_policy_documents_the_automation_and_its_legal_assumption():
    block = policies.load_policies()['automation']
    assert block['legalBasis'] == 'terveydenhuoltolaki 51 § 3 mom. (digitaalinen hoidon tarpeen arvio) – prototyyppi olettaa lakimuutoksen voimaan 2027'
    assert block['responsiblePerson'].startswith('Vastuuhenkilö') and block['version'] == 'demo-1'
    assert len(block['principles']) == 7 and any('nimenomaista suostumusta' in p for p in block['principles'])
    assert [r['id'] for r in block['symptomRules']] == ['TRI-EMERG-001', 'TRI-BP-002', 'TRI-BP-003', 'TRI-GEN-004', 'TRI-SELF-005']
    assert block['sampling']['reviewShare'] == 0.2 and block['whatStaysHuman']
    actions = policies.load_policies()['actions']
    assert actions['assess_care_need'] == {'label': 'Hoidon tarpeen ja kiireellisyyden automaattinen arvio (sääntöjen mukaan)', 'level': 8, 'contactsUser': False}
    assert actions['escalate']['label'] == 'Ohjaus vastuuammattilaiselle arvion perusteella'
    assert policies.forbidden_labels()['treatment_decision'] == 'Hoitopäätöksen tekeminen (kuuluu ammattilaiselle)'
    for theme_id in ('blood_pressure', 'lipids', 'glucose'):
        assert 'assess_care_need' in policies.theme(theme_id)['allowedActions']
    rules = {r['id']: r for r in policies.theme('blood_pressure')['escalationRules']}
    assert rules['ESC-BP-001']['urgencyLabel'] == 'Kiireetön' and rules['ESC-BP-003']['urgencyLabel'] == 'Kiireetön'
    assert rules['ESC-BP-002']['urgencyLabel'] == 'Kiireellinen – samana päivänä'
    assert rules['ESC-USER-001']['urgency'] == 'soon' and rules['ESC-USER-001']['handlingTime'] == '3 arkipäivän kuluessa'
    assert all('automaattisen hoidon tarpeen arvion' in r['description'] or 'hoidon tarpeen arvion' in r['description'] for r in rules.values())
    for theme_id in ('lipids', 'glucose'):
        assert [r['id'] for r in policies.theme(theme_id)['escalationRules']] == ['ESC-GEN-USER']


# --- classification: deterministic symptom table and context rules ---------------------------------------------------

@pytest.mark.parametrize('text, urgency, rule_id', [
    ('Minulla on rintakipua ja hengenahdistusta.', 'emergency', 'TRI-EMERG-001'),
    ('Puhe puuroutuu ja toispuoleista heikkoutta.', 'emergency', 'TRI-EMERG-001'),
    ('Kova päänsärky ja näköhäiriöitä aamusta asti.', 'same_day', 'TRI-BP-002'),
    ('Nenäverenvuotoa ja sekavuutta.', 'same_day', 'TRI-BP-002'),
    ('Minulla on ollut pari päivää päänsärkyä ja huimausta, pitäisikö mennä lääkäriin?', 'within_3_days', 'TRI-BP-003'),
    ('Sydämentykytystä iltaisin.', 'within_3_days', 'TRI-BP-003'),
    ('Väsymys on jatkunut ja niska on kipeä.', 'routine', 'TRI-GEN-004'),
    ('Stressiä ja unettomuutta viime viikkoina.', 'routine', 'TRI-GEN-004'),
    ('Kaikki on ihan hyvin, kävelyt sujuvat.', 'self_care', 'TRI-SELF-005'),
    ('Onko tämä kiireellistä?', 'self_care', 'TRI-SELF-005'),
])
def test_symptom_table_classifies_deterministically(state, text, urgency, rule_id):
    result = assessment.classify_symptoms(state, text)
    assert result['urgency'] == urgency and result['rule']['id'] == rule_id
    assert result['reason'] and result['contextNotes'] == []
    assert bool(result['symptoms']) == (rule_id != 'TRI-SELF-005')


def test_symptom_keywords_are_taken_from_the_users_own_words(state):
    result = assessment.classify_symptoms(state, 'Minulla on ollut pari päivää päänsärkyä ja huimausta.')
    assert result['symptoms'] == ['huimausta', 'päänsärkyä'] or set(result['symptoms']) == {'huimausta', 'päänsärkyä'}
    assert result['reason'] == 'Oire kannattaa arvioida kiirevastaanotolla.'


def test_context_rule_raises_routine_to_within_3_days_when_the_average_is_above_target(state):
    _activate_bp(state)
    for reading in ((142, 91), (144, 92)):
        cycle.add_home_measurement(state, *reading)
    result = assessment.classify_symptoms(state, 'Väsymys on jatkunut koko viikon.')
    assert result['urgency'] == 'within_3_days' and result['rule']['id'] == 'TRI-GEN-004'
    assert [r['id'] for r in result['contextRules']] == ['TRI-CTX-BP-ABOVE']
    assert result['contextNotes'] and 'tavoitetason yläpuolella' in result['contextNotes'][0]
    assert result['reason'].endswith('oire arvioidaan kiirevastaanotolla.')


def test_context_rule_makes_any_symptom_at_least_same_day_after_a_reading_over_the_safety_limit(state):
    _activate_bp(state)
    cycle.add_home_measurement(state, 185, 112)
    result = assessment.classify_symptoms(state, 'Muuten kaikki hyvin.')
    assert result['urgency'] == 'same_day' and [r['id'] for r in result['contextRules']] == ['TRI-CTX-BP-SAFETY']
    # an emergency description is never downgraded or changed by context
    assert assessment.classify_symptoms(state, 'Rintakipua ja vaikea hengittää.')['urgency'] == 'emergency'


def test_context_rules_need_an_active_blood_pressure_plan(state):
    # the plan is still pending: no plan metrics, no context rules
    result = assessment.classify_symptoms(state, 'Väsymys on jatkunut koko viikon.')
    assert result['urgency'] == 'routine' and result['contextRules'] == []


# --- assessment records, the user's right and oversight -----------------------------------------------------------------

def test_create_records_mode_labels_legal_notice_and_audit(state):
    plan = _activate_bp(state)
    item = assessment.create(state, trigger='check_in', urgency='routine', reason='Testiperuste.', basis=['LDLR-geeni mainittu'],
                             rules=[plan.escalationRules[0]], plan=plan)
    assert item.id == 'hta-0001' and item.mode == 'automated' and item.status == 'issued'
    assert item.urgencyLabel == 'Kiireetön' and item.careNeedLabel == 'Hoitajan yhteydenotto 5 arkipäivän kuluessa'
    assert item.legalNotice == texts.LEGAL_NOTICE and '2027' in item.legalNotice and '112' in item.legalNotice
    assert item.basis == ['Perimätiedon havainto mainittu']  # masked
    assert item.rulesApplied[0]['id'] == 'ESC-BP-001' and item.chainId
    entry = state.support.audit[-1]
    assert entry.stage == 'assess' and entry.actor == 'agent' and entry.outcome == 'routine' and entry.rule['id'] == 'ESC-BP-001'
    assert entry.detail.startswith('Automaattinen hoidon tarpeen arvio: Kiireetön (5 arkipäivän kuluessa). Peruste: Testiperuste.')
    assert plan.lastAgentAction['action'] == 'assess' and plan.lastAgentAction['label'] == 'Hoidon tarpeen arvio tehty automaattisesti'
    assert assessment.latest_open(state).id == item.id and assessment.latest_open(state, plan).id == item.id
    view = assessment.view(state, item)
    assert view['statusLabel'] == 'Arvio tehty' and view['modeLabel'] == 'Automaattinen arvio (sääntöjen mukaan)' and view['canRequestHuman'] is True


def test_without_consent_the_assessment_is_preliminary_and_emergencies_are_excluded(state):
    state.support.consent.automatedAssessment = False
    item = assessment.create(state, trigger='check_in', urgency='routine', reason='Testi.', basis=[], rules=[])
    assert item.mode == 'professional_required' and 'esiarvio' in state.support.audit[-1].detail
    assert assessment.view(state, item)['modeLabel'] == 'Esiarvio – ammattilainen tekee arvion'
    emergency = assessment.create(state, trigger='symptom_report', urgency='emergency', reason='Testi.', basis=[], rules=[])
    assert emergency.mode == 'excluded_emergency' and assessment.view(state, emergency)['canRequestHuman'] is False
    with pytest.raises(assessment.AssessmentError, match='112'):
        assessment.request_human_review(state, emergency.id)


def test_emergency_symptom_report_is_recorded_but_never_phrased_by_the_rules(state):
    _activate_bp(state)
    item, message = assessment.assess_symptom_report(state, 'Minulla on kova rintakipu ja hengitysvaikeuksia.')
    assert item.mode == 'excluded_emergency' and item.urgency == 'emergency' and message is None
    assert state.support.escalations == []  # 112 cases are not routed through the plan


def test_symptom_report_routes_through_the_plan_and_offers_the_human_assessment(state):
    plan = _activate_bp(state)
    item, message = assessment.assess_symptom_report(state, 'Minulla on ollut pari päivää päänsärkyä ja huimausta.')
    assert item.urgency == 'within_3_days' and item.trigger == 'symptom_report' and item.planId == plan.id
    esc = state.support.escalations[0]
    assert esc.assessmentId == item.id and item.escalationId == esc.id and plan.status == 'escalated'
    assert esc.urgency == 'soon' and esc.urgencyLabel == 'Kiirevastaanotto 3 arkipäivän kuluessa' and esc.rulesApplied[0]['id'] == 'TRI-BP-003'
    assert esc.openDecision == ('Automaattinen arvio oirekuvauksesta: Kiirevastaanotto 3 arkipäivän kuluessa. Vahvista tai muuta arvio ja '
                                'ota yhteyttä asiakkaaseen 3 arkipäivän kuluessa.')
    assert message.kind == 'care_assessment' and message.assessment['urgency'] == 'within_3_days'
    assert [a.type for a in message.actions] == ['request_human_assessment', 'dismiss'] and message.actions[0].label == 'Pyydä ammattilaisen arvio'
    assert message.text.startswith('Kiitos, että kerroit. Automaattinen hoidon tarpeen arvio: Kiirevastaanotto 3 arkipäivän kuluessa.')
    assert 'Välitin tiedon hoitajallesi, joka ottaa yhteyttä 3 arkipäivän kuluessa.' in message.text
    assert message.basis['decisionBy'] == 'Sääntömoottori – automaattinen hoidon tarpeen arvio' and message.basis['statement'].endswith('Kielimalli ei tehnyt arviota.')
    assert check_text(message.text, allowed_urgency='within_3_days')['passed']
    # self-care needs no routing while the plan already has an open escalation anyway
    calm, calm_message = assessment.assess_symptom_report(state, 'Nyt on ihan hyvä olo.')
    assert calm.urgency == 'self_care' and calm.escalationId is None and 'omahoitoa' in calm_message.text.lower()
    assert 'Jos oireet pahenevat tai jatkuvat' in calm_message.text


def test_human_review_request_creates_a_user_request_escalation_without_a_second_assessment(state):
    plan = _activate_bp(state)
    item = assessment.create(state, trigger='check_in', urgency='self_care', reason='Testi.', basis=[], rules=[], plan=plan)
    reviewed = assessment.request_human_review(state, item.id)
    assert reviewed.status == 'human_review_requested' and reviewed.humanReviewRequestedAt == state.currentDate
    assert len(state.support.assessments) == 1
    esc = state.support.escalations[0]
    assert esc.trigger == 'user_request' and esc.humanReviewRequested is True and esc.assessmentId == item.id
    assert esc.urgency == 'soon' and esc.handlingTime == '3 arkipäivän kuluessa'  # the rule's class is higher than self-care
    notice = state.chatMessages[-1]
    assert notice.kind == 'assessment_notice' and notice.text == ('Selvä. Pyysit ammattilaisen tekemän arvion: hoitajasi tekee sen 3 arkipäivän '
                                                                  'kuluessa ja ottaa sinuun yhteyttä. Automaattinen arvio (Omahoito riittää) jää taustatiedoksi.')
    assert state.support.audit[-2].stage == 'assess' and state.support.audit[-2].actor == 'user' and state.support.audit[-2].outcome == 'human_review_requested'
    with pytest.raises(assessment.AssessmentError, match='jo pyydetty'):
        assessment.request_human_review(state, item.id)


def test_sampling_selects_every_fifth_unrouted_assessment_for_oversight(state):
    for _ in range(6):
        assessment.create(state, trigger='check_in', urgency='routine', reason='Testi.', basis=[], rules=[])
    assert assessment.sampling_due(state) == ['hta-0005']
    assert assessment.oversight_ids(state) == ['hta-0005']
    assessment.professional_review(state, 'hta-0005', 'confirm', role='nurse')
    assert assessment.sampling_due(state) == [] and assessment.human_review_request_ids(state) == []


def test_professional_review_validates_ids_decisions_and_classes(state):
    item = assessment.create(state, trigger='check_in', urgency='routine', reason='Testi.', basis=[], rules=[])
    with pytest.raises(assessment.AssessmentError, match='ei löytynyt'):
        assessment.professional_review(state, 'hta-9999', 'confirm', role='nurse')
    with pytest.raises(assessment.AssessmentError, match='Tuntematon päätös'):
        assessment.professional_review(state, item.id, 'approve', role='nurse')
    with pytest.raises(assessment.AssessmentError, match='rooli'):
        assessment.professional_review(state, item.id, 'confirm', role='astronaut')
    with pytest.raises(assessment.AssessmentError, match='uusi kiireellisyysluokka'):
        assessment.professional_review(state, item.id, 'change_urgency', role='nurse')
    with pytest.raises(assessment.AssessmentError, match='kelvollinen'):
        assessment.professional_review(state, item.id, 'change_urgency', role='nurse', new_urgency='asap')
    with pytest.raises(assessment.AssessmentError, match='sama kuin nykyinen'):
        assessment.professional_review(state, item.id, 'change_urgency', role='nurse', new_urgency='routine')
    taken = assessment.professional_review(state, item.id, 'take_over', role='physician', note='Soitan asiakkaalle.')
    assert taken.status == 'human_reviewed' and taken.professionalReview['label'] == 'Tee arvio itse (ammattihenkilön arvio)'
    assert state.chatMessages[-1].text == 'Lääkärisi teki hoidon tarpeen arvion itse: Kiireetön. Soitan asiakkaalle.'
    with pytest.raises(assessment.AssessmentError, match='jo käsitelty'):
        assessment.professional_review(state, item.id, 'confirm', role='nurse')


# --- the safety check knows the allowed class vocabulary but still blocks invented urgency ----------------------------

def test_check_text_allows_only_the_allowed_class_and_the_emergency_number():
    assert not check_text('Soita hätänumeroon 112.')['passed']  # unchanged without a class
    assert not check_text('Tilanne on kiireellinen, mene heti lääkäriin.')['passed']
    assert check_text('Soita hätänumeroon 112.', allowed_urgency='routine')['passed']
    assert check_text('Kiireetön. Hoitajan yhteydenotto 5 arkipäivän kuluessa. Virka-ajan ulkopuolella Päivystysapu 116 117.',
                      allowed_urgency='routine')['passed']
    assert check_text('Kiireellinen – samana päivänä. Yhteys terveysasemalle tänään.', allowed_urgency='same_day')['passed']
    assert check_text('Hätätilanne. Soita hätänumeroon 112. Oirekuvaus viittaa mahdolliseen hätätilanteeseen.', allowed_urgency='emergency')['passed']
    # invented urgency stays blocked even with an allowed class
    for text in ('Tilanne on kiireellinen, mene heti lääkäriin.', 'Mene päivystykseen välittömästi.', 'Tämä on hätätilanne.',
                 'Hoida asia kiireellisesti.'):
        assert not check_text(text, allowed_urgency='routine')['passed'], text
    assert not check_text('Tämä on hätätilanne.', allowed_urgency='same_day')['passed']
    # the other guards are untouched by the class
    assert not check_text('Riski on 35 %', allowed_urgency='routine')['passed']
    assert not check_text('Lopeta lääkkeen käyttö', allowed_urgency='same_day')['passed']
    with pytest.raises(ValueError):
        check_text('Kiireetön.', allowed_urgency='asap')


def test_every_assessment_template_passes_the_safety_check_with_its_class():
    reasons = {r['urgency']: r['reason'] for r in policies.load_policies()['automation']['symptomRules']}
    for cls in assessment.urgency_classes():
        urgency, label, care_need, handling = cls['id'], cls['label'], f"{cls['careNeedLabel']}.", cls['handlingTime']
        follow_up = texts.SYMPTOM_FOLLOW_UP_SELF_CARE if urgency == 'self_care' else texts.SYMPTOM_FOLLOW_UP_CONTACT.format(owner='hoitajallesi', handling=handling)
        samples = [
            texts.SYMPTOM_ASSESSMENT.format(urgency_label=label, care_need=care_need, reason=reasons[urgency], follow_up=follow_up),
            texts.SYMPTOM_ASSESSMENT_PRELIMINARY.format(urgency_label=label, care_need=care_need, reason=reasons[urgency], owner='hoitajasi', handling=handling),
            texts.ESCALATION_NOTICE.format(urgency_label=label, owner_cap='Hoitajasi', handling=handling, reason_short=texts.ESCALATION_REASON_SHORT['symptom_report']),
            texts.ESCALATION_NOTICE_PRELIMINARY.format(urgency_label=label, owner_cap='Hoitajasi', handling=handling, reason_short=texts.ESCALATION_REASON_SHORT['data_missing']),
            texts.HUMAN_REVIEW_CONFIRMED.format(owner='hoitajasi', handling=handling, urgency_label=label),
            texts.HUMAN_REVIEW_REQUESTED.format(owner='hoitajasi', handling=handling),
            texts.ASSESSMENT_REVIEWED_CONFIRM.format(owner_cap='Hoitajasi', urgency_label=label),
            texts.ASSESSMENT_REVIEWED_CHANGED.format(owner_cap='Hoitajasi', urgency_label=label, note='Soitan huomenna.'),
            texts.ASSESSMENT_REVIEWED_TAKEOVER.format(owner_cap='Lääkärisi', urgency_label=label, note=''),
            f'{label}. {care_need} Käsittely {handling}. {reasons[urgency]}',
        ]
        for sample in samples:
            assert check_text(sample, allowed_urgency=urgency)['passed'], (urgency, sample)
    # fixed texts are exempt from the check but must always carry the emergency number
    assert '112' in texts.SAFETY_THRESHOLD_USER and 'Voit aina pyytää ammattilaisen tekemän arvion.' in texts.SAFETY_THRESHOLD_USER
    assert texts.SAFETY_THRESHOLD_USER.startswith('Automaattinen hoidon tarpeen arvio: kiireellinen, hoidettava samana päivänä.')
    assert '112' in texts.LEGAL_NOTICE and 'terveydenhuoltolaki 51 § 3 mom.' in texts.LEGAL_NOTICE


def test_escalation_summary_from_the_llm_must_restate_the_class_verbatim(state, monkeypatch):
    from app.config import settings
    from app.loop import llm
    monkeypatch.setattr(settings, 'LOOP_LLM_PROVIDER', 'anthropic')
    plan = _activate_bp(state)
    drafts = iter(['Tilanne kannattaa hoitaa kiireellisesti heti lääkäriin.',  # invents urgency -> template
                   'Asiakas kuvasi oireita. Arvio: Kiireellinen – samana päivänä.',  # changes the class -> template
                   'Asiakas kuvasi oireita. Automaattinen arvio: Kiirevastaanotto 3 arkipäivän kuluessa.'])  # restates -> accepted
    monkeypatch.setattr(llm, '_call', lambda prompt, output_schema=None: next(drafts))
    for expected in ('template', 'template', 'llm'):
        item = assessment.create(state, trigger='symptom_report', urgency='within_3_days', reason='Oire kannattaa arvioida kiirevastaanotolla.',
                                 basis=[], rules=[{'id': 'TRI-BP-003', 'name': 'Oireet', 'description': 'd'}], plan=plan)
        esc, _ = escalation.create_from_assessment(state, plan, item, item.chainId, notify=False)
        assert esc.summarySource == expected and esc.urgencyLabel == 'Kiirevastaanotto 3 arkipäivän kuluessa'
        esc.status = 'resolved'  # make room for the next one
