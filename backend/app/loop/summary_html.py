from __future__ import annotations

import html

from app.loop.timeline import entry_line, group_entries


def _e(value) -> str:
    return html.escape('' if value is None else str(value))


def render_summary_html(summary: dict) -> str:
    finding = summary['finding']
    event = summary.get('event') or {}
    dates = summary['dates']
    value = f"{event.get('value', '')} {event.get('unit') or ''}".strip()
    missing = ''.join(f'<li>{_e(item)}</li>' for item in summary['missingInformation'])
    limitations = ''.join(f'<li>{_e(item)}</li>' for item in summary['limitations'])
    family = ''.join(
        f"<li>{_e(e['value'])} · kirjattu {_e(e['date'])} · käyttäjän kertoma ja vahvistama</li>" for e in summary.get('userConfirmedFamilyHistory', [])
    ) or '<li>Ei käyttäjän vahvistamaa sukuhistoriaa.</li>'
    relevant = ''.join(
        f"<li>{_e(e['displayName'])} {_e(e.get('value'))} {_e(e.get('unit') or '')} ({_e(e['date'])})</li>" for e in summary.get('relevantEvents', [])
    )
    rules = ''.join(f"<li>{_e(r['id'])} – {_e(r['name'])}</li>" for r in summary.get('rules', []))
    questions = ''.join(f'<li>{_e(q)}</li>' for q in summary.get('questionsForProfessional', []))
    return f"""<!DOCTYPE html>
<html lang="fi">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Ammattilaisyhteenveto – {_e(summary['syntheticPersonName'])}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 820px; padding: 0 1rem; color: #12263a; line-height: 1.5; }}
  h1 {{ font-size: 1.5rem; margin-bottom: 0.25rem; }}
  h2 {{ font-size: 1.1rem; margin: 1.4rem 0 0.4rem; color: #163f52; }}
  .synthetic {{ background: #fff4dc; border: 2px dashed #8a5500; color: #5c3900; padding: 0.6rem 0.8rem; font-weight: 700; }}
  .disclaimer {{ background: #edf3f5; border-left: 4px solid #18758b; padding: 0.8rem; font-weight: 600; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #c9d5de; padding: 0.45rem 0.6rem; text-align: left; vertical-align: top; }}
  th {{ background: #f3f6fb; width: 38%; }}
  @media print {{ .synthetic {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }} }}
</style>
</head>
<body>
<p class="synthetic">SYNTEETTINEN DEMOAINEISTO – ei oikean henkilön tietoja</p>
<h1>Yhteenveto terveydenhuollon ammattilaiselle</h1>
<p>OmaGenomi Loop · muodostettu {_e(summary['generatedAt'])} · huomio {_e(summary['observationId'])}</p>
<p class="disclaimer">{_e(summary['disclaimer'])}</p>

<h2>Henkilö</h2>
<table>
<tr><th>Nimi</th><td>{_e(summary['syntheticPersonName'])}</td></tr>
</table>

<h2>Johdanto</h2>
<p>{_e(summary['intro'])}</p>

<h2>Geneettinen löydös</h2>
<table>
<tr><th>Löydös</th><td>{_e(finding['title'])}</td></tr>
<tr><th>Geeni / variantti</th><td>{_e(finding['gene'])} · {_e(finding['variant'])}</td></tr>
<tr><th>Luokitus</th><td>{_e(finding['classification'])}</td></tr>
<tr><th>Vahvistustila</th><td>{_e(summary['confirmationLabel'])} ({_e(summary['confirmationStatus'])})</td></tr>
<tr><th>Evidenssin taso</th><td>{_e(summary['evidenceLevelLabel'])}</td></tr>
<tr><th>Lähde</th><td>{_e(summary['source'])}</td></tr>
</table>

<h2>Relevantti terveystapahtuma</h2>
<table>
<tr><th>Tapahtuma</th><td>{_e(event.get('displayName'))}</td></tr>
<tr><th>Arvo</th><td>{_e(value)}</td></tr>
<tr><th>Poikkeamamerkintä</th><td>{_e(event.get('abnormalFlag'))}</td></tr>
<tr><th>Tapahtuman lähde</th><td>{_e(event.get('source'))}</td></tr>
<tr><th>Alkuperäinen teksti</th><td>{_e(event.get('rawText'))}</td></tr>
</table>

<h2>Kaikki huomioon liittyvät terveystapahtumat</h2>
<ul>{relevant}</ul>

<h2>Käyttäjän vahvistama sukuhistoria</h2>
<ul>{family}</ul>

<h2>Päivämäärät</h2>
<table>
<tr><th>Löydöksen evidenssi tarkistettu</th><td>{_e(dates['findingLastReviewedAt'])}</td></tr>
<tr><th>Seuranta hyväksytty</th><td>{_e(dates['monitoringConsentedAt'])}</td></tr>
<tr><th>Terveystapahtuma</th><td>{_e(dates['eventDate'])}</td></tr>
<tr><th>Huomio muodostettu</th><td>{_e(dates['observationCreatedAt'])}</td></tr>
</table>

<h2>Miksi huomio muodostettiin</h2>
<p>{_e(summary['reason'])}</p>
<p><strong>Sääntömoottorin säännöt (synteettisiä demosääntöjä):</strong></p>
<ul>{rules}</ul>

<h2>Puuttuvat tiedot</h2>
<ul>{missing}</ul>

<h2>Käyttäjän kysymyksiä vastaanotolle</h2>
<ul>{questions}</ul>

<h2>Vastuullisuusrajaus</h2>
<ul>{limitations}</ul>
</body>
</html>
"""


