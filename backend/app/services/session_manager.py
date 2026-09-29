from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.config import settings


SESSION_ROOT = Path(settings.SESSION_ROOT)
SESSION_ROOT.mkdir(parents=True, exist_ok=True)


class SessionManager:
    @staticmethod
    def create_session(input_source: str, mode: str, resource_profile: str, source_display_name: str, genome_build: str = 'GRCh38') -> dict[str, Any]:
        session_id = uuid.uuid4().hex
        session_dir = SESSION_ROOT / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        db_path = session_dir / 'session.sqlite'
        conn = sqlite3.connect(db_path)
        conn.execute('PRAGMA journal_mode=DELETE')
        conn.execute('PRAGMA synchronous=NORMAL')
        conn.execute('PRAGMA temp_store=FILE')
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA cache_size=-8192')
        conn.execute('''
            CREATE TABLE analysis_state (
                session_id TEXT PRIMARY KEY,
                status TEXT,
                stage TEXT,
                mode TEXT,
                resource_profile TEXT,
                genome_build TEXT,
                input_source TEXT,
                source_display_name TEXT,
                raw_file_path TEXT,
                created_at TEXT,
                updated_at TEXT,
                expires_at TEXT,
                parse_byte_offset INTEGER,
                parse_line_number INTEGER,
                parse_rows_processed INTEGER,
                match_cursor INTEGER,
                position_matches INTEGER,
                allele_matches INTEGER,
                error_code TEXT,
                error_message_fi TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE user_variants (
                input_order INTEGER PRIMARY KEY,
                rsid TEXT,
                chrom TEXT,
                pos INTEGER,
                genotype TEXT,
                allele_1 TEXT,
                allele_2 TEXT,
                source_line_number INTEGER
            )
        ''')
        conn.execute('''
            CREATE TABLE matched_findings (
                id TEXT PRIMARY KEY,
                rsid TEXT,
                chrom TEXT,
                pos INTEGER,
                ref TEXT,
                alt TEXT,
                genotype TEXT,
                alt_allele_count INTEGER,
                zygosity TEXT,
                gene TEXT,
                conditions TEXT,
                clinical_significance TEXT,
                category TEXT,
                review_status TEXT,
                review_stars INTEGER,
                variation_id TEXT,
                match_method TEXT,
                source TEXT,
                source_url TEXT,
                summary_fi TEXT,
                limitations_fi TEXT,
                inheritance_note_fi TEXT,
                synthetic INTEGER,
                data TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE parse_warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                warning_type TEXT,
                metadata TEXT
            )
        ''')
        now = datetime.now(timezone.utc).isoformat()
        expires = (datetime.now(timezone.utc) + timedelta(hours=settings.SESSION_TTL_HOURS)).isoformat()
        conn.execute(
            '''
            INSERT INTO analysis_state (
                session_id, status, stage, mode, resource_profile, genome_build, input_source,
                source_display_name, raw_file_path, created_at, updated_at, expires_at,
                parse_byte_offset, parse_line_number, parse_rows_processed, match_cursor,
                position_matches, allele_matches, error_code, error_message_fi
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                session_id,
                'created',
                'created',
                mode,
                resource_profile,
                genome_build,
                input_source,
                source_display_name,
                str(session_dir / 'raw_input.tmp'),
                now,
                now,
                expires,
                0,
                0,
                0,
                0,
                0,
                0,
                None,
                None,
            ),
        )
        conn.commit()
        conn.close()
        return {
            'session_id': session_id,
            'session_dir': session_dir,
            'db_path': db_path,
            'raw_file_path': session_dir / 'raw_input.tmp'
        }

    @staticmethod
    def get_session_db(session_id: str) -> sqlite3.Connection:
        session_dir = SESSION_ROOT / session_id
        db_path = session_dir / 'session.sqlite'
        if not db_path.exists():
            raise FileNotFoundError('Session not found')
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def get_state(session_id: str) -> dict[str, Any]:
        conn = SessionManager.get_session_db(session_id)
        row = conn.execute('SELECT * FROM analysis_state WHERE session_id=?', (session_id,)).fetchone()
        conn.close()
        return dict(row) if row else {}

    @staticmethod
    def update_state(session_id: str, **fields):
        conn = SessionManager.get_session_db(session_id)
        updates = []
        values = []
        for key, value in fields.items():
            updates.append(f'{key} = ?')
            values.append(value)
        values.append(session_id)
        conn.execute(f"UPDATE analysis_state SET {', '.join(updates)} WHERE session_id=?", values)
        conn.commit()
        conn.close()

    @staticmethod
    def update_state_with_now(session_id: str, **fields):
        fields['updated_at'] = datetime.now(timezone.utc).isoformat()
        SessionManager.update_state(session_id, **fields)

    @staticmethod
    def add_warning(session_id: str, warning_type: str, metadata: dict[str, Any]):
        conn = SessionManager.get_session_db(session_id)
        conn.execute('INSERT INTO parse_warnings (warning_type, metadata) VALUES (?, ?)', (warning_type, json.dumps(metadata)))
        conn.commit()
        conn.close()

    @staticmethod
    def cleanup_expired_sessions() -> int:
        deleted = 0
        now = datetime.now(timezone.utc)
        for item in SESSION_ROOT.iterdir():
            if not item.is_dir():
                continue
            session_db = item / 'session.sqlite'
            if not session_db.exists():
                continue
            state = SessionManager.get_state(item.name)
            expires_at = state.get('expires_at')
            if expires_at:
                try:
                    expires_dt = datetime.fromisoformat(expires_at)
                except Exception:
                    expires_dt = None
                if expires_dt and now > expires_dt:
                    SessionManager.delete_session(item.name)
                    deleted += 1
        return deleted

    @staticmethod
    def delete_session(session_id: str):
        session_dir = SESSION_ROOT / session_id
        if not session_dir.exists() or not session_dir.is_dir():
            return
        for file in session_dir.iterdir():
            if file.is_file():
                try:
                    file.unlink(missing_ok=True)
                except Exception:
                    pass
        try:
            session_dir.rmdir()
        except Exception:
            pass
