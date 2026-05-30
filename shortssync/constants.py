"""Shared constants and file-enumeration helpers."""

import os
from typing import List

AUDIO_EXTS = ('.mp3', '.wav', '.m4a', '.flac', '.ogg')
VIDEO_EXTS = ('.mp4', '.mov', '.mkv')
MEDIA_EXTS = AUDIO_EXTS + VIDEO_EXTS


def iter_media_files(root: str, *, extensions: tuple = MEDIA_EXTS) -> List[str]:
    """Walk *root* recursively and return relative paths matching *extensions*.

    Skips hidden files/directories and common temp prefixes.
    """
    results: List[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip hidden directories in-place
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]
        for f in sorted(filenames):
            if f.startswith('.') or f.startswith('._'):
                continue
            if f.lower().endswith(extensions):
                results.append(os.path.relpath(os.path.join(dirpath, f), root))
    return results
