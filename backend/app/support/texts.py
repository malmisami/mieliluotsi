"""Finnish texts for the agent. Calm, action-oriented, no diagnoses, no medication advice, no risk figures.

Regular texts are checked in tests with the same deterministic safety check as LLM output. The fixed
safety message (SAFETY_THRESHOLD_USER) is exempt, like the chat's predefined emergency message.
"""
from __future__ import annotations

from app.loop.templates import fi_date

NUMBER_WORDS = {1: 'yksi', 2: 'kaksi', 3: 'kolme', 4: 'neljä', 5: 'viisi', 6: 'kuusi', 7: 'seitsemän'}
NUMBER_GENITIVES = {1: 'yhden', 2: 'kahden', 3: 'kolmen', 4: 'neljän', 5: 'viiden', 6: 'kuuden', 7: 'seitsemän'}
ACTIVITY_FORMS = {
    'kävely': ('kävely', 'kävelyä'),
    'sisäliikunta': ('sisäliikuntahetki', 'sisäliikuntahetkeä'),
    'taukoliikunta': ('taukoliikuntahetki', 'taukoliikuntahetkeä'),
}
OWNER_POSSESSIVE = {
    'nurse': 'hoitajasi',
    'public_health_nurse': 'terveydenhoitajasi',
    'physician': 'lääkärisi',
    'genetics': 'perinnöllisyyslääkäri',
    'other': 'vastuuammattilaisesi',
}
OWNER_ALLATIVE = {  # "välitin tiedon hoitajallesi"
    'nurse': 'hoitajallesi',
    'public_health_nurse': 'terveydenhoitajallesi',
    'physician': 'lääkärillesi',
    'genetics': 'perinnöllisyyslääkärille',
    'other': 'vastuuammattilaisellesi',
}
PLAN_STATUS_LABELS = {
    'candidate': 'Ehdotus',
    'pending_professional_review': 'Odottaa ammattilaisen hyväksyntää',
    'active': 'Käynnissä',
    'paused': 'Tauolla',
    'escalated': 'Arvioitu automaattisesti – ammattilainen mukana',
    'completed': 'Päättynyt',
    'rejected': 'Ei otettu käyttöön',
}
CATEGORY_LABELS = {
    'no_practical_significance': 'Ei käytännön merkitystä seurannalle',
    'uncertain_or_conflicting': 'Epävarma tai ristiriitainen havainto',
    'needs_professional_check': 'Vaatii ammattilaisen tarkistuksen',
    'potentially_actionable': 'Mahdollisesti toimintakelpoinen',
    'professionally_approved': 'Ammattilaisen hyväksymä seurantakohde',
}
REVIEW_STATUS_LABELS = {
    'not_requested': 'Arviota ei ole pyydetty',
    'pending_professional_review': 'Odottaa ammattilaisen arviota',
    'approved': 'Ammattilaisen hyväksymä',
    'rejected': 'Ei käytetä seurannassa',
    'info_requested': 'Ammattilainen pyysi lisätietoa',
}


def times_word(n: int) -> str:
    return NUMBER_WORDS.get(n, str(n))


def times_per_week(n: int) -> str:
    """'kerran' / 'kaksi kertaa' as in 'vähintään kerran viikossa'."""
    return 'kerran' if n == 1 else f'{times_word(n)} kertaa'


def count_phrase(n: int, singular: str, partitive: str) -> str:
    """'yksi kotimittaus' / 'kaksi kotimittausta' - Finnish numerals take the partitive from two upwards."""
    return f'{times_word(n)} {singular if n == 1 else partitive}'


def goal_label(activity: str, times: int, minutes) -> str:
    singular, partitive = ACTIVITY_FORMS.get(activity, (activity, activity))
    minutes_part = f'{minutes} minuutin ' if minutes else ''
    noun = singular if times == 1 else partitive
    return f'{times_word(times)} {minutes_part}{noun} viikossa'


def step_label(activity: str, times: int, minutes) -> str:
    """The one thing to try for the next seven days, e.g. '30 minuutin kävely kolme kertaa'."""
    singular, _ = ACTIVITY_FORMS.get(activity, (activity, activity))
    minutes_part = f'{minutes} minuutin ' if minutes else ''
    return f'{minutes_part}{singular} {times_per_week(times)}'


def goal_step(goal) -> str:
    """step_label for a Goal (or any object with activity, timesPerWeek and minutes)."""
    return step_label(goal.activity, goal.timesPerWeek, goal.minutes)


