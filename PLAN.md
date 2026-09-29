# Välituki – implementation plan (v2 pivot)

> "Tuki alkaa heti, vaikka terapia ei vielä ala." Hackathon prototype on synthetic data. Not a medical device,
> not clinically validated, not for real patient use.

## 1. What the repository contains today

| Area | Found | Decision |
|---|---|---|
| Frontend | React 18 + Vite 5 + TypeScript (strict), no router (hash deep links), `run()` mutation pattern in a context, own SVG icon set | **Keep** stack, context/`run()` pattern, HTTP helper, icons. **Rebuild** the Välituki UI (new journey, mobile-first client in a phone frame, desktop pro/therapist views, new design tokens). |
| Backend | FastAPI + pydantic, JSON-file repository with lock + transaction, demo clock | **Keep** (`store.py`, `records.py`). |
| Domain engine (Välituki v1) | Journey state machine, one-module agent engine, deterministic safety engine, own-baseline trends, approved activity library, hard-filter + weighted matching, consent-scoped handover, mock adapters, replay seed, AI provider (DEMO/LIVE) + output guard | **Evolve in place.** Keep safety, matching core, handover pattern, adapters, AI-provider pattern and guard. **Replace** form onboarding + PHQ/GAD questionnaires with conversational intake and 1–5 check-ins; **split** the agent into named agents; **add** fit profile, insights/memory, patterns, therapy mode. |
| Legacy OmaGenomi (DNA analysis, genetic-risk loop, care plans, Apple Health) | Already hidden behind `LEGACY_FEATURES_ENABLED=0` / `VITE_ENABLE_LEGACY_APP=false` | **Keep hidden**, untouched; legacy tests keep running. |
| Claude | `anthropic` SDK, `claude-opus-5`, adaptive thinking, JSON-schema output, refusal check, `fallbacks: "default"` | **Keep** the call pattern; add the new provider methods. |

## 2. Target architecture

```
backend/app/valituki/
  models.py        entities (+ IntakeSession, TherapyFitProfile, ClientInsight, InsightPermission, WellbeingMetric,
                   TherapyEpisode, TherapistAgentConfiguration, MatchFeedback …) with provenance/status/consentScope
  journey.py       deterministic state machine: INVITED → INTAKE → WAITING_ACTIVE ⇄ HUMAN_REVIEW_NEEDED → MATCHING_READY
                   → MATCH_PROPOSED → MATCH_ACCEPTED → THERAPY_ACTIVE
  agents/          orchestrator.py  event → agents routing; SafetyAgent runs first and can interrupt the flow
                   safety_agent.py, checkin.py, observation.py, support.py, matching_agent.py, navigation.py
  intake.py        conversational intake: follow-up plan, proposals → explicit approval → insights
  insights.py      ClientInsight + per-item permissions (private / professional / matching), audit of changes
  fit_profile.py   TherapyFitProfile rebuilt from approved insights only (versioned changelog)
  trends.py        1–5 check-ins vs. the client's own baseline; patterns ("Huomasimme jotain")
  matching.py      pure deterministic engine: hard filters → weighted fit (weights in data/valituki/matching_config.json)
  handover.py      "Yhteenveto ensimmäistä tapaamista varten": typed sections, edit/remove/approve, snapshot to therapist
  therapy.py       therapist-configured between-session mode (TherapistAgentConfiguration)
  ai.py, guard.py  AIProvider (DEMO_AI_MODE / LIVE_AI_MODE) + strict system prompt + deterministic output guard
  adapters.py      WaitingList, HealthRecord, TherapistDirectory, Appointment, Notification, ProfessionalTask (mocks)
  simulation.py    demo time machine (+1 / +7 / 14 days, deterioration, stable, slot opening, first session, crisis)
  seed.py          ~30 days of synthetic history replayed through the same engine
  view.py, router.py
frontend/src/valituki/
  ValitukiApp (role switcher Asiakas / Ammattilainen / Terapeutti + Konsepti, demo dock, safety overlay)
  client/   phone frame: intake · Tänään · Matkani · Oma suunnitelma · Terapeutin löytäminen · Viestit · Tietoni
  pro/      Terapiajono (KPIs + sortable queue) · asiakkaan tarkistus · Mitä Välituki teki? · Terapeutit · Vaikuttavuus
  therapist/ first-session summary + between-session configuration
  pitch/    "Passiivisesta jonosta aktiiviseksi hoitopoluksi"
```

