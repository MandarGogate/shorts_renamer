"""
Filename generation and sanitization utilities.
"""

import os
import random
from pathlib import Path
from typing import Set, Optional


def sanitize_filename(name: str, max_length: Optional[int] = 100) -> str:
    """
    Sanitize a string for use as a filename.
    
    Removes or replaces characters that are invalid in filenames.
    """
    # Characters not allowed in filenames on most systems
    invalid_chars = '<>:"/\\|?*'
    
    # Replace invalid characters with underscore
    for char in invalid_chars:
        name = name.replace(char, '_')
    
    # Remove control characters
    name = ''.join(char for char in name if ord(char) >= 32)
    
    # Strip leading/trailing whitespace and dots
    name = name.strip(' .')
    
    # Limit length
    if max_length is not None and len(name) > max_length:
        name = name[:max_length].rsplit(' ', 1)[0]  # Try to break at word boundary
    
    return name


def truncate_intelligently(text: str, max_length: int = 100) -> str:
    """
    Truncate text intelligently without cutting words/tags in half.
    
    Args:
        text: Text to truncate
        max_length: Maximum length
    
    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text
    
    # Split into parts and rebuild within limit
    parts = text.split()
    truncated = []
    current_length = 0
    
    for part in parts:
        # Account for space between parts
        added_length = len(part) + (1 if truncated else 0)
        if current_length + added_length <= max_length:
            truncated.append(part)
            current_length += added_length
        else:
            break
    
    return " ".join(truncated)


def generate_name(
    ref_name: str,
    vid_name: str,
    vid_dir: str,
    used_names: Set[str],
    fixed_tags: str = "",
    pool_tags: str = "",
    preserve_exact: bool = False,
    max_length: int = 100,
    max_attempts: int = 20
) -> str:
    """
    Generate a unique filename based on reference audio name.
    
    Args:
        ref_name: Reference audio filename (e.g., "Song Title.mp3")
        vid_name: Original video filename (e.g., "video123.mp4")
        vid_dir: Directory where video will be saved
        used_names: Set of already-used lowercase filenames
        fixed_tags: Fixed tags to append (e.g., "#shorts")
        pool_tags: Space-separated pool of random tags to choose from
        preserve_exact: If True, don't add tags, just ensure uniqueness
        max_length: Maximum filename length (excluding extension)
        max_attempts: Maximum attempts to find unique name
    
    Returns:
        Unique filename with proper extension
    """
    base = os.path.splitext(ref_name)[0]
    ext = os.path.splitext(vid_name)[1]
    
    # Sanitize base name without truncating first.
    # We reserve filename space based on suffix/tags per candidate so we don't
    # chop song metadata prematurely.
    base = sanitize_filename(base, max_length=None)
    
    if preserve_exact:
        # Try exact name first
        exact_base = truncate_intelligently(base, max_length)
        candidate = f"{exact_base}{ext}"
        full_path = os.path.join(vid_dir, candidate)
        
        if not os.path.exists(full_path) and candidate.lower() not in used_names:
            return candidate
        
        # Try with incrementing numbers
        for i in range(1, 100):
            suffix = f"_{i}"
            truncated = truncate_intelligently(base, max(1, max_length - len(suffix)))
            candidate = f"{truncated}{suffix}{ext}"
            full_path = os.path.join(vid_dir, candidate)
            if not os.path.exists(full_path) and candidate.lower() not in used_names:
                return candidate
        
        # Fallback to random number
        return f"{base}_{random.randint(1000, 9999)}{ext}"
    
    # Parse pool tags
    pool = pool_tags.split() if pool_tags else []
    fixed = fixed_tags.strip() if fixed_tags else ""
    
    # Try different tag combinations
    for _ in range(max_attempts):
        # Select random tags from pool
        if pool:
            num_tags = min(2, len(pool))
            tags = random.sample(pool, k=num_tags)
            tag_str = " ".join(tags)
        else:
            tag_str = ""
        
        # Build suffix first so we can reserve room for tags and keep base intact.
        suffix_parts = []
        if fixed:
            suffix_parts.append(fixed)
        if tag_str:
            suffix_parts.append(tag_str)
        suffix = " ".join(suffix_parts).strip()

        if suffix:
            available_base_len = max(1, max_length - len(suffix) - 1)
            base_part = truncate_intelligently(base, available_base_len)
            full = f"{base_part} {suffix}".strip()
        else:
            full = truncate_intelligently(base, max_length)
        
        candidate = f"{full}{ext}"
        full_path = os.path.join(vid_dir, candidate)
        
        if not os.path.exists(full_path) and candidate.lower() not in used_names:
            return candidate
    
    # Fallback: use base with random number
    return f"{base}_{random.randint(1000, 9999)}{ext}"
def build_reference_label(
    source_path: str,
    preferred_name: Optional[str],
    used_labels: Set[str]
) -> str:
    """
    Build a readable, unique label for a reference track.

    Recursive indexing can surface multiple files with the same basename or
    Shazam-derived title. This helper preserves the first label as-is, then
    appends parent folders only when needed to avoid silent overwrites.
    """
    label = (preferred_name or "").strip() or os.path.basename(source_path)

    if label.lower() not in used_labels:
        return label

    parent = Path(source_path).parent
    if parent != Path("."):
        parts = parent.parts
        for depth in range(1, len(parts) + 1):
            context = Path(*parts[-depth:]).as_posix()
            candidate = f"{label} [{context}]"
            if candidate.lower() not in used_labels:
                return candidate

    for index in range(2, 1000):
        candidate = f"{label} [{index}]"
        if candidate.lower() not in used_labels:
            return candidate

    return f"{label} [{random.randint(1000, 9999)}]"