def days_genitive(days: int) -> str:
    """'kolmen päivän' as in 'kolmen päivän kotiseuranta'."""
    return f'{NUMBER_GENITIVES.get(days, str(days))} päivän'


def owner_possessive(role: str) -> str:
    return OWNER_POSSESSIVE.get(role, 'vastuuammattilaisesi')


def owner_allative(role: str) -> str:
    return OWNER_ALLATIVE.get(role, 'vastuuammattilaisellesi')


def capitalize(text: str) -> str:
    return text[:1].upper() + text[1:]


# --- messages to the user --------------------------------------------------------------------------------------

STEP_TRY = 'Kokeillaan seuraavat 7 päivää yhtä asiaa: {step}.'


def plan_activated(plan_name: str, owner: str, measurements: str | None, next_check: str, step: str | None = None) -> str:
    """The first message of an approved plan: one realistic step for seven days, then the agent asks how it went."""
    parts = [f'{capitalize(owner)} hyväksyi seurantasuunnitelman: {plan_name}.']
    if step:
        parts.append(STEP_TRY.format(step=step))
    if measurements:
        parts.append(f'Lisäksi sovittiin {measurements}.' if step else f'Tällä viikolla tehtäväsi on tehdä {measurements}.')
    if not step and not measurements:
        parts.append('Voit jatkaa arkea tavalliseen tapaan.')
    parts.append(f'Kysyn {fi_date(next_check)}, miten meni.' if step else f'Kysyn kuulumisia {fi_date(next_check)}.')
    return ' '.join(parts)


def guide_attached(title: str) -> str:
    return f'Liitin suunnitelmaan hyväksytyn ohjeen ”{title}”, koska olet kysynyt aiheesta aiemmin.'


def reminder_measurements(count: int, required: int, since: str) -> str:
    return (
        f'Pieni muistutus: päivästä {fi_date(since)} alkaen on kirjattu {count}/{required} sovitusta kotimittauksesta. '
        'Voit kirjata mittauksen Tilanne nyt -näkymässä.'
    )


def reminder_review(plan_name: str, review_date: str, contact: str) -> str:
    return f'{plan_name}: sovittu tarkistus on {fi_date(review_date)}. Ajan voi varata palvelusta {contact}.'


def checkin_intro(plan_name: str, count: int) -> str:
    amount = 'yhden lyhyen kysymyksen' if count == 1 else f'{times_word(count)} lyhyttä kysymystä'
    return f'Viikkotarkistus: {plan_name}. Kysyn {amount}. Voit vastata tässä tai Tilanne nyt -näkymässä.'


GOAL_QUESTION = 'Kokeilimme seitsemän päivää yhtä asiaa: {step}. Miten se sujui?'
GOAL_WHY = 'Kysyn, koska palautteesi perusteella sovitan seuraavan askeleen: pienemmäksi, samaksi tai hieman isommaksi.'
MEASUREMENT_QUESTION = 'Päivästä {since} alkaen on kirjattu {count}/{required} sovitusta kotimittauksesta. Onko mittaaminen onnistunut?'
MEASUREMENT_WHY = 'Kysyn, koska suunnitelman mukaan kotimittaus tehdään {required} kertaa viikossa.'
BARRIER_QUESTION = 'Mikä oli suurin este?'
BARRIER_QUESTION_AGAIN = 'Mikä esti tällä kertaa?'
BARRIER_WHY = 'Kysyn, jotta voin ehdottaa sopivampaa tavoitetta sen sijaan, että toistaisin saman ohjeen.'
SMALLER_GOAL_QUESTION = 'Kokeillaanko seuraavat 7 päivää pienemmällä askeleella: {goal}? {hint}'
SMALLER_GOAL_WHY = 'Ehdotus on {owner} hyväksymän vaihteluvälin sisällä (vähintään {min_times} viikossa).'
STEP_UP_QUESTION = 'Hienoa! Kokeillaanko seuraavat 7 päivää hieman enemmän: {goal}?'
STEP_UP_WHY = 'Ehdotus on {owner} hyväksymän vaihteluvälin sisällä (enintään {max_times} viikossa). Voit myös pitää nykyisen askeleen.'
WELLBEING_QUESTION = 'Miten olet jaksanut viime viikolla?'
WELLBEING_WHY = 'Kysyn, koska kotimittausten keskiarvo on noussut ja haluan kuulla, miten arki on sujunut.'
CONTACT_QUESTION = 'Kuvaamasi kipu tai vaiva kannattaa arvioida. Haluatko, että {owner} ottaa sinuun yhteyttä?'
CONTACT_WHY = 'Kysyn, koska kivun tai vaivan hoito kuuluu ammattilaiselle; voin tehdä hoidon tarpeen arvion ja ohjata sinut eteenpäin.'
USEFULNESS_QUESTION = 'Oliko tästä tarkistuksesta sinulle hyötyä?'
USEFULNESS_WHY = 'Kysyn, jotta palvelua voidaan parantaa. Vastaaminen on vapaaehtoista.'
CONCERN_QUESTION = 'Kirjasit {date}: ”{text}” Haluatko, että välitän tämän {owner} seuraavaa tarkistusta varten?'
CONCERN_WHY = 'Kysyn, koska uusi huoli voi olla tärkeä seurantasi kannalta. Päätös on sinun.'
CLOSING_CONCERN_SHARED = 'Selvä, huoli näkyy {owner} seurannan tiedoissa.'
CLOSING_CONCERN_KEPT = 'Selvä, en välitä tietoa eteenpäin.'

