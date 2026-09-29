"""Legacy OmaGenomi API (DNA analysis, genetic-risk loop, care plans, Apple Health data).

Kept intact so the earlier application can be restored, but hidden from the product: the routes are mounted on the
main app only when LEGACY_FEATURES_ENABLED=1. `legacy_app` serves them standalone (used by the legacy tests).
The endpoint code below is moved verbatim from the former app/main.py.
"""
from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from fastapi import APIRouter, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

from app.config import settings
from app.loop.router import router as loop_router
from app.models import ConfigResponse, HealthResponse, MatchNextResponse, ParseNextResponse
from app.services.clinvar_repository import ClinVarRepository
from app.services.demo_repository import DemoRepository
from app.services.dna_parser import parse_line
from app.services.html_export import build_html_report
from app.services.report_builder import build_report
from app.services.resource_profiles import PROFILES
from app.services.session_manager import SessionManager
from app.support.router import router as support_router
from app.wellbeing.router import router as wellbeing_router

legacy_router = APIRouter(tags=['Legacy: OmaGenomi'])

batch_lock = Lock()


def _resolve_mode(mode: str | None) -> str:
    if mode in (None, 'auto'):
        return 'demo' if not ClinVarRepository.available() else 'clinvar'
    return mode


@legacy_router.get('/api/health')
def health() -> HealthResponse:
    return HealthResponse(
        status='ok',
        application_version=settings.APP_VERSION,
        mode=settings.OMAGENOMI_MODE,
        resource_profile_defaults={
            'ultralight': PROFILES['ultralight'],
            'light': PROFILES['light'],
            'normal': PROFILES['normal'],
        },
        active_batch_lock=batch_lock.locked(),
        demo_lookup_available=Path(settings.DEMO_LOOKUP_PATH).exists(),
        clinvar_db_available=ClinVarRepository.available(),
        clinvar_metadata=ClinVarRepository.metadata() if ClinVarRepository.available() else {},
    )


@legacy_router.get('/api/config')
def config() -> ConfigResponse:
    return ConfigResponse(
        supported_input_methods=['pasted_text', 'uploaded_file', 'quick_demo', 'full_demo'],
        quick_demo_available=Path(settings.DEMO_SNIPPET_PATH).exists(),
        full_demo_available=Path(settings.DEMO_DNA_PATH).exists(),
        supported_formats=['23andme_like', 'vcf'],
        supported_genome_build=['GRCh38'],
        upload_size_limit_mb=settings.MAX_UPLOAD_MB,
        paste_size_limit_mb=settings.MAX_PASTE_MB,
        current_mode=settings.OMAGENOMI_MODE,
        resource_profiles=PROFILES,
        privacy_behavior=[
            'Raaka-DNA-aineistoa ei lähetetä pilveen eikä säilytetä pysyvästi.',
            'Paikalliset väliaikaistiedostot poistetaan analyysin, peruutuksen tai vanhenemisen jälkeen.',
        ],
        session_expiry_hours=settings.SESSION_TTL_HOURS,
        limitations=[
            'Tutkimus- ja demokäyttöön. Ei diagnoosi eikä lääkinnällinen laite.',
            'Genotyping arrays inspect selected sites, not the full genome.',
        ],
    )


@legacy_router.get('/api/demo-snippet')
def demo_snippet() -> JSONResponse:
    text = DemoRepository.get_demo_snippet()
    return JSONResponse(
        content={
            'text': text,
            'synthetic': True,
            'genome_build': 'GRCh38',
            'not_for_medical_use': True,
            'metadata': {'label': 'Synthetic quick demo snippet'},
        },
        headers={'Cache-Control': 'no-store'},
    )


@legacy_router.get('/api/demo-file')
def demo_file():
    return FileResponse(
        path=settings.DEMO_DNA_PATH,
        filename=Path(settings.DEMO_DNA_PATH).name,
        media_type='text/plain',
    )


@legacy_router.post('/api/analysis/sessions/from-text')
async def create_session_from_text(request: Request):
    content_type = request.headers.get('content-type', '')
    if 'text/plain' not in content_type:
        raise HTTPException(status_code=400, detail='Content-Type tulee olla text/plain.')

    mode = _resolve_mode(request.query_params.get('mode'))
    resource_profile = request.query_params.get('resource_profile') or settings.DEFAULT_RESOURCE_PROFILE
    genome_build = request.query_params.get('genome_build') or 'GRCh38'

    max_bytes = settings.MAX_PASTE_MB * 1024 * 1024
    total = 0
    chunks = []
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail='Liian suuri paste. Käytä tiedostoa tai pienempää DNA-tekstiä.')
        chunks.append(chunk)

    session = SessionManager.create_session(
        input_source='pasted_text',
        mode=mode,
        resource_profile=resource_profile,
        source_display_name='pasted_text_input.txt',
        genome_build=genome_build,
    )
    Path(session['raw_file_path']).write_bytes(b''.join(chunks))
    return {'session_id': session['session_id'], 'next_action': 'Jatka esitarkastukseen'}


