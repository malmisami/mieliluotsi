from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, ConfigDict


class HealthResponse(BaseModel):
    status: str
    application_version: str
    mode: str
    resource_profile_defaults: dict[str, dict[str, int | str]]
    active_batch_lock: bool
    demo_lookup_available: bool
    clinvar_db_available: bool
    clinvar_metadata: dict[str, Any] | None = None


class ConfigResponse(BaseModel):
    supported_input_methods: list[str]
    quick_demo_available: bool
    full_demo_available: bool
    supported_formats: list[str]
    supported_genome_build: list[str]
    upload_size_limit_mb: int
    paste_size_limit_mb: int
    current_mode: str
    resource_profiles: dict[str, dict[str, int | str]]
    privacy_behavior: list[str]
    session_expiry_hours: int
    limitations: list[str]


class CreateSessionResponse(BaseModel):
    session_id: str
    next_action: str


class SessionStateResponse(BaseModel):
    session_id: str
    state: str
    stage: str
    counters: dict[str, int]
    next_action: str
    warnings: list[str]


class ParseNextResponse(BaseModel):
    session_id: str
    processed_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    progress_estimate: str
    done: bool
    next_action: str


class MatchNextResponse(BaseModel):
    session_id: str
    processed_variants: int
    position_matches: int
    allele_matches: int
    progress: str
    done: bool
    next_action: str


class Finding(BaseModel):
    model_config = ConfigDict(extra='ignore')

    id: str
    rsid: str | None = None
    chrom: str
    pos: int
    ref: str
    alt: str
    genotype: str
    alt_allele_count: int
    zygosity: str
    gene: str | None = None
    conditions: list[str] = []
    clinical_significance: str | None = None
    clinical_significance_fi: str | None = None
    category: str
    review_status: str | None = None
    review_stars: int
    variation_id: str | None = None
    match_method: str
    source: str
    source_url: str | None = None
    summary_fi: str
    limitations_fi: str
    inheritance_note_fi: str | None = None
    synthetic: bool = True
    disease_observation: dict[str, Any] = {}
    classification_explanation_fi: str | None = None


class Report(BaseModel):
    report_version: str = '1.0'
    generated_at: str
    source_file: dict[str, Any]
    analysis: dict[str, Any]
    findings: list[Finding] = []
    warnings: list[str] = []
    limitations: list[str] = []
    provenance: dict[str, Any]
