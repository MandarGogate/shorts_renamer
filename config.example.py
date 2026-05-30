"""Example local config override for ShortsSync.

Copy this file to ``config_local.py`` (which is git-ignored) and set your own
paths. Anything you put in ``DEFAULT_SETTINGS`` here overrides the values in
``config.py``. You only need to include the keys you want to change.

Alternatively, set the environment variables ``SHORTSSYNC_VIDEO_DIR`` and
``SHORTSSYNC_AUDIO_DIR`` instead of using this file.
"""

DEFAULT_SETTINGS = {
    # Where your short-form videos to be renamed live (top-level scan).
    'video_dir': '/path/to/your/videos',
    # Reference audio library (scanned recursively).
    'audio_dir': '/path/to/your/audio',
    # Optional preference overrides:
    # 'fixed_tags': '#shorts',
    # 'pool_tags': '#fyp #viral #trending',
    # 'move_files': False,
}
