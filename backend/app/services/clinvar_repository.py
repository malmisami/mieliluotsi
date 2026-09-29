from __future__ import annotations

import sqlite3
import gzip
from pathlib import Path

from app.config import settings


class ClinVarRepository:
    @staticmethod
    def vcf_path() -> Path | None:
        if not settings.CLINVAR_VCF_PATH:
            return None
        path = Path(settings.CLINVAR_VCF_PATH)
        return path if path.exists() else None

    @staticmethod
    def available() -> bool:
        return Path(settings.CLINVAR_DB_PATH).exists() or ClinVarRepository.vcf_path() is not None

    @staticmethod
    def load_vcf_lookup() -> dict[str, dict]:
        path = ClinVarRepository.vcf_path()
        if path is None:
            return {}

        opener = gzip.open if path.suffix == '.gz' else open
        lookup = {}
        with opener(path, 'rt', encoding='utf-8', errors='replace') as handle:
            for line in handle:
                if not line.strip() or line.startswith('#'):
                    continue
                parts = line.rstrip('\n').split('\t')
                if len(parts) < 5:
                    continue
                chrom, pos_raw, rsid, ref, alt_raw = parts[:5]
                try:
                    pos = int(pos_raw)
                except ValueError:
                    continue
                info = _parse_info(parts[7] if len(parts) > 7 else '')
                for alt in alt_raw.split(','):
                    key = f'{chrom.removeprefix("chr")}:{pos}'
                    lookup.setdefault(key, {
                        'rsid': rsid if rsid != '.' else None,
                        'chrom': chrom.removeprefix('chr'),
                        'pos': pos,
                        'ref': ref,
                        'alt': alt,
                        'gene': info.get('GENEINFO', '').split(':')[0] or None,
                        'conditions': info.get('CLNDN', '').replace('|', ', ').split(', ') if info.get('CLNDN') else [],
                        'clinical_significance': info.get('CLNSIG', '').replace('|', ', ') or None,
                        'category': 'other',
                        'review_status': info.get('CLNREVSTAT') or None,
                        'review_stars': 0,
                        'variation_id': info.get('ALLELEID') or None,
                        'source_url': None,
                        'summary_fi': 'Löydös löytyi paikallisesta VCF-vertailutiedostosta.',
                        'limitations_fi': 'VCF-tiedoston sisältö ja annotaatiot määrittävät löydöksen tarkkuuden.',
                        'inheritance_note_fi': None,
                        'synthetic': False,
                    })
        return lookup

    @staticmethod
    def metadata() -> dict[str, str]:
        db_path = Path(settings.CLINVAR_DB_PATH)
        if not db_path.exists():
            return {}

        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute('SELECT key, value FROM clinvar_metadata').fetchall()
            return {row[0]: row[1] for row in rows}
        finally:
            conn.close()


def _parse_info(raw_info: str) -> dict[str, str]:
    values = {}
    for item in raw_info.split(';'):
        if '=' in item:
            key, value = item.split('=', 1)
            values[key] = value
    return values
