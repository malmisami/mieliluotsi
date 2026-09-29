from __future__ import annotations

PROFILES = {
    'ultralight': {
        'parse_batch': 500,
        'match_batch': 500,
        'cooldown_ms': 750,
        'label': 'Erittäin kevyt tila'
    },
    'light': {
        'parse_batch': 2000,
        'match_batch': 2000,
        'cooldown_ms': 250,
        'label': 'Kevyt tila'
    },
    'normal': {
        'parse_batch': 5000,
        'match_batch': 5000,
        'cooldown_ms': 100,
        'label': 'Normaali tila'
    }
}


def get_profile(profile_name: str):
    normalized = (profile_name or 'light').strip().lower()
    if normalized not in PROFILES:
        raise ValueError(f'Unsupported resource profile: {profile_name}')
    return PROFILES[normalized]
