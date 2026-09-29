from __future__ import annotations

import html


def build_html_report(report: dict) -> str:
    findings_html = []
    for finding in report.get('findings', []):
        findings_html.append(
            f"""
            <article class=\"finding\">
                <h3>{html.escape(finding.get('gene') or finding.get('rsid') or 'Unknown')}</h3>
                <p><strong>Luokitus:</strong> {html.escape(finding.get('clinical_significance') or '-')}</p>
                <p><strong>Kategoria:</strong> {html.escape(finding.get('category') or '-')}</p>
                <p><strong>RsID:</strong> {html.escape(finding.get('rsid') or '-')}</p>
                <p>{html.escape(finding.get('summary_fi') or '')}</p>
            </article>
            """
        )

    return f"""
    <!DOCTYPE html>
    <html lang=\"fi\">
      <head>
        <meta charset=\"UTF-8\" />
        <title>OmaGenomi Lite raportti</title>
        <style>
          body {{ font-family: sans-serif; margin: 2rem; color: #132b3d; }}
          .finding {{ border: 1px solid #d0d8df; padding: 1rem; margin-bottom: 1rem; border-radius: 10px; }}
          .disclaimer {{ background: #edf3f5; padding: 0.9rem; border-left: 4px solid #18758b; margin-bottom: 1rem; }}
        </style>
      </head>
      <body>
        <h1>OmaGenomi Lite</h1>
        <div class=\"disclaimer\">
          <strong>Tutkimus- ja demokäyttöön. Ei diagnoosi eikä lääkinnällinen laite.</strong>
        </div>
        <p>Raaka-DNA-aineistoa ei lähetetä pilveen eikä säilytetä pysyvästi.</p>
        {''.join(findings_html)}
      </body>
    </html>
    """
