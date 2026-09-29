"""Fixed and template texts for Hyvinvointikumppani. Fixed safety texts never go through an LLM."""
from __future__ import annotations

from app.loop.models import GenomicFinding, HealthEvent
from app.loop.templates import fi_date, fi_value

EMERGENCY = (
    'Jos oireesi voivat viitata hätätilanteeseen tai vointisi on nopeasti heikentynyt, '
    'hakeudu välittömästi päivystysarvioon tai soita hätänumeroon 112.'
)
EMERGENCY_NOTE = (
    'Hätätilanne ei kuulu automaattisen hoidon tarpeen arvion piiriin: soita 112 tai Päivystysapuun 116 117. '
    'En arvioi hätätilanteen oireita enkä yhdistä niitä perimätietoon.'
)
# The fixed reason recorded on the excluded_emergency assessment (the rule engine's words, never the LLM's).
EMERGENCY_ASSESSMENT_REASON = 'Oirekuvaus viittaa mahdolliseen hätätilanteeseen.'
EMERGENCY_DECISION_BY = 'Kiinteä turvallisuussääntö: hätätilanne ei kuulu automaattisen hoidon tarpeen arvion piiriin (ei kielimallia)'
EMERGENCY_BASIS_STATEMENT = (
    'Viesti on kiinteä, ennalta hyväksytty hätäohje. Kielimallia ei käytetty. Hätätilanne kirjattiin sääntöjen perusteella, '
    'mutta se ei kuulu automaattisen hoidon tarpeen arvion piiriin.'
)

WHY_NOW_DISCLAIMER = (
    'Tämä ei ole diagnoosi tai hoitosuositus. '
    'Hyvinvointikumppani tekee hoidon tarpeen arvion automaattisesti; diagnoosit ja hoitopäätökset tekee ammattilainen.'
)
AI_UNAVAILABLE = 'AI-selitys ei ole juuri nyt käytettävissä. Seuranta ja sääntömoottori toimivat normaalisti.'

BASIS_LLM = 'LLM muotoili selityksen. Seurantatilan päätös tehtiin sääntömoottorissa.'
BASIS_TEMPLATE = 'Selitys muodostettiin valmiista tekstipohjasta (ei LLM:ää). Seurantatilan päätös tehtiin sääntömoottorissa.'
BASIS_FIXED = 'Vastaus on kiinteä, ennalta hyväksytty viesti. LLM:ää ei käytetty. Seurantatilaa ei muutettu.'
BASIS_FIXED_RULE = 'Viesti on kiinteä, ennalta hyväksytty teksti (ei LLM:ää). Seurantatilan päätös tehtiin sääntömoottorissa.'

GREETING = (
    'Hei! Olen Hyvinvointikumppanisi, ja pidän omahoitosi käynnissä arjessa myös vastaanottojen välissä. Muistan puolestasi '
    'tavoitteesi ja ammattilaisen kanssa sovitut asiat, otan itse yhteyttä, kun seurannassa tapahtuu jotain, ehdotan yhden '
    'realistisen askeleen kerrallaan ja huomaan, milloin omahoito ei enää riitä. Toimin ammattilaisen hyväksymän suunnitelman '
    'rajoissa: en tee diagnooseja enkä muuta hoitoa. Käytän vain tietoja, joiden käytön olet sallinut, enkä näe koko '
    'DNA-aineistoasi. Kaikki tämän demon tiedot ovat synteettisiä. '
    'Voit myös kuvata oireesi, niin teen hoidon tarpeen ja kiireellisyyden arvion automaattisesti – ja voit aina '
    'pyytää ammattilaisen tekemän arvion.'
)
PROACTIVE_NEW_OBSERVATION = 'Seurannassasi on uusi tapahtuma. Haluatko nähdä miksi se voi olla relevantti?'
PROACTIVE_TASK_DUE = (
    'Aiempi geneettiseen seurantaasi liittyvä huomio on edelleen avoinna. '
    'Onko asia jo käsitelty ammattilaisen kanssa?'
)
MISSING_INFO_INTRO = 'Tulkinnasta puuttuu yksi mahdollisesti merkityksellinen tieto. Haluatko täydentää sen nyt?'
RULE_UPDATED = 'Uusi tieto täydensi seurantaasi. Tämä ei ole diagnoosi, mutta ammattilaisen arvio voi olla perusteltu.'
STATE_CHANGED_PROMPT = 'Uusi tieto muutti seurannan tilaa. Haluatko nähdä miksi?'
SAVED_NO_CHANGE = 'Tieto tallennettiin seurantaasi. Sääntömoottori arvioi tilanteen uudelleen, eikä seurannan tila muuttunut.'