@legacy_router.post('/api/analysis/sessions/from-file')
async def create_session_from_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail='Tiedoston nimi puuttuu.')

    session = SessionManager.create_session(
        input_source='uploaded_file',
        mode=_resolve_mode(settings.OMAGENOMI_MODE),
        resource_profile=settings.DEFAULT_RESOURCE_PROFILE,
        source_display_name=file.filename,
        genome_build='GRCh38',
    )

    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    total = 0
    raw_path = Path(session['raw_file_path'])
    with raw_path.open('wb') as handle:
        while True:
            chunk = await file.read(settings.UPLOAD_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise HTTPException(status_code=413, detail='Liian suuri tiedosto. Käytä pienempää tiedostoa.')
            handle.write(chunk)

    return {'session_id': session['session_id'], 'next_action': 'Jatka esitarkastukseen'}


@legacy_router.post('/api/analysis/sessions/from-demo')
async def create_session_from_demo(payload: dict):
    kind = payload.get('kind')
    if kind == 'quick_snippet':
        source_path = settings.DEMO_SNIPPET_PATH
        input_source = 'quick_demo'
        source_display_name = 'quick_demo_snippet_GRCh38.txt'
    elif kind == 'full_100k':
        source_path = settings.DEMO_DNA_PATH
        input_source = 'full_demo'
        source_display_name = 'synthetic_100k_23andme_like_GRCh38.txt'
    else:
        raise HTTPException(status_code=400, detail='Tuntematon demo-tyyppi.')

    session = SessionManager.create_session(
        input_source=input_source,
        mode=_resolve_mode(payload.get('mode') or settings.OMAGENOMI_MODE),
        resource_profile=payload.get('resource_profile') or settings.DEFAULT_RESOURCE_PROFILE,
        source_display_name=source_display_name,
        genome_build='GRCh38',
    )

    Path(session['raw_file_path']).write_text(Path(source_path).read_text(encoding='utf-8'), encoding='utf-8')
    return {'session_id': session['session_id'], 'next_action': 'Jatka esitarkastukseen'}


@legacy_router.get('/api/analysis/sessions/{session_id}')
def get_session(session_id: str):
    state = SessionManager.get_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail='Istuntoa ei löytynyt.')

    return {
        'session_id': session_id,
        'state': state.get('status'),
        'stage': state.get('stage'),
        'counters': {
            'parse_rows_processed': state.get('parse_rows_processed', 0),
            'position_matches': state.get('position_matches', 0),
            'allele_matches': state.get('allele_matches', 0),
        },
        'next_action': 'Jatka esitarkastukseen',
        'warnings': [],
    }


@legacy_router.post('/api/analysis/sessions/{session_id}/preflight')
def preflight(session_id: str):
    state = SessionManager.get_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail='Istuntoa ei löytynyt.')

    raw_path = Path(state['raw_file_path'])
    if not raw_path.exists():
        raise HTTPException(status_code=410, detail='Aineryhmä on jo poistettu.')

    content = raw_path.read_text(encoding='utf-8', errors='ignore')
    sample_lines = [line for line in content.splitlines() if line.strip() and not line.lstrip().startswith('#')]
    warnings = []
    if not sample_lines:
        warnings.append('Ei näy DNA-sisältöä.')

    detected_format = 'unknown'
    if sample_lines:
        first_data = sample_lines[0].split()
        detected_format = 'vcf' if len(first_data) >= 8 and first_data[1].isdigit() else '23andme_like'

    return {
        'session_id': session_id,
        'detected_format': detected_format,
        'genome_build_status': 'GRCh38 detected' if 'GRCh38' in content else 'unknown',
        'file_size_bytes': raw_path.stat().st_size,
        'estimated_row_count': max(0, len(sample_lines)),
        'mode_available': True,
        'warnings': warnings,
        'next_action': 'Jatka varianttien käsittelyyn',
    }


