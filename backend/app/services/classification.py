from __future__ import annotations


def classify_match(entry: dict) -> str:
    significance = (entry.get('clinical_significance') or '').lower()
    if 'pathogenic' in significance:
        return 'clinically_significant'
    if 'uncertain' in significance or 'conflicting' in significance:
        return 'uncertain_or_conflicting'
    if 'drug response' in significance:
        return 'pharmacogenetics'
    if 'risk factor' in significance or 'association' in significance or 'protective' in significance:
        return 'risk_or_association'
    return 'other'