SUMMARY_CONFIRM = 'Voin muodostaa nykyiseen seurantaasi perustuvan yhteenvedon. Haluatko jatkaa?'
SUMMARY_READY = (
    'Yhteenveto on valmis. Siinä ovat kaikki seurannassa olevat geneettiset löydökset, niihin liittyvät '
    'terveystapahtumat aikajanalta (sekä erikseen tapahtumat, jotka eivät liity suoraan mihinkään löydökseen), '
    'puuttuvat tiedot, ehdotetut lisäselvitykset ja vastuullisuusrajaus. Tietoja ei lähetetty kenellekään.'
)
REMINDER_ASK = 'Milloin haluat muistutuksen?'
RESOLVE_ASK = 'Haluatko merkitä tämän huomion käsitellyksi?'
CANCELLED = 'Selvä, en tehnyt muutoksia.'
NO_OPEN_OBSERVATION = 'Seurannassasi ei ole nyt avointa huomiota.'
EXTRACTION_FAILED = (
    'En pystynyt tulkitsemaan vastausta varmasti, joten en tallentanut mitään. Voit kirjoittaa esimerkiksi: '
    '”Isäni sai sydäninfarktin 49-vuotiaana” tai ”Lähisuvussa ei ole ollut sydänsairauksia”.'
)
SKIPPED_QUESTION = 'Selvä. Voit täydentää tiedon myöhemmin kirjoittamalla sen tähän keskusteluun.'

DIAGNOSIS = (
    'En voi tehdä diagnoosia enkä arvioida, onko sinulla jokin sairaus tai kuinka todennäköisesti sairastut. '
    'Voin kertoa, mitä seurannassasi tällä hetkellä tiedetään:'
)
DIAGNOSIS_END = 'Diagnoosin tekee terveydenhuollon ammattilainen. Voin kuitenkin tehdä hoidon tarpeen ja kiireellisyyden arvion, jos kuvaat oireesi.'
OFFER_SUMMARY = 'Voin koota avoimen huomion tiedot yhteenvedoksi, jonka voit ottaa mukaan vastaanotolle.'
MEDICATION = (
    'En voi antaa ohjeita lääkkeen aloittamiseen, lopettamiseen tai annoksen muuttamiseen. '
    'Älä muuta lääkitystä ilman terveydenhuollon ammattilaisen arviota.'
)
GENERAL = (
    'Autan vain seurantasuunnitelmaasi liittyvissä asioissa, joten en vastaa yleisiin terveyskysymyksiin. '
    'Niihin saat luotettavan vastauksen terveydenhuollosta. Voin esimerkiksi kertoa seurantasi tilan, '
    'selittää huomion, valmistella yhteenvedon ammattilaiselle tai tehdä hoidon tarpeen ja kiireellisyyden arvion '
    'automaattisesti, jos kuvaat oireesi. Ammattilaisen arvion voi aina pyytää.'
)
GENETIC_DETAILS_HIDDEN = (
    'Olet valinnut, ettei perimätiedon yksityiskohtia näytetä. Seurannassasi on ammattilaisen hyväksymä perimätiedon '
    'havainto, jota käytetään vain taustatietona. Voit sallia yksityiskohtien näyttämisen Suostumukset-näkymässä.'
)

TASK_RESPONSE_REPLIES = {
    'yes': 'Kiitos. Merkitsin huomion käsitellyksi. Seuranta jatkuu normaalisti.',
    'not_yet': 'Selvä. Kysyn asiasta uudelleen {date}.',
    'no_reminder': 'Selvä, en muistuta tästä enää. Huomio pysyy avoimena Minun seuranta -näkymässä.',
    'not_relevant': 'Selvä. Merkitsin, että löydös todettiin epäolennaiseksi. Seuranta jatkuu.',
}

STATUS_NOTHING_ACUTE = (
    'Ei mitään akuuttia: seurannassasi ei ole avoimia huomioita tai odottavia tehtäviä, '
    'eikä viimeisen 3 kuukauden tuloksissa ole viitealueen ulkopuolisiksi merkittyjä arvoja.'
)
STATUS_ACUTE_HEADING = 'Huomioitavaa nyt:'
STATUS_RECENT_HEADING = 'Terveysaikajana, viimeiset 3 kuukautta:'
STATUS_NOTE = (
    'Tämä on yhteenveto tallennetuista tiedoistasi. Jos haluat hoidon tarpeen arvion, kuvaa oireesi; '
    'ammattilaisen arvion voi aina pyytää.'
)
STATUS_LATEST_ASSESSMENT = 'Viimeisin automaattinen arvio: {label} ({date}); ammattilaisen arvion voi pyytää.'

# --- automated assessment of the need for care and its urgency (the class always comes from the rule engine) -------
HUMAN_REVIEW_CHAT_REASON = 'Asiakas pyysi ammattilaisen tekemän arvion chatissa.'
HUMAN_REVIEW_CHAT_BASIS = 'Asiakas pyysi chatissa {date} ammattilaisen tekemän arvion.'
HUMAN_REVIEW_ALREADY = (
    'Olet jo pyytänyt ammattilaisen tekemän arvion ({date}). Ammattilainen ottaa sinuun yhteyttä, '
    'eikä tämä vaadi sinulta nyt muuta.'
)
HUMAN_REVIEW_SERVICE_CONTACT = (
    'Sinulla on aina oikeus terveydenhuollon ammattihenkilön tekemään arvioon. Sinulla ei ole nyt seurantasuunnitelmaa, '
    'jonka kautta voisin välittää pyynnön, joten ota yhteyttä palveluun: {contact}.'
)