@legacy_router.post('/api/analysis/sessions/{session_id}/parse-next')
def parse_next(session_id: str):
    state = SessionManager.get_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail='Istuntoa ei löytynyt.')

    if batch_lock.locked():
        raise HTTPException(status_code=409, detail='Toinen erä käsitellään jo. Yritä uudelleen.')

    batch_lock.acquire()
    try:
        raw_path = Path(state['raw_file_path'])
        if not raw_path.exists():
            raise HTTPException(status_code=410, detail='Tiedosto on jo poistettu.')

        text = raw_path.read_text(encoding='utf-8', errors='ignore')
        lines = text.splitlines()
        start = int(state.get('parse_byte_offset') or 0)
        batch_size = 2000

        conn = SessionManager.get_session_db(session_id)
        current_max = conn.execute('SELECT COALESCE(MAX(input_order), 0) FROM user_variants').fetchone()[0]
        processed_rows = 0
        valid_rows = 0
        invalid_rows = 0
        next_offset = min(start + batch_size, len(lines))

        for index, line in enumerate(lines[start:next_offset], start=start):
            parsed = parse_line(line)
            if parsed.get('ignored'):
                continue
            if not parsed.get('valid'):
                invalid_rows += 1
                continue

            current_max += 1
            conn.execute(
                'INSERT INTO user_variants (input_order, rsid, chrom, pos, genotype, allele_1, allele_2, source_line_number) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (
                    current_max,
                    parsed['rsid'],
                    parsed['chrom'],
                    parsed['pos'],
                    parsed['genotype'],
                    parsed['genotype'][0],
                    parsed['genotype'][-1],
                    index + 1,
                ),
            )
            valid_rows += 1
            processed_rows += 1

        conn.commit()
        conn.close()

        total_processed = int(state.get('parse_rows_processed', 0)) + valid_rows
        done = next_offset >= len(lines)

        SessionManager.update_state(
            session_id,
            status='parsed' if done else 'parsing',
            stage='parsed' if done else 'parsing',
            parse_byte_offset=next_offset,
            parse_rows_processed=total_processed,
            updated_at='now',
        )

        return ParseNextResponse(
            session_id=session_id,
            processed_rows=processed_rows,
            valid_rows=valid_rows,
            invalid_rows=invalid_rows,
            duplicate_rows=0,
            progress_estimate=f'{min(next_offset, len(lines))} / {len(lines)}',
            done=done,
            next_action='Jatka ClinVar-vertailuun' if done else 'Käsittele seuraava erä',
        )
    finally:
        batch_lock.release()