GOAL_HINTS = {
    'time': 'Sen voi tehdä esimerkiksi lounastauolla tai työmatkalla.',
    'tired': 'Lyhyempi ja kevyempi liikuntahetki voi sopia paremmin väsyneeseen arkeen.',
    'weather': 'Sisällä liikkuminen ei riipu säästä.',
    'other': 'Pienempi tavoite on helpompi sovittaa arkeen.',
    'alternative': 'Tämä on vaihtoehto kävelylle.',
}

CLOSING_THANKS = 'Kiitos vastauksista!'
CLOSING_GOAL_MET = 'Hienoa, että askel toteutui.'
CLOSING_GOAL_PARTIAL = 'Hyvä, että osa askeleesta toteutui. Jatketaan samalla askeleella.'
CLOSING_NEW_GOAL = 'Seuraavat 7 päivää kokeillaan: {goal}.'
CLOSING_KEEP_GOAL = 'Pidetään nykyinen askel: {goal}.'
CLOSING_NO_TIME = 'Muistathan kotimittaukset tällä viikolla. Mittauksen voi kirjata Tilanne nyt -näkymässä.'
CLOSING_DEVICE = 'Mittarin kanssa voi auttaa terveysaseman hoitaja: {contact}.'
CLOSING_WELLBEING = 'Jos vointisi mietityttää, voit ottaa yhteyttä: {contact}.'
CLOSING_CONTACT_REQUESTED = 'Välitin toiveesi: {owner} ottaa sinuun yhteyttä ({handling}).'
CLOSING_NEXT_CHECK = 'Kysyn seuraavan kerran {date}.'

# --- automated assessment of the need for care and its urgency (hoidon tarpeen ja kiireellisyyden arvio) ------------
# Legal framing: terveydenhuoltolaki 51 § 3 mom. (digitaalinen hoidon tarpeen arvio) – the prototype ASSUMES the amendment
# enters into force in 2027. The urgency class always comes from the rule engine; the LLM never sets or changes it.