def _unrelated_line(entry: dict) -> str:
    """One timeline entry; a lab order is one line with its result count, like in Omakanta."""
    if entry['orderSize'] > 1:
        return f"<li>{_e(entry_line(entry))} ({_e(entry['date'])})</li>"
    e = entry['events'][0]
    return f"<li>{_e(e['displayName'])} {_e(e.get('value'))} {_e(e.get('unit') or '')} ({_e(e['date'])})</li>"


def render_full_summary_html(summary: dict) -> str:
    missing = ''.join(f'<li>{_e(item)}</li>' for item in summary['missingInformation'])
    limitations = ''.join(f'<li>{_e(item)}</li>' for item in summary['limitations'])
    steps = ''.join(f'<li>{_e(item)}</li>' for item in summary['suggestedNextSteps']) or '<li>Ei ehdotettuja lisäselvityksiä.</li>'
    questions = ''.join(f'<li>{_e(q)}</li>' for q in summary.get('questionsForProfessional', []))
    unrelated = ''.join(_unrelated_line(entry) for entry in group_entries(summary.get('unrelatedEvents', []))) or '<li>Ei muita tapahtumia.</li>'

    def metric_line(metric: dict) -> str:
        points = ' → '.join(f"{_e(p['value'])} ({_e(p['date'])})" for p in metric['points'])
        return f"<li>{_e(metric['label'])} [{_e(metric['unit'])}]: {points}</li>"

    def finding_block(fv: dict) -> str:
        finding = fv['finding']
        events = ''.join(
            f"<li>{_e(e['displayName'])} {_e(e.get('value'))} {_e(e.get('unit') or '')} ({_e(e['date'])})</li>" for e in fv['relatedEvents']
        ) or '<li>Ei liittyviä tapahtumia aikajanalla.</li>'
        missing_items = ''.join(f'<li>{_e(item)}</li>' for item in fv['missingInformation']) or '<li>Ei puuttuvia tietoja.</li>'
        if fv['trackedMetrics']:
            metrics = ''.join(metric_line(m) for m in fv['trackedMetrics'])
        elif fv['hasDefinedMetric']:
            metrics = '<li>Ei vielä numeerisia mittaustuloksia aikajanalla.</li>'
        else:
            metrics = '<li>Ei tässä demossa määriteltyä seurattavaa mittaria (raakaehdokaslöydös ilman virallista seurantasääntöä).</li>'
        return f"""
<h3>{_e(finding['title'])}</h3>
<table>
<tr><th>Geeni / variantti</th><td>{_e(finding['gene'])} · {_e(finding['variant'])}</td></tr>
<tr><th>Luokitus</th><td>{_e(finding['classification'])}</td></tr>
<tr><th>Vahvistustila</th><td>{_e(fv['confirmationLabel'])}</td></tr>
<tr><th>Evidenssin taso</th><td>{_e(fv['evidenceLevelLabel'])}</td></tr>
<tr><th>Seurannan tila</th><td>{_e(fv['monitoringStatus'])}</td></tr>
</table>
<p><strong>Seurattava mittari ja sen kehitys:</strong></p>
<ul>{metrics}</ul>
<p><strong>Liittyvät terveystapahtumat aikajanalla:</strong></p>
<ul>{events}</ul>
<p><strong>Puuttuvat tiedot:</strong></p>
<ul>{missing_items}</ul>
"""

    findings_html = ''.join(finding_block(fv) for fv in summary['findings'])
    return f"""<!DOCTYPE html>
<html lang="fi">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Ammattilaisyhteenveto – {_e(summary['syntheticPersonName'])}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 820px; padding: 0 1rem; color: #12263a; line-height: 1.5; }}
  h1 {{ font-size: 1.5rem; margin-bottom: 0.25rem; }}
  h2 {{ font-size: 1.1rem; margin: 1.4rem 0 0.4rem; color: #163f52; }}
  h3 {{ font-size: 1rem; margin: 1.2rem 0 0.3rem; color: #163f52; }}
  .synthetic {{ background: #fff4dc; border: 2px dashed #8a5500; color: #5c3900; padding: 0.6rem 0.8rem; font-weight: 700; }}
  .disclaimer {{ background: #edf3f5; border-left: 4px solid #18758b; padding: 0.8rem; font-weight: 600; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #c9d5de; padding: 0.45rem 0.6rem; text-align: left; vertical-align: top; }}
  th {{ background: #f3f6fb; width: 38%; }}
  @media print {{ .synthetic {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }} }}
</style>
</head>
<body>
<p class="synthetic">SYNTEETTINEN DEMOAINEISTO – ei oikean henkilön tietoja</p>
<h1>Yhteenveto terveydenhuollon ammattilaiselle</h1>
<p>OmaGenomi Loop · muodostettu {_e(summary['generatedAt'])} · kaikki seurannassa olevat löydökset</p>
<p class="disclaimer">{_e(summary['disclaimer'])}</p>

<h2>Henkilö</h2>
<table>
<tr><th>Nimi</th><td>{_e(summary['syntheticPersonName'])}</td></tr>
</table>

<h2>Johdanto</h2>
<p>{_e(summary['intro'])}</p>

<h2>Geneettiset löydökset ja niihin liittyvät terveystapahtumat</h2>
{findings_html}

<h2>Muut terveystapahtumat (eivät liity suoraan mihinkään löydökseen)</h2>
<ul>{unrelated}</ul>

<h2>Ehdotettuja lisäselvityksiä</h2>
<ul>{steps}</ul>

<h2>Kaikki puuttuvat tiedot</h2>
<ul>{missing}</ul>

<h2>Käyttäjän kysymyksiä vastaanotolle</h2>
<ul>{questions}</ul>

<h2>Vastuullisuusrajaus</h2>
<ul>{limitations}</ul>
</body>
</html>
"""