@legacy_router.post('/api/analysis/sessions/{session_id}/match-next')
def match_next(session_id: str):
    state = SessionManager.get_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail='Istuntoa ei löytynyt.')

    if batch_lock.locked():
        raise HTTPException(status_code=409, detail='Toinen erä käsitellään jo. Yritä uudelleen.')

    batch_lock.acquire()
    try:
        vcf_lookup = ClinVarRepository.load_vcf_lookup() if state.get('mode') == 'clinvar' else {}
        if vcf_lookup:
            lookup_by_key = vcf_lookup
        else:
            lookup_payload = DemoRepository.load_lookup()
            lookup_entries = lookup_payload.get('entries', [])
            lookup_by_key = {f"{entry['chrom']}:{entry['pos']}": entry for entry in lookup_entries}

        conn = SessionManager.get_session_db(session_id)
        batch_size = 2000
        current_cursor = int(state.get('match_cursor') or 0)
        rows = conn.execute(
            'SELECT * FROM user_variants WHERE input_order > ? ORDER BY input_order LIMIT ?',
            (current_cursor, batch_size),
        ).fetchall()

        position_matches = int(state.get('position_matches', 0))
        allele_matches = int(state.get('allele_matches', 0))
        processed_variants = 0

        for row in rows:
            processed_variants += 1
            key = f"{row['chrom']}:{row['pos']}"
            entry = lookup_by_key.get(key)
            if not entry:
                continue

            position_matches += 1
            genotype = row['genotype']
            alt = entry.get('alt', '')
            if alt and alt not in genotype and alt not in genotype.replace('|', ''):
                continue

            allele_matches += 1
            conn.execute(
                '''INSERT OR REPLACE INTO matched_findings (
                    id, rsid, chrom, pos, ref, alt, genotype, alt_allele_count,
                    zygosity, gene, conditions, clinical_significance, category,
                    review_status, review_stars, variation_id, match_method, source,
                    source_url, summary_fi, limitations_fi, inheritance_note_fi,
                    synthetic, data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    f"match-{row['input_order']}",
                    row['rsid'],
                    row['chrom'],
                    row['pos'],
                    entry.get('ref', ''),
                    entry.get('alt', ''),
                    row['genotype'],
                    1 if row['genotype'] not in ('CC', 'TT') else 2,
                    'heterozygous' if row['genotype'] not in ('CC', 'TT') else 'homozygous_alt',
                    entry.get('gene'),
                    json.dumps(entry.get('conditions', [])),
                    entry.get('clinical_significance'),
                    entry.get('category', 'other'),
                    entry.get('review_status'),
                    entry.get('review_stars', 0),
                    entry.get('variation_id'),
                    'coordinate_and_allele',
                    'ClinVar VCF' if vcf_lookup else 'ClinVar demo',
                    entry.get('source_url'),
                    entry.get('summary_fi'),
                    entry.get('limitations_fi'),
                    entry.get('inheritance_note_fi'),
                    0 if vcf_lookup else 1,
                    json.dumps(entry),
                ),
            )

        conn.commit()
        conn.close()

        new_cursor = current_cursor + processed_variants
        done = processed_variants < batch_size

        SessionManager.update_state(
            session_id,
            status='matched' if done else 'matching',
            stage='matched' if done else 'matching',
            match_cursor=new_cursor,
            position_matches=position_matches,
            allele_matches=allele_matches,
            updated_at='now',
        )

        return MatchNextResponse(
            session_id=session_id,
            processed_variants=processed_variants,
            position_matches=position_matches,
            allele_matches=allele_matches,
            progress=f'{new_cursor} / {int(SessionManager.get_state(session_id).get("parse_rows_processed", 0))}',
            done=done,
            next_action='Jatka löydösten luokitteluun' if done else 'Verrataan seuraava erä',
        )
    finally:
        batch_lock.release()


@legacy_router.post('/api/analysis/sessions/{session_id}/classify')
def classify(session_id: str):
    state = SessionManager.get_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail='Istuntoa ei löytynyt.')

    db = SessionManager.get_session_db(session_id)
    rows = db.execute('SELECT category FROM matched_findings').fetchall()
    counts = {
        'clinically_significant': 0,
        'uncertain_or_conflicting': 0,
        'pharmacogenetics': 0,
        'risk_or_association': 0,
        'other': 0,
    }
    for row in rows:
        category = row[0] or 'other'
        counts[category] = counts.get(category, 0) + 1
    db.close()

    SessionManager.update_state(session_id, status='classified', stage='classified', updated_at='now')
    return {'session_id': session_id, 'category_counts': counts, 'next_action': 'Muodosta raportti'}


@legacy_router.post('/api/analysis/sessions/{session_id}/finalize')
def finalize(session_id: str):
    state = SessionManager.get_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail='Istuntoa ei löytynyt.')

    report = build_report(session_id)
    SessionManager.update_state(session_id, status='report_ready', stage='report_ready', updated_at='now')
    return {'session_id': session_id, 'report': report, 'next_action': 'Raportti valmis'}


@legacy_router.get('/api/analysis/sessions/{session_id}/report')
def get_report(session_id: str):
    state = SessionManager.get_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail='Istuntoa ei löytynyt.')
    if state.get('stage') != 'report_ready':
        raise HTTPException(status_code=409, detail='Raportti ei ole vielä valmis.')
    return build_report(session_id)


@legacy_router.post('/api/analysis/sessions/{session_id}/pause')
def pause(session_id: str):
    SessionManager.update_state(session_id, status='paused', stage='paused', updated_at='now')
    return {'session_id': session_id, 'status': 'paused'}


@legacy_router.post('/api/analysis/sessions/{session_id}/resume')
def resume(session_id: str):
    SessionManager.update_state(session_id, status='resumed', stage='parsed', updated_at='now')
    return {'session_id': session_id, 'status': 'resumed'}


@legacy_router.delete('/api/analysis/sessions/{session_id}')
def delete_session(session_id: str):
    SessionManager.delete_session(session_id)
    return {'deleted': True}


@legacy_router.post('/api/analysis/cleanup-expired')
def cleanup_expired():
    return {'deleted_sessions': SessionManager.cleanup_expired_sessions()}


@legacy_router.post('/api/export/html')
def export_html(payload: dict):
    return Response(content=build_html_report(payload.get('report') or {}), media_type='text/html')


@legacy_router.get('/')
def root():
    return {'message': 'OmaGenomi Lite API'}


def include_legacy_routes(app: FastAPI) -> None:
    app.include_router(loop_router)
    app.include_router(support_router)
    app.include_router(wellbeing_router)
    app.include_router(legacy_router)


legacy_app = FastAPI(title='OmaGenomi Loop API (legacy)')
legacy_app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
include_legacy_routes(legacy_app)