LEGAL_NOTICE_PRELIMINARY = (
    'Esiarvio on tehty automaattisesti sääntöjen perusteella ilman suostumusta automaattiseen arvioon, joten hoidon tarpeen '
    'arvion tekee terveydenhuollon ammattihenkilö (terveydenhuoltolaki 51 § 3 mom., digitaalinen hoidon tarpeen arvio – '
    'prototyyppi olettaa lakimuutoksen voimaan 2027). Hätätilanteessa soita 112.'
)
LEGAL_NOTICE = (
    'Arvio on tehty automaattisesti sääntöjen perusteella (terveydenhuoltolaki 51 § 3 mom., digitaalinen hoidon tarpeen arvio – '
    'prototyyppi olettaa lakimuutoksen voimaan 2027). Hätätilanteessa soita 112.'
)
RIGHTS_SENTENCE = 'Sinulla on aina oikeus terveydenhuollon ammattihenkilön tekemään arvioon.'
HUMAN_REVIEW_BUTTON = 'Pyydä ammattilaisen arvio'
HUMAN_REVIEW_REQUESTED = 'Ammattilaisen arvio pyydetty – {owner} tekee arvion {handling}.'
ASSESSMENT_DONE_LABEL = 'Hoidon tarpeen arvio tehty automaattisesti'
ASSESSMENT_MODE_LABELS = {
    'automated': 'Automaattinen arvio (sääntöjen mukaan)',
    'professional_required': 'Esiarvio – ammattilainen tekee arvion',
    'excluded_emergency': 'Hätätilanne – ei automaattisen arvion piirissä',
}
ASSESSMENT_STATUS_LABELS = {
    'issued': 'Arvio tehty',
    'confirmed': 'Ammattilainen vahvisti arvion',
    'changed': 'Ammattilainen muutti arviota',
    'human_review_requested': 'Ammattilaisen arvio pyydetty',
    'human_reviewed': 'Ammattilainen teki arvion itse',
}
ASSESSMENT_REVIEW_LABELS = {
    'confirm': 'Vahvista arvio',
    'change_urgency': 'Muuta kiireellisyysluokkaa',
    'take_over': 'Tee arvio itse (ammattihenkilön arvio)',
}
# one deterministic sentence per escalation-rule kind, used as the assessment's reason
ASSESSMENT_REASONS = {
    'goal_failures_and_above_target': 'Sovittu omahoitotavoite ei ole toteutunut peräkkäisillä tarkistuksilla ja kotimittausten keskiarvo on suunnitelman tavoitetason yläpuolella',
    'safety_threshold': 'Yksittäinen kotimittaus ylitti suunnitelmaan asetetun turvarajan',
    'data_missing': 'Kotimittauksia ei ole kirjattu pitkään aikaan muistutuksista huolimatta',
    'user_request': 'Asiakas pyysi ammattilaisen tekemän arvion tarkistuksessa',
    'home_monitoring_above': 'Kolmen päivän kotiseurannan keskiarvo on suunnitelmassa sovitun rajan yläpuolella',
}
HUMAN_REVIEW_REASON = 'Asiakas pyysi ammattilaisen tekemän arvion tarkistuksessa.'

ESCALATION_NOTICE = (
    'Tein tilanteestasi automaattisen hoidon tarpeen arvion: {urgency_label}. {owner_cap} ottaa yhteyttä {handling}. '
    'Syy: {reason_short} Arvio perustuu suunnitelman sääntöihin, ei kielimalliin. Voit aina pyytää ammattilaisen tekemän arvion '
    '– tämä ei vaadi sinulta nyt muuta.'
)
ESCALATION_NOTICE_PRELIMINARY = (
    'Tein tilanteestasi esiarvion, koska et ole antanut suostumusta automaattiseen arvioon: {urgency_label}. '
    '{owner_cap} tekee hoidon tarpeen arvion ja ottaa yhteyttä {handling}. Syy: {reason_short} Tämä ei vaadi sinulta nyt muuta.'
)
ESCALATION_REASON_SHORT = {
    'goal_failures_and_above_target': 'sovittu tavoite ei ole toteutunut kahdella viikolla ja kotimittausten keskiarvo on suunnitelmassa sovittua tavoitetasoa korkeampi.',
    'data_missing': 'kotimittauksia ei ole kirjattu pitkään aikaan.',
    'user_request': 'pyysit ammattilaisen tekemän arvion.',
    'safety_threshold': 'kirjattu mittaus ylitti suunnitelman turvarajan.',
    'symptom_report': 'kuvaamasi oireet kannattaa arvioida.',
    'home_monitoring_above': 'kolmen päivän kotiseurannan keskiarvo oli suunnitelmassa sovitun rajan yläpuolella.',
}
HUMAN_REVIEW_CONFIRMED = (
    'Selvä. Pyysit ammattilaisen tekemän arvion: {owner} tekee sen {handling} ja ottaa sinuun yhteyttä. '
    'Automaattinen arvio ({urgency_label}) jää taustatiedoksi.'
)
ASSESSMENT_REVIEWED_CONFIRM = '{owner_cap} vahvisti automaattisen arvion: {urgency_label}.'
ASSESSMENT_REVIEWED_CHANGED = '{owner_cap} tarkensi arviota: {urgency_label}. {note}'
ASSESSMENT_REVIEWED_TAKEOVER = '{owner_cap} teki hoidon tarpeen arvion itse: {urgency_label}. {note}'
SYMPTOM_ASSESSMENT = 'Kiitos, että kerroit. Automaattinen hoidon tarpeen arvio: {urgency_label}. {care_need} Peruste: {reason} {follow_up}'
SYMPTOM_ASSESSMENT_PRELIMINARY = (
    'Kiitos, että kerroit. Esiarvio – ammattilainen tekee arvion: {urgency_label}. {care_need} Peruste: {reason} '
    'Et ole antanut suostumusta automaattiseen arvioon, joten {owner} tekee hoidon tarpeen arvion ja ottaa yhteyttä {handling}.'
)
SYMPTOM_FOLLOW_UP_CONTACT = 'Välitin tiedon {owner}, joka ottaa yhteyttä {handling}.'
SYMPTOM_FOLLOW_UP_SELF_CARE = 'Jos oireet pahenevat tai jatkuvat, kerro uudelleen tai pyydä ammattilaisen arvio.'
SYMPTOM_FOLLOW_UP_NO_PLAN = 'Voit ottaa yhteyttä palveluun: {contact}.'
SYMPTOM_DISMISS_BUTTON = 'Selvä, toimin ohjeen mukaan'

