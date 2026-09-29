from __future__ import annotations

import json
from pathlib import Path

from app.config import settings


class DemoRepository:
    @staticmethod
    def load_manifest() -> dict:
        manifest_path = Path(settings.DEMO_MANIFEST_PATH)
        if not manifest_path.exists():
            raise FileNotFoundError(f'Manifest missing: {manifest_path}')
        return json.loads(manifest_path.read_text(encoding='utf-8'))

    @staticmethod
    def load_lookup() -> dict:
        lookup_path = Path(settings.DEMO_LOOKUP_PATH)
        if not lookup_path.exists():
            raise FileNotFoundError(f'Demo lookup missing: {lookup_path}')
        return json.loads(lookup_path.read_text(encoding='utf-8'))

    @staticmethod
    def get_demo_snippet() -> str:
        snippet_path = Path(settings.DEMO_SNIPPET_PATH)
        if not snippet_path.exists():
            raise FileNotFoundError(f'Demo snippet missing: {snippet_path}')
        return snippet_path.read_text(encoding='utf-8')

    @staticmethod
    def get_demo_file_path() -> Path:
        demo_path = Path(settings.DEMO_DNA_PATH)
        if not demo_path.exists():
            raise FileNotFoundError(f'Demo DNA file missing: {demo_path}')
        return demo_path
