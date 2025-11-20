"""Application defaults.

This module now only exposes defaults and a helper to return them.
No JSON file I/O or project-local config paths are provided.
If you want to change defaults, edit `DEFAULT_SETTINGS` directly.
"""

DEFAULT_SETTINGS = {
    'video_dir': '/Users/mandargogate/Work/CC/036ToEdit',
    'audio_dir': '/Users/mandargogate/Work/CC/TrendingMusic',
    'fixed_tags': '#dance #viral #shorts',
    'pool_tags': '#fyp #viral #trending #foryou #reels',
    'preserve_exact_titles': True,
    'preserve_exact_names': False,
    'move_files': True,
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
}

def get_defaults():
    """Return a copy of the default settings dict."""
    return dict(DEFAULT_SETTINGS)
    
