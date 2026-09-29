"""Finnish display labels shared by the engine's explanations and the UI (sent to the frontend in the view meta)."""
from __future__ import annotations

from datetime import date

TOPICS = {
    'anxiety': 'ahdistus ja jännittäminen',
    'work_stress': 'työhön liittyvä stressi',
    'burnout': 'uupumus',
    'stress': 'stressi ja kuormitus',
    'sleep': 'uni',
    'mood': 'mieliala',
    'relationships': 'ihmissuhteet',
    'life_transitions': 'elämänmuutokset',
    'loneliness': 'yksinäisyys',
    'grief': 'menetys ja suru',
    'trauma': 'vaikeat kokemukset',
    'self_esteem': 'itsetunto',
    'panic': 'paniikkioireet',
    'young_people': 'nuoret (13–17 v)',
}

LANGUAGES = {'fi': 'suomi', 'sv': 'ruotsi', 'en': 'englanti'}
FORMATS = {'remote': 'Etävastaanotto', 'in_person': 'Lähivastaanotto', 'either': 'Etä- tai lähivastaanotto'}
TIMES = {'morning': 'aamupäivä', 'daytime': 'iltapäivä', 'evening': 'ilta'}
WEEKDAYS = ['maanantai', 'tiistai', 'keskiviikko', 'torstai', 'perjantai', 'lauantai', 'sunnuntai']
WEEKDAYS_SHORT = ['ma', 'ti', 'ke', 'to', 'pe', 'la', 'su']

STYLE_DIMENSIONS = {
    'structure': {'label': 'Rakenne', 'values': {'structured': 'Selkeä rakenne ja eteneminen', 'balanced': 'Joustava rakenne',
                                                'exploratory': 'Vapaa, tutkiva eteneminen'}},
    'exercises': {'label': 'Harjoitteet vai keskustelu', 'values': {'concrete': 'Konkreettiset harjoitteet',
                                                                     'both': 'Harjoitteita ja keskustelua',
                                                                     'conversation': 'Pääosin keskustelua'}},
    'approach': {'label': 'Haastaminen', 'values': {'directive': 'Terapeutti saa haastaa aktiivisesti',
                                                    'balanced': 'Sekä haastamista että pohtimista',
                                                    'reflective': 'Terapeutti auttaa lähinnä pohtimaan'}},
    'homework': {'label': 'Välitehtävät', 'values': {'yes': 'Välitehtävät sopivat', 'some': 'Välitehtäviä joskus',
                                                     'no': 'Ei välitehtäviä'}},
}

DOMAINS = {'sleep': 'Uni', 'anxiety': 'Ahdistus', 'energy': 'Jaksaminen', 'work': 'Työkyky', 'social': 'Sosiaalinen elämä'}
MOOD_SCALE = {1: 'Tosi huonosti', 2: 'Huonosti', 3: 'Kohtalaisesti', 4: 'Hyvin', 5: 'Tosi hyvin'}
ANXIETY_SCALE = {1: 'Ei lainkaan', 2: 'Vähän', 3: 'Jonkin verran', 4: 'Paljon', 5: 'Hyvin paljon'}

# The kinds of practice shown in "Edistyminen" (the tag on each completed item).
PRACTICE_KINDS = {
    'thought_record': 'Ajatukset',
    'experiment': 'Käyttäytymiskoe',
    'exposure': 'Altistus',
    'activity': 'Harjoitus',
    'checkin': 'Check-in',
    'homework': 'Välitehtävä',
}

SERVICE_CATEGORIES = {'short_therapy': 'Lyhytterapia', 'psychotherapy': 'Kuntoutuspsykoterapia'}
ROLE_CATEGORIES = {'psychotherapist': 'psykoterapeutti', 'psychologist': 'psykologi', 'short_therapist': 'lyhytterapeutti',
                   'psychiatric_nurse': 'psykiatrinen sairaanhoitaja'}
AGE_GROUPS = {'13-17': '13–17 v', '18-29': '18–29 v', '30-64': '30–64 v', '65+': '65+ v'}
AGE_RANGES = {'13-17': (13, 17), '18-29': (18, 29), '30-64': (30, 64), '65+': (65, 130)}
ACCESSIBILITY = {
    'step_free': 'esteetön kulku', 'induction_loop': 'induktiosilmukka', 'plain_language': 'selkokieli',
    'interpreter': 'tulkkaus mahdollinen', 'captions': 'tekstitys etävastaanotolla',
}
CLIENT_FLAGS = {
    'acute_safety_concern': 'avoin, tarkistamaton turvallisuushavainto',
    'primary_substance_use': 'päihteiden käyttö ensisijaisena hoidon tarpeena',
    'needs_interpreter': 'tarvitsee tulkkausta',
}
URGENCY = {'non_urgent': 'Kiireetön', 'urgent': 'Kiireellinen'}

CONSENTS = {
    'proactiveCheckins': {'title': 'Mieliluotsi saa ottaa itse yhteyttä',
                          'description': 'Check-in-kysymykset ja muistutukset valitsemassasi rytmissä.'},
    'storeHistory': {'title': 'Vastaukseni tallennetaan',
                     'description': 'Jotta vointiasi voidaan verrata omaan lähtötasoosi ja huomata muutokset.'},
    'professionalMonitoring': {'title': 'Hoitotiimi näkee voinnin suunnan',
                               'description': 'Ammattilainen näkee check-iniesi yhteenvedon ja Mieliluotsin havainnot. '
                                              'Muut tiedot jaetaan vain, jos annat siihen luvan.'},
    'sharePractice': {'title': 'Terapeuttini näkee harjoitukseni',
                      'description': 'Kun terapia alkaa: harjoitusten määrät, tunnistamasi ajatusloukut ja tunteen muutos 0–10. '
                                     'Ajatuspäiväkirjan merkinnät näkyvät vain, jos jaat ne itse.'},
}

