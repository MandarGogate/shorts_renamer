"""
ShortsSync - Shared modules for audio fingerprinting and video matching.
"""

from .fingerprint import get_fingerprint, get_fingerprint_cached, FingerprintCache
from .naming import generate_name, sanitize_filename
from .shazam_client import ShazamClient, ShazamCache, is_shazam_available, identify_song, get_song_name
from .utils import extract_audio_safe, get_fpcalc_path, VideoAudioExtractor

__all__ = [
    'get_fingerprint',
    'get_fingerprint_cached',
    'FingerprintCache',
    'generate_name',
    'sanitize_filename',
    'ShazamClient',
    'ShazamCache',
    'is_shazam_available',
    'identify_song',
    'get_song_name',
    'extract_audio_safe',
    'get_fpcalc_path',
    'VideoAudioExtractor',
]

__version__ = '1.0.0'
