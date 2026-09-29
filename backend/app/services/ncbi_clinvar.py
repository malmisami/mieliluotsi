from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote_plus

import httpx

NCBI_EUTILS = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils'


@lru_cache(maxsize=512)
def fetch_variant_details(query: str) -> dict:
    search_url = f'{NCBI_EUTILS}/esearch.fcgi'
    summary_url = f'{NCBI_EUTILS}/esummary.fcgi'
    try:
        with httpx.Client(timeout=8.0, follow_redirects=True) as client:
            search = client.get(search_url, params={'db': 'clinvar', 'term': query, 'retmode': 'json'})
            search.raise_for_status()
            ids = search.json().get('esearchresult', {}).get('idlist', [])[:5]
            if not ids:
                return {'query': query, 'records': [], 'url': f'https://www.ncbi.nlm.nih.gov/clinvar/?term={quote_plus(query)}'}

            summary = client.get(summary_url, params={'db': 'clinvar', 'id': ','.join(ids), 'retmode': 'json'})
            summary.raise_for_status()
            result = summary.json().get('result', {})
            records = []
            for uid in ids:
                item = result.get(uid, {})
                records.append({
                    'uid': uid,
                    'title': item.get('title'),
                    'description': item.get('description'),
                    'url': f'https://www.ncbi.nlm.nih.gov/clinvar/{uid}/',
                })
            return {'query': query, 'records': records, 'url': f'https://www.ncbi.nlm.nih.gov/clinvar/?term={quote_plus(query)}'}
    except (httpx.HTTPError, ValueError):
        return {'query': query, 'records': [], 'url': f'https://www.ncbi.nlm.nih.gov/clinvar/?term={quote_plus(query)}'}