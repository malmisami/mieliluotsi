from __future__ import annotations

from typing import Any


def normalize_genotype(genotype: str) -> dict[str, Any]:
    raw = (genotype or '').strip()
    if not raw:
        return {
            'normalized_genotype': '',
            'alleles': [],
            'alt_allele_count': 0,
            'zygosity': 'unknown',
            'supported': False,
        }

    if '/' in raw:
        parts = raw.split('/')
        alleles = [p.strip() for p in parts if p.strip()]
    elif '|' in raw:
        parts = raw.split('|')
        alleles = [p.strip() for p in parts if p.strip()]
    else:
        alleles = [ch for ch in raw if ch.strip()]

    if len(alleles) == 1:
        # REF-only or unsupported genotype style
        alleles = [alleles[0], alleles[0]] if alleles[0] else []

    if len(alleles) == 2 and alleles[0] == alleles[1]:
        alt_count = sum(1 for allele in alleles if allele not in {'0', '.'})
        if alt_count == 0:
            zygosity = 'no_alt'
        else:
            zygosity = 'homozygous_alt'
        return {
            'normalized_genotype': raw,
            'alleles': alleles,
            'alt_allele_count': alt_count,
            'zygosity': zygosity,
            'supported': True,
        }

    if len(alleles) == 2 and alleles[0] != alleles[1]:
        alt_count = sum(1 for allele in alleles if allele not in {'0', '.'})
        if alt_count == 0:
            zygosity = 'no_alt'
        else:
            zygosity = 'heterozygous'
        return {
            'normalized_genotype': raw,
            'alleles': alleles,
            'alt_allele_count': alt_count,
            'zygosity': zygosity,
            'supported': True,
        }

    return {
        'normalized_genotype': raw,
        'alleles': alleles,
        'alt_allele_count': 0,
        'zygosity': 'unknown',
        'supported': False,
    }
