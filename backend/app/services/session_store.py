from __future__ import annotations

import json
import sqlite3
from pathlib import Path


class SessionStore:
    @staticmethod
    def ensure_schema(conn: sqlite3.Connection):
        conn.execute('''CREATE TABLE IF NOT EXISTS user_variants (
            input_order INTEGER PRIMARY KEY,
            rsid TEXT,
            chrom TEXT,
            pos INTEGER,
            genotype TEXT,
            allele_1 TEXT,
            allele_2 TEXT,
            source_line_number INTEGER
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS matched_findings (
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
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS parse_warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            warning_type TEXT,
            metadata TEXT
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS analysis_state (
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
        )''')
        conn.commit()
