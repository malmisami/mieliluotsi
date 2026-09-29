"""Finnish texts for Hyvinvointidata. Data, interpretation and the next action are kept apart; no disease is named,
no percentages, no urgency words. Tested with the same deterministic safety check as the rest of the agent."""
from __future__ import annotations

TITLE_CHANGE = 'Huomasin muutoksen'
TITLE_POSITIVE = 'Hyvä kehitys'
MAIN_SIGNAL = '{subject} {verb} omasta tasostasi: viimeisen 7 päivän keskiarvo {current}, oma {days} päivän tasosi {baseline}.'
MAIN_SIGNAL_SPARSE = '{subject} {verb} omasta tasostasi: viimeisin {current}, oma tasosi {baseline}.'
OTHER_SIGNALS = 'Samalla {items}.'
OTHER_SIGNAL = '{noun} {verb} ({delta})'
AREA_NOTE = 'Nämä kuuluvat {area} seurantaasi.'
AREA_NOTE_ONE = 'Tämä kuuluu {area} seurantaasi.'
CONSECUTIVE = '{label}: omaa tasoasi {side} viimeiset {days} päivää.'
SIDE = {'up': 'korkeampi', 'down': 'matalampi'}
WHY_PERIOD = 'Vertailu: viimeiset 7 päivää ja oma {days} päivän tasosi ennen viimeisintä kuukautta.'
WHY_RULE = 'Muutos omasta tasostasi ylittää demo-policyn kynnyksen: {thresholds}. Kynnys tunnistaa muutoksen, se ei tee johtopäätöstä terveydestäsi.'
WHY_SOURCE = 'Lähde: {source}, päivittäiset yhteenvedot {start}–{end}.'

INTERPRETATION = ('Tällaiseen muutokseen voi olla monta syytä, esimerkiksi lyhyemmät yöunet, kuormittava ajanjakso, sairastelu '
                  'tai muutos liikunnassa. Data kertoo muutoksesta, ei sen syystä.')
INTERPRETATION_POSITIVE = 'Muutos on omaan tasoosi verrattuna myönteinen. Mikä on auttanut? Sitä kannattaa jatkaa.'
DISCUSS_INTRO = 'Katsotaan yhdessä. Hyvinvointidatassasi näkyy muutos, joka kuuluu {area} seurantaasi:'
DISCUSS_INTRO_POSITIVE = 'Hienoa kehitystä! Hyvinvointidatassasi näkyy myönteinen muutos, joka kuuluu {area} seurantaasi:'
DISCUSS_QUESTION = 'Mitä haluaisit tehdä?'
PROACTIVE = '{title}: {summary} {area_note} Haluatko, että katsotaan tätä yhdessä?'

ACTION_DISCUSS = 'Selvitetään yhdessä'
ACTION_CONTINUE = 'Jatka keskustelua'
ACTION_LATER = 'Ei nyt'
ACTION_REASONS = 'Käydään läpi mahdollisia syitä'
ACTION_FOLLOW = 'Seurataan viikon ajan'
ACTION_PROFESSIONAL = 'Haluan ammattilaisen arvion'
REASON_QUESTION = 'Mikä näistä kuvaa viime viikkojasi parhaiten?'
REASON_OPTIONS = [
    ('load', 'Kiireinen tai kuormittava jakso'),
    ('sleep', 'Olen nukkunut huonommin'),
    ('ill', 'Olen sairastellut'),
    ('activity', 'Liikun tavallista vähemmän'),
    ('unknown', 'En tunnista syytä'),
]
REASON_REPLIES = {
    'load': 'Kuormittava jakso näkyy usein palautumisessa. Liitin alle hyväksytyn ohjeen. Yksi pieni askel seuraaville 7 päivälle voisi olla '
            '10 minuutin rauhoittumishetki illalla.',
    'sleep': 'Uni ja palautuminen kulkevat usein yhdessä. Liitin alle hyväksytyn ohjeen. Kokeillaanko seuraavat 7 päivää yhtä asiaa: '
             'sama nukkumaanmenoaika joka ilta?',
    'ill': 'Sairastelu voi näkyä leposykkeessä ja HRV:ssä. Jos sinulla on nyt oireita, kuvaa ne minulle, niin arvioin hoidon tarpeen '
           'sääntöjen perusteella – tai pyydä ammattilaisen arvio.',
    'activity': 'Liikunnan väheneminen näkyy askelissa ja palautumisessa. Liitin alle hyväksytyn ohjeen. Kokeillaanko seuraavat 7 päivää '
                'yhtä asiaa: 20 minuutin kävely kolmena päivänä?',
    'unknown': 'Selvä, syytä ei aina tunnista. Seurataan tilannetta ja katsotaan, jatkuuko muutos.',
}
FOLLOW_UP = 'Seuraan {metrics} ja kerron {date}, miten viikko meni. Voit milloin tahansa kuvata oireita tai pyytää ammattilaisen arvion.'
FOLLOW_UP_POSITIVE = 'Jatketaan samaan malliin. Seuraan {metrics} ja kerron, jos jokin muuttuu.'
DISMISSED = 'Selvä, en nosta tätä nyt esiin. Muutos näkyy edelleen Hyvinvointidata-välilehdellä.'
GUIDE_LINE = '{title}: {text}'

CHAT_SUMMARY_INTRO = 'Hyvinvointidatasi ({source}) viimeiset 7 päivää omaan tasoosi verrattuna:'
CHAT_SUMMARY_NONE = 'Hyvinvointidataa ei ole yhdistetty. Voit yhdistää Apple Healthin Hyvinvointidata-välilehdellä.'
CHAT_SUMMARY_NOT_ALLOWED = 'Hyvinvointidatan käyttö ei ole sallittu suostumuksissasi, joten en käytä sitä.'
CHAT_SUMMARY_NO_CHANGES = 'Merkittäviä muutoksia omaan tasoosi verrattuna ei näy.'
CHAT_SUMMARY_NOTE = 'Luvut ovat päivittäisiä yhteenvetoja. Muutos ei ole diagnoosi – se on syy katsoa tilannetta yhdessä.'