FOCUS_INTRO = 'Kun yhdistän geneettisen seurantasi ja terveysaikajanasi, kiinnittäisin huomiota näihin:'
FOCUS_NOTE = 'Nämä ovat yleisiä huomioita tallennettujen tietojen pohjalta, eivät diagnoosi tai hoito-ohje.'

# What each monitored gene means for the timeline: which measurements would show its effect, and what
# to keep in mind when no such measurement exists.
FOCUS_BY_GENE: dict[str, dict] = {
    'LDLR': {'codes': ['LDL'], 'metric': 'LDL-kolesterolista',
             'why': 'LDL-kolesteroli on tämän löydöksen tärkein seurattava arvo.'},
    'APOE': {'codes': ['LDL', 'CHOL'], 'metric': 'kolesterolista',
             'why': 'Löydös liittyy rasva-aineenvaihduntaan, joten kolesteroliarvot kertovat sen merkityksestä sinulle.'},
    'MTHFR': {'codes': ['HCY'], 'metric': 'homokysteiinistä',
              'why': 'Löydöksen tulkinta on epävarma. Homokysteiinimittaus voi olla hyödyllinen vain, jos ammattilainen pitää sitä tarpeellisena.'},
    'F5': {'note': 'Veren hyytymiseen liittyvä löydös: kerro siitä terveydenhuollossa erityisesti ennen leikkauksia, '
                   'pitkiä matkoja tai hormonivalmisteiden aloittamista.'},
    'CYP2C19': {'note': 'Lääkevasteeseen liittyvä löydös: mainitse se aina, kun sinulle määrätään uusia lääkkeitä, '
                        'erityisesti verenohennuslääkkeitä.'},
    'BRCA1': {'note': 'Perinnölliseen syöpäalttiuteen liittyvä löydös: siitä voi keskustella perinnöllisyysneuvonnassa, '
                      'johon ammattilainen voi ohjata.'},
    'TP53': {'note': 'Perinnölliseen syöpäalttiuteen liittyvä löydös: siitä voi keskustella perinnöllisyysneuvonnassa, '
                     'johon ammattilainen voi ohjata.'},
}
CARDIO_GENES = {'LDLR', 'APOE', 'F5'}

LIFESTYLE_LABELS = {
    'liikunta': 'liikunta', 'ruokavalio': 'ruokavalio', 'tupakointi': 'nikotiinituotteet', 'alkoholi': 'alkoholi',
    'uni': 'uni', 'sukuhistoria': 'suvun sairaushistorian selvittäminen', 'seuranta': 'perusmittaukset',
    'stressi': 'palautuminen',
}

FLAG_SHORT = {
    'high': 'viitealueen yläpuolella',
    'low': 'viitealueen alapuolella',
    'normal': 'viitealueella',
    'unknown': 'viitealuetieto puuttuu',
}

STATUS_LABELS = {
    'monitoring': 'seuranta aktiivinen',
    'no_action': 'ei toimenpiteitä',
    'additional_information_needed': 'lisätietoa tarvitaan',
    'professional_review_recommended': 'ammattilaisen arvio suositeltu (perimätieto)',
    'waiting_for_user': 'odottaa toimintaasi',
    'waiting_for_professional_review': 'odottaa ammattilaisen arviota',
    'resolved': 'käsitelty',
    'dismissed': 'käsitelty (todettu epäolennaiseksi)',
}


def event_line(event: HealthEvent) -> str:
    value = fi_value(event)
    return f"{event.displayName}{': ' + value if value else ''} ({fi_date(event.date)})"


def explain_finding(finding: GenomicFinding, confirmation_label: str, status: str) -> str:
    return (
        f'{finding.title} on seurannassasi. {finding.description} '
        f'Luokitus: {finding.classification}. Vahvistustila: {confirmation_label}. '
        'Seuranta vertaa uusia terveystapahtumia löydökseen ennalta määritellyillä säännöillä. '
        f'Seurannan tila nyt: {STATUS_LABELS.get(status, status)}.'
    )


def explain_observation(title: str, events: list[HealthEvent], connection: str, rule_names: list[str]) -> str:
    event_text = '; '.join(event_line(e) for e in events)
    return (
        f'{title}. Huomio perustuu näihin tietoihin: {event_text}. {connection} '
        f"Tilan päätti sääntömoottori ({', '.join(rule_names)})."
    )

# The self-care continuity engine's answers (memory, this week's step, is self-care enough) are templates from
# app.support.continuity; the chat only routes the question.
CONTINUITY_UNAVAILABLE = 'Seurannan tietoja ei ole ladattu, joten minulla ei ole nyt muistettavaa. Palauta demo alkutilaan.'

