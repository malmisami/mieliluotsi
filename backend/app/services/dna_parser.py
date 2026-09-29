from __future__ import annotations

import re
from pathlib import Path
from typing import Any

COMMENT_PREFIX = '#'


def parse_line(line: str) -> dict[str, Any]:
    stripped = line.strip()
    if not stripped or stripped.startswith(COMMENT_PREFIX):
        return {'valid': False, 'ignored': True}

    parts = stripped.split()
    if len(parts) < 4:
        return {'valid': False, 'ignored': False, 'error': 'Malformed line'}

    if len(parts) >= 10 and _looks_like_vcf(parts):
        return _parse_vcf_line(parts)

    rsid, chrom, pos_raw = parts[:3]
    genotype = ''.join(parts[3:5]) if len(parts) >= 5 else parts[3]
    if not rsid or not chrom or not pos_raw or not genotype:
        return {'valid': False, 'ignored': False, 'error': 'Missing required values'}

    chrom = chrom.strip().lower()
    if chrom.startswith('chr'):
        chrom = chrom[3:]
    if chrom not in {str(i) for i in range(1, 23)} | {'X', 'Y', 'MT'}:
        return {'valid': False, 'ignored': False, 'error': 'Unsupported chromosome'}

    try:
        pos = int(pos_raw)
    except ValueError:
        return {'valid': False, 'ignored': False, 'error': 'Invalid position'}

    if pos <= 0:
        return {'valid': False, 'ignored': False, 'error': 'Invalid position'}

    genotype = genotype.strip().replace('/', '').replace('|', '')
    valid = len(genotype) == 2 and all(allele in {'A', 'C', 'G', 'T'} for allele in genotype)

    if not valid:
        return {'valid': False, 'ignored': False, 'error': 'Unsupported genotype'}

    return {
        'valid': True,
        'ignored': False,
        'rsid': rsid,
        'chrom': chrom,
        'pos': pos,
        'genotype': genotype,
    }


def _looks_like_vcf(parts: list[str]) -> bool:
    return (
        parts[0].lower().removeprefix('chr') in {str(i) for i in range(1, 23)} | {'X', 'Y', 'M', 'MT'}
        and parts[1].isdigit()
        and all(base in {'A', 'C', 'G', 'T'} for base in parts[3].upper())
        and all(base in {'A', 'C', 'G', 'T'} for base in parts[4].split(',')[0].upper())
        and 'GT' in parts[8].split(':')
    )


def _parse_vcf_line(parts: list[str]) -> dict[str, Any]:
    chrom, pos_raw, rsid, ref, alt = parts[:5]
    format_fields = parts[8].split(':')
    sample_fields = parts[9].split(':')
    genotype_index = format_fields.index('GT')
    genotype_code = sample_fields[genotype_index]
    allele_indexes = re.split(r'[/|]', genotype_code)

    if len(allele_indexes) != 2 or any(index == '.' or not index.isdigit() for index in allele_indexes):
        return {'valid': False, 'ignored': False, 'error': 'Missing VCF genotype'}

    alleles = [ref.upper(), *[allele.upper() for allele in alt.split(',')]]
    try:
        genotype = ''.join(alleles[int(index)] for index in allele_indexes)
    except (IndexError, ValueError):
        return {'valid': False, 'ignored': False, 'error': 'Invalid VCF genotype'}

    normalized_chrom = chrom.lower().removeprefix('chr').upper()
    if normalized_chrom == 'M':
        normalized_chrom = 'MT'

    return {
        'valid': True,
        'ignored': False,
        'rsid': rsid if rsid != '.' else f'{normalized_chrom}:{pos_raw}',
        'chrom': normalized_chrom,
        'pos': int(pos_raw),
        'genotype': genotype,
    }