# Fixed, predefined safety message (set in the professional-approved plan). Never generated or rewritten by an LLM.
SAFETY_THRESHOLD_USER = (
    'Automaattinen hoidon tarpeen arvio: kiireellinen, hoidettava samana päivänä. Kirjaamasi kotimittaus {value} mmHg ylittää '
    'suunnitelmaan asetetun turvarajan. Mittaa verenpaine uudelleen, kun olet levännyt viisi minuuttia. Jos lukema on edelleen '
    'yhtä korkea, ota yhteyttä terveysasemalle tänään: {contact}. Jos sinulla on rintakipua, hengenahdistusta, puhe- tai '
    'näköhäiriöitä tai toispuolista heikkoutta, soita hätänumeroon 112. Välitin tiedon myös {owner}. '
    'Voit aina pyytää ammattilaisen tekemän arvion.'
)

DECISION_NOTICES = {
    'edit': '{owner_cap} päivitti seurantasuunnitelmaa (versio {version}). {instructions}',
    'continue': '{owner_cap} vahvisti automaattisen arvion ja kävi tilanteesi läpi. Seuranta jatkuu nykyisellä suunnitelmalla.',
    'continue_changed': '{owner_cap} kävi tilanteesi läpi ja tarkensi automaattista arviota. Seuranta jatkuu nykyisellä suunnitelmalla.',
    'continue_plain': '{owner_cap} kävi tilanteesi läpi. Seuranta jatkuu nykyisellä suunnitelmalla.',
    'reject': 'Ehdotettua seurantaa ({plan}) ei otettu käyttöön. Päätös on {owner} arvio, eikä se vaadi sinulta toimia.',
    'request_info': '{owner_cap} pyytää lisätietoa ennen seurannan aloittamista: {note}',
    'change_permissions': '{owner_cap} päivitti, miten Hyvinvointikumppani saa tukea sinua tässä seurannassa (versio {version}).',
    'contact_user': '{owner_cap} ottaa sinuun yhteyttä ({channel}).',
    'end': 'Seuranta ({plan}) on päätetty yhdessä {owner} kanssa. Kiitos yhteistyöstä!',
    'set_review_date': 'Seurannan seuraava tarkistus on {date}.',
}

PLAN_PAUSED = 'Seuranta ({plan}) on tauolla {until}. En lähetä tästä teemasta muistutuksia tauon aikana.'
PLAN_RESUMED = 'Seuranta ({plan}) jatkuu. Kysyn kuulumisia {date}.'


# --- Linking health records to DNA-analysis findings (Terveystiedot, on the user's request) --------------------------
GENETIC_LINK_STATUS = {
    'approved': 'Käytössä seurannassa',
    'pending': 'Ei käytössä – odottaa ammattilaisen arviota',
    'rejected': 'Ei käytössä – ammattilainen ei hyväksynyt',
    'needs_professional_check': 'Ei käytössä – vaatii ammattilaisen arvion',
    'uncertain_or_conflicting': 'Ei käytössä – tulkinta on epävarma',
    'no_practical_significance': 'Ei käytössä – ei merkitystä seurannalle',
    'not_allowed': 'Ei käytössä – käyttöä ei ole sallittu',
}
GENETIC_LINK_ORIGIN = {'source_record': 'Perimätietolähde', 'dna_analysis': 'Oma DNA-analyysi'}
GENETIC_LINK_MASKED = 'Geenimuutos'
GENETIC_LINK_NOT_ALLOWED = ('Perimätiedon käyttöä ei ole sallittu suostumuksissa, joten terveystietoja ei linkitetä DNA-analyysiin. '
                            'Voit muuttaa valinnan Suostumukset-välilehdellä.')
