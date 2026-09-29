"""Mieliluotsi's logical agents. Each agent owns one responsibility; the orchestrator decides which agents an event activates.

SupportAgent      conversational support, approved activity introduction, reflection
CheckInAgent      scheduled check-ins, missing check-in follow-up
ObservationAgent  structured longitudinal changes against the client's own baseline, recurring patterns
MatchingAgent     deterministic matching when capacity opens, human-readable explanations, match feedback
NavigationAgent   the next service step, hand-offs and journey state management
SafetyAgent       deterministic safety triggers; can interrupt every other agent

The agents are rule-driven. A language model is used only through the AIProvider to phrase texts and propose
interpretations – never to decide.
"""