Principles: rules decide, the language model only phrases; every autonomous step is an `AgentAction` with the agent's
name ("Mitä Välituki teki?"); AI inferences stay *proposed* until the client approves them; only approved insights with
the matching permission reach the matcher; the agent has no code path that changes clinical urgency.

## 3. Implementation order

1. Backend domain: models, journey, insights + fit profile, intake, check-ins/trends/patterns, activities.
2. Agents + orchestrator, safety interrupt, therapy mode; matching + handover adapted to the fit profile.
3. Seed (Sami pre-intake on 16.10.2026; Mikko, Sara, Demo-kriisikäyttäjä and background clients with ~30 days of
   history; 10 synthetic therapists), time machine, API.
4. Frontend: shell + demo dock → intake → Tänään/Matkani → pro queue + review → matching → handover → therapist
   view + configuration → Tietoni → pitch + impact.
5. Tests (the 16 required cases + an end-to-end demo run), ruff, ESLint, tsc, production build, browser check.
6. README.

## 4. Assumptions

- Demo world starts Friday 16.10.2026; time moves only with the demo controls. Check-ins in the waiting period run
  Mon/Wed/Sat (3× week) unless the client chooses otherwise; the therapist can change this in therapy mode.
- Wellbeing is a 1–5 self-report plus "what changed" domains; the baseline is the client's own early level. No
  questionnaires with scores, no diagnoses.
- Professional dashboard cohort numbers are synthetic and labelled as such; demo clients add to them live.
- Matching weights, trend thresholds, safety phrases and activities are demo policies in `data/valituki/*.json` and need
  clinical validation.

## 5. Status

Implemented end to end (steps 1–6). Verified: 283 backend tests (45 Välituki), ruff, `tsc`, ESLint and the production
build pass; the 8-step demo was walked through in a browser at desktop and phone widths. The demo clock ticks per
cascade (a check-in at 14:40 → the agents' reactions at 14:41), matching the timeline example in the brief.

## 6. v3 – chat-first, Limbic/Wysa-style client with guided CBT

| Decision | Why |
|---|---|
| Client app rebuilt around the chat: **Koti · Keskustelu · Harjoitukset · Edistyminen · Hoitopolku** (Tietoni behind the avatar, Viestit behind the bell) | Limbic's simplicity (serif greeting, "Answer here…", one guided-session card) with Wysa's structure (day plan, library, journal / week in review, therapist tab). The original pathway stays in Hoitopolku. |
| Guided CBT tools as **deterministic flows** (`practice.py` + `data/valituki/cbt.json`): check-in, Ajatusten tutkiminen, Käyttäytymiskoe (+ review), Altistusporras (+ attempts) | Rules decide the steps, answers, allowed tools and what is stored; a model only phrases (`generate_guided_turn`) and proposes traps/examples/ladder steps that the client chooses from. DEMO_AI_MODE works without a key. |
| Mood **and anxiety** on the same 1–5 self-report scale; situational feelings 0–10 in the exercises | One chart axis (no dual axis), the trend engine unchanged; 0–10 is the CBT convention for situational intensity. |
| Results become **tasks with a day** and a 09:00 reminder in the chat; homework assigned by the therapist renews weekly | "Mitä sovittua harjoitusta voisit kokeilla?" becomes something concrete. |
| Practice is **private by default** (`private` agent actions, journal entries shared per entry, therapist summary only with `sharePractice`) | The client decides; the coordinator never sees journal content. |
| New journey state **AFTERCARE** (`THERAPY_ENDED`) with an AftercarePlan | "Terapian jälkeen mielialan seuranta": weekly mood/anxiety; a decline goes back to human review. |

Status: implemented end to end – 13 new backend tests (practice flows, safety interrupt, model validation, privacy,
therapist tools/homework, aftercare, API), the demo script extended to 10 steps (`cbt` and `aftercare` scenes), and the
new UI checked in the browser at desktop and phone widths.