GENETIC_LINK_NO_FINDINGS = 'Perimätietoa ei ole. Aja DNA-analyysi Perimätieto-välilehdellä, niin terveystiedot voi linkittää siihen.'
GENETIC_LINK_SESSION_MISSING = 'DNA-analyysiä ei löytynyt. Aja analyysi uudelleen Perimätieto-välilehdellä.'
GENETIC_LINK_NOTE = ('Linkitys kertoo, mitkä terveystiedot liittyvät samaan aiheeseen kuin DNA-analyysin havainto. Se ei ole diagnoosi '
                     'eikä muuta seurantaasi: vain ammattilaisen hyväksymä havainto voi olla seurannan taustatietona.')


# --- The self-care continuity engine (omahoidon jatkuvuuden moottori) ---------------------------------------------------
# 1 remember, 2 reach out, 3 one step at a time, 4 notice when self-care is not enough. Rules decide, texts are templates.

MEMORY_TITLES = {
    'goals': 'Tavoitteesi',
    'agreed': 'Sovittu ammattilaisen kanssa',
    'monitor': 'Mitä seuraat',
    'tried': 'Mitä olet jo kokeillut',
    'works': 'Mikä toimii sinulla',
    'recheck': 'Milloin tarkistetaan uudelleen',
}
MEMORY_EMPTY = {
    'goals': 'Ei sovittuja tavoitteita.',
    'agreed': 'Ei ammattilaisen kanssa sovittuja asioita sallimissasi tiedoissa.',
    'monitor': 'Ei seurattavia asioita.',
    'tried': 'Kokeilut kirjautuvat tähän viikkotarkistuksista.',
    'works': 'Opin tämän kokeiluistasi: kerron, mikä on toiminut, kun askelia on takana.',
    'recheck': 'Ei sovittuja tarkistuksia.',
}
MEMORY_NOTES_OFF = 'Ammattilaisten kirjaukset eivät ole käytössä suostumuksissasi, joten en poimi niistä sovittuja asioita.'

HOME_MONITORING_OFFER = (
    'Verenpaineesi on ollut viime viikkoina hieman aiempaa korkeampi: kotimittausten keskiarvo {now} mmHg, aiemmin {before} mmHg. '
    'Haluaisitko tehdä tällä viikolla {days} kotiseurannan? Mittaisit aamulla ja illalla, ja kokoan tuloksista yhteenvedon.'
)
HOME_MONITORING_OFFER_ABOVE = (
    'Kotimittaustesi keskiarvo {now} mmHg on ollut viime viikkoina sovitun tavoitetason yläpuolella. Haluaisitko tehdä tällä '
    'viikolla {days} kotiseurannan? Mittaisit aamulla ja illalla, ja kokoan tuloksista yhteenvedon.'
)
HOME_MONITORING_ACCEPT = 'Kyllä, aloitetaan'
HOME_MONITORING_DECLINE = 'Ei tällä viikolla'
HOME_MONITORING_STARTED = (
    'Hienoa, aloitetaan! Kotiseuranta {start}–{end}: mittaa aamulla ja illalla, yhteensä {total} mittausta. {guide} '
    'Kirjaa mittaukset Tilanne nyt -näkymässä. Kokoan yhteenvedon, kun mittaukset on tehty.'
)
HOME_MONITORING_DECLINED = 'Selvä, ei tällä viikolla. Seuraan kotimittauksia tavalliseen tapaan ja kysyn kuulumisia {date}.'
HOME_MONITORING_EXPIRED = 'Ehdotus kotiseurannasta vanheni ilman vastausta.'
HOME_MONITORING_RESULT = {
    'continue': ('Kotiseuranta on valmis, kiitos! Keskiarvo {avg} mmHg ({n} mittausta) on sovitulla tavoitetasolla. '
                 'Jatketaan omahoitoa nykyisellä suunnitelmalla.'),
    'adjust': ('Kotiseuranta on valmis, kiitos! Keskiarvo {avg} mmHg ({n} mittausta) on hieman sovitun tavoitetason yläpuolella. '
               'Muutetaan suunnitelmaa pienesti {owner} hyväksymissä rajoissa: jatketaan kotimittauksia ja tämän viikon askelta '
               '({step}). Viikkotarkistuksessa {date} katsotaan, miten askel sujui.'),
    'professional': 'Kotiseuranta on valmis, kiitos! Keskiarvo {avg} mmHg ({n} mittausta).',
    'incomplete': ('Kotiseurannasta kirjattiin {n}/{total} mittausta, joten luotettavaa yhteenvetoa ei voi tehdä. '
                   'Seuraan tilannetta viikkotarkistuksessa {date}.'),
}
HOME_MONITORING_ALREADY_WITH_PROFESSIONAL = 'Ammattilainen on jo mukana seurannassasi, ja tulos on tallennettu seurantaasi.'