INFO_TYPES = {
    'user_said': 'Asiakkaan omin sanoin / hyväksymä',
    'measured': 'Mitattu / itse raportoitu',
    'ai_summary': 'Tekoälyn tiivistelmä',
    'professional_note': 'Ammattilaisen merkintä',
    'system': 'Järjestelmätieto',
}

INSIGHT_CATEGORIES = {
    'goal': 'Tavoitteeni',
    'preference': 'Toiveeni',
    'helpful': 'Hyödylliseksi kokemani asiat',
    'challenge': 'Arjen haasteet',
    'therapist_wish': 'Terapeuttiin liittyvät toiveet',
}

INSIGHT_ORIGINS = {
    'user_said': 'Omin sanoin',
    'ai_interpreted': 'Tekoälyn tulkinta, jonka hyväksyit',
    'observed': 'Mieliluotsin havainto, jonka hyväksyit',
    'measured': 'Omista vastauksistasi',
}

CONTACT_REASONS = {
    'wellbeing': 'Vointini huolestuttaa minua',
    'waiting': 'Haluan kysyä jonotilanteesta',
    'matching': 'Tarvitsen apua terapeutin valinnassa',
    'other': 'Muu asia',
}

AGENT_DESCRIPTIONS = {
    'SupportAgent': 'Keskustelutuki, ohjatut KKT-harjoitukset chatissa ja hyväksyttyjen harjoitusten esittely',
    'CheckInAgent': 'Check-inien ajoitus ja puuttuvien check-inien seuranta',
    'ObservationAgent': 'Muutokset omaan lähtötasoon ja toistuvat havainnot',
    'MatchingAgent': 'Deterministinen terapeuttimatching ja sen selitykset',
    'NavigationAgent': 'Palvelupolun seuraava askel ja siirtymät',
    'SafetyAgent': 'Deterministiset turvallisuussäännöt – voi keskeyttää kaiken muun',
    'Orchestrator': 'Päättää, mikä agentti käsittelee tapahtuman',
}


_ALLATIVE = {'Mikko': 'Mikolle', 'Pekka': 'Pekalle'}
_GENITIVE = {'Mikko': 'Mikon', 'Pekka': 'Pekan'}


def allative(name: str) -> str:
    """'Samille', 'Mikolle' – Finnish allative of a first name (small exception list for consonant gradation)."""
    return _ALLATIVE.get(name, f'{name}lle')


def genitive(name: str) -> str:
    """'Samin', 'Mikon'."""
    return _GENITIVE.get(name, f'{name}n')


def topic(code: str) -> str:
    return TOPICS.get(code, code)


def join_fi(items: list[str], word: str = 'ja') -> str:
    """'a', 'a ja b', 'a, b ja c'."""
    items = [item for item in items if item]
    if not items:
        return ''
    if len(items) == 1:
        return items[0]
    return ', '.join(items[:-1]) + f' {word} ' + items[-1]


def fmt_num(value: float, digits: int = 1) -> str:
    return f'{value:.{digits}f}'.replace('.', ',')


def fmt_date(iso: str | None) -> str:
    if not iso:
        return '–'
    y, m, d = iso[:10].split('-')
    return f'{int(d)}.{int(m)}.'


def fmt_date_long(iso: str | None) -> str:
    if not iso:
        return '–'
    y, m, d = iso[:10].split('-')
    return f'{int(d)}.{int(m)}.{y}'


def fmt_slot(iso: str | None) -> str:
    """'ti 17.11. klo 18.00'"""
    if not iso:
        return '–'
    day = date.fromisoformat(iso[:10])
    time = iso[11:16].replace(':', '.') if len(iso) >= 16 else ''
    return f'{WEEKDAYS_SHORT[day.weekday()]} {day.day}.{day.month}.' + (f' klo {time}' if time else '')


def fmt_slot_title(iso: str | None) -> str:
    """'Ti 17.11. klo 18.00'"""
    text = fmt_slot(iso)
    return text[:1].upper() + text[1:]


def days_text(days: list[int]) -> str:
    return join_fi([WEEKDAYS_SHORT[d] for d in sorted(days)])


def frequency_text(days: list[int]) -> str:
    count = len(days)
    if count == 0:
        return 'ei säännöllisiä check-inejä'
    per_week = {1: 'kerran viikossa', 2: '2× viikossa', 3: '3× viikossa'}.get(count, f'{count}× viikossa')
    return f'{per_week} ({days_text(days)})'


def relative_label(iso: str | None, today: str) -> str:
    """'tänään', 'huomenna' or 'ke 21.10.'"""
    if not iso:
        return '–'
    delta = (date.fromisoformat(iso[:10]) - date.fromisoformat(today[:10])).days
    if delta == 0:
        return 'tänään'
    if delta == 1:
        return 'huomenna'
    return fmt_slot(iso[:10])


def count_word(count: int) -> str:
    return {1: 'yhden', 2: 'kaksi', 3: 'kolme', 4: 'neljä', 5: 'viisi', 6: 'kuusi'}.get(count, str(count))
