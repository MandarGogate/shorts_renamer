"""Application defaults.

Paths are intentionally **not** hardcoded here so this file can be committed
without leaking a personal directory layout. Resolution order for the source
directories:

1. ``SHORTSSYNC_VIDEO_DIR`` / ``SHORTSSYNC_AUDIO_DIR`` environment variables.
2. An optional, untracked ``config_local.py`` (see ``config.example.py``).
3. Empty string -> the CLI/GUI/web will ask you to provide a directory.

Non-path defaults (tags, matching flags) can be tuned directly below.
"""

import os

DEFAULT_SETTINGS = {
    'video_dir': os.environ.get('SHORTSSYNC_VIDEO_DIR', ''),
    'audio_dir': os.environ.get('SHORTSSYNC_AUDIO_DIR', ''),
    'fixed_tags': '#dance #viral #shorts',
    'pool_tags': '#fyp #trending #foryou #trend',
    'preserve_exact_titles': True,
    'preserve_exact_names': False,
    'move_files': False,
    'feature_method': 'combined',
    # Alignment / scoring defaults
    'use_alignment': True,
    # 'auto' will try DTW (dtw-python) then fall back to correlation
    'alignment_method': 'auto',
    # Weight given to DTW-cost-derived similarity vs alignment confidence
    # combined_score = weight * similarity + (1-weight) * alignment_confidence
    'alignment_weight': 0.5,
    # Combined similarity threshold in [0,1] above which a match is accepted
    'similarity_threshold': 0.55,
    # DTW cost threshold used for early rejection (kept for legacy)
    'match_threshold': 60.0,
    # Minimum audio length (seconds) to attempt DTW alignment; below this use correlation
    'alignment_min_length_seconds': 0.5,
    # Require the best match to be significantly better than runner-up (higher = stricter)
    'min_cost_margin': 6.0,
    # Minimum alignment confidence (0-1) we accept when alignment succeeds
    'min_alignment_confidence': 0.3,
    # If True, we must have alignment_conf >= min_alignment_confidence to accept any match
    'require_alignment_for_match': False,
    # Shazam settings
    'use_shazam': False,  # Enable Shazam to identify reference audio files during indexing
    'shazam_only_mode': True,  # Use Shazam for renaming without running Chromaprint first
    'use_shazam_fallback': True,  # Use Shazam as fallback for unmatched videos
    'save_new_audio': True,  # Save Shazam-identified audio to reference library
    'shazam_fallback_any': True,  # Use Shazam name directly when song not in reference library
    # Slowed audio detection
    'detect_slowed': True,  # Detect slowed videos and add [SLOWED] label
    'slowed_speeds': [],  # Speed factors to check for slowed detection
}

# Optional local overrides kept out of version control (see config.example.py).
try:
    from config_local import DEFAULT_SETTINGS as _LOCAL_SETTINGS  # type: ignore
    if isinstance(_LOCAL_SETTINGS, dict):
        DEFAULT_SETTINGS.update(_LOCAL_SETTINGS)
except ImportError:
    pass


def get_defaults():
    """Return a copy of the default settings dict."""
    return dict(DEFAULT_SETTINGS)