DIRECTION_REASONS = {
    'started': 'Ensimmäinen askel on käynnissä.',
    'stable': 'Tilanne on suunnitelman mukainen.',
    'goal_met': 'Viime kierroksen askel toteutui.',
    'goal_partial': 'Viime kierroksen askel toteutui osittain.',
    'goal_none': 'Viime kierroksen askel ei toteutunut{barrier}, joten askelta mukautettiin.',
    'trend_rising': 'Kotimittausten keskiarvo on noussut aiempiin mittauksiin verrattuna ({delta} mmHg).',
    'monitoring_offered': 'Ehdotin {days} kotiseurantaa.',
    'monitoring_active': 'Kotiseuranta on käynnissä ({n}/{total} mittausta).',
    'monitoring_above': 'Kotiseurannan keskiarvo {avg} mmHg oli sovitun tavoitetason yläpuolella.',
    'monitoring_ok': 'Kotiseurannan keskiarvo {avg} mmHg oli sovitulla tavoitetasolla.',
    'escalated': 'Automaattinen hoidon tarpeen arvio on tehty ({label}), ja {owner} ottaa yhteyttä {handling}.',
    'new_version': '{owner_cap} päivitti suunnitelman (versio {version}).',
    'lab_review': 'Seuraava laboratoriokontrolli on {date}.',
    'pending': '{owner_cap} käy ehdotuksen läpi ennen käyttöönottoa.',
    'paused': 'Seuranta on tauolla{until}.',
}
DIRECTION_PROFESSIONAL_WHEN = 'Otan ammattilaisen mukaan, jos:'
# the plan's escalation rules in the user's words (the rules themselves are written for the professional)
PROFESSIONAL_WHEN = {
    'goal_failures_and_above_target': 'askel ei toteudu kahdella peräkkäisellä viikolla ja kotimittausten keskiarvo on tavoitetason yläpuolella',
    'safety_threshold': 'yksittäinen kotimittaus on {systolic}/{diastolic} mmHg tai korkeampi',
    'data_missing': 'kotimittauksia ei ole kirjattu {days} päivään muistutuksista huolimatta',
    'home_monitoring_above': 'kotiseurannan keskiarvo on {systolic}/{diastolic} mmHg tai korkeampi',
    'user_request': 'pyydät itse ammattilaisen arviota tai yhteydenottoa',
}
PROFESSIONAL_WHEN_SYMPTOMS = 'kuvaat oireita, jotka vaativat yhteydenottoa (hoidon tarpeen arvio)'

CHAT_MEMORY_INTRO = 'Tässä on se, mitä muistan puolestasi:'
CHAT_MEMORY_NOTE = ('Kokosin tiedot suunnitelmistasi, ammattilaisten kirjauksista ja vastauksistasi sääntöjen perusteella. '
                    'En muuta sovittuja asioita itse – muutokset sovitaan ammattilaisen kanssa.')
CHAT_STEP_NONE = 'Sinulla ei ole nyt käynnissä olevaa askelta. Askel sovitaan, kun ammattilainen on hyväksynyt seurantasuunnitelman.'
CHAT_STEP = ('Tämän viikon askel: {step} ({start}–{end}). Kysyn {feedback}, miten meni. Palautteesi perusteella sovitan '
             'seuraavan askeleen: pienemmäksi, samaksi tai hieman isommaksi {owner} hyväksymissä rajoissa.')
CHAT_DIRECTION_INTRO = 'Seuraan koko ajan, riittääkö omahoito:'
CHAT_DIRECTION_NOTE = 'Suunta tulee ammattilaisen hyväksymistä säännöistä, ei kielimallilta. ' + RIGHTS_SENTENCE

