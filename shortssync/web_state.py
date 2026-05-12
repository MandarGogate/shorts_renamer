"""
Persistent web app state for configuration and staged match review.
"""

from __future__ import annotations

import json
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def validate_review_filename(filename: Any, label: str = 'Filename') -> str | None:
    if not isinstance(filename, str):
        return f'{label} must be a string'

    cleaned = filename.strip()
    if not cleaned:
        return f'{label} is required'

    if (
        '\x00' in cleaned
        or '/' in cleaned
        or '\\' in cleaned
        or cleaned in {'.', '..'}
        or Path(cleaned).name != cleaned
    ):
        return f'{label} must be a filename, not a path'

    return None


class WebStateStore:
    """Persist lightweight web state to JSON on disk."""

    VALID_DECISIONS = {'pending', 'approved', 'skipped'}

    def __init__(self, path: str | Path, defaults: dict[str, Any]):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._defaults = self._normalize_config(defaults)
        self._state = self._load()

    def _default_state(self) -> dict[str, Any]:
        return {
            'config': {},
            'review_batch': None,
        }

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._default_state()

        try:
            with open(self.path, 'r', encoding='utf-8') as handle:
                data = json.load(handle)
        except (json.JSONDecodeError, OSError):
            return self._default_state()

        if isinstance(data, dict):
            state = self._default_state()
            state.update(data)
            if not isinstance(state.get('config'), dict):
                state['config'] = {}
            if state.get('review_batch') is not None and not isinstance(state['review_batch'], dict):
                state['review_batch'] = None
            return state

        return self._default_state()

    def _save(self) -> None:
        tmp_path = self.path.with_suffix('.tmp')
        with open(tmp_path, 'w', encoding='utf-8') as handle:
            json.dump(self._state, handle, indent=2, ensure_ascii=False)
        tmp_path.replace(self.path)

    def _normalize_config(self, config: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(config)

        if 'preserve_exact_names' not in normalized and 'preserve_exact_titles' in normalized:
            normalized['preserve_exact_names'] = normalized['preserve_exact_titles']

        if 'preserve_exact_names' in normalized:
            normalized['preserve_exact_titles'] = normalized['preserve_exact_names']

        return normalized

    def get_config(self) -> dict[str, Any]:
        with self._lock:
            merged = self._normalize_config(self._defaults)
            merged.update(self._normalize_config(self._state.get('config', {})))
            return merged

    def update_config(self, updates: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            filtered = {
                key: value
                for key, value in self._normalize_config(updates).items()
                if key in self._defaults
            }
            current = self._normalize_config(self._state.get('config', {}))
            current.update(filtered)
            self._state['config'] = current
            self._save()
            return self.get_config()

    def _summarize_matches(self, matches: list[dict[str, Any]]) -> dict[str, int]:
        summary = {'pending': 0, 'approved': 0, 'skipped': 0}
        for match in matches:
            decision = match.get('decision', 'pending')
            if decision not in summary:
                decision = 'pending'
            summary[decision] += 1
        summary['total'] = len(matches)
        return summary

    def set_review_batch(self, video_dir: str, matches: list[dict[str, Any]]) -> dict[str, Any]:
        with self._lock:
            stored_matches = []
            for match in matches:
                item = deepcopy(match)
                item['id'] = uuid.uuid4().hex
                item['decision'] = 'pending'
                item['suggested_name'] = match['new_name']
                stored_matches.append(item)

            batch = {
                'id': uuid.uuid4().hex,
                'video_dir': video_dir,
                'created_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                'matches': stored_matches,
                'summary': self._summarize_matches(stored_matches),
            }
            self._state['review_batch'] = batch
            self._save()
            return deepcopy(batch)

    def get_review_batch(self) -> dict[str, Any] | None:
        with self._lock:
            batch = self._state.get('review_batch')
            if batch is None:
                return None

            copied = deepcopy(batch)
            if not isinstance(copied.get('matches'), list):
                copied['matches'] = []
            copied['summary'] = self._summarize_matches(copied.get('matches', []))
            return copied

    def update_match(
        self,
        match_id: str,
        *,
        decision: str | None = None,
        new_name: str | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            batch = self._state.get('review_batch')
            if not batch:
                return None

            for match in batch.get('matches', []):
                if match.get('id') != match_id:
                    continue

                if new_name is not None:
                    filename_error = validate_review_filename(new_name, 'New name')
                    if filename_error:
                        raise ValueError(filename_error)
                    cleaned_name = new_name.strip()
                    match['new_name'] = cleaned_name

                if decision is not None:
                    if decision not in self.VALID_DECISIONS:
                        raise ValueError(f"Invalid decision: {decision}")
                    match['decision'] = decision

                batch['summary'] = self._summarize_matches(batch.get('matches', []))
                self._save()
                return deepcopy(match)

        return None

    def approve_all(self) -> dict[str, Any] | None:
        with self._lock:
            batch = self._state.get('review_batch')
            if not batch:
                return None

            for match in batch.get('matches', []):
                if match.get('decision') != 'skipped':
                    match['decision'] = 'approved'

            batch['summary'] = self._summarize_matches(batch.get('matches', []))
            self._save()
            return deepcopy(batch)

    def remove_matches(self, match_ids: list[str]) -> dict[str, Any] | None:
        with self._lock:
            batch = self._state.get('review_batch')
            if not batch:
                return None

            ids = set(match_ids)
            matches = [
                match for match in batch.get('matches', [])
                if match.get('id') not in ids
            ]

            if not matches:
                self._state['review_batch'] = None
                self._save()
                return None

            batch['matches'] = matches
            batch['summary'] = self._summarize_matches(matches)
            self._save()
            return deepcopy(batch)

    def clear_review_batch(self) -> None:
        with self._lock:
            self._state['review_batch'] = None
            self._save()
