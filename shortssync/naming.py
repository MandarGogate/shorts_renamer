"""
Filename generation and sanitization utilities.
"""

import os
import random
import re
from pathlib import Path
from typing import Set, Optional


def sanitize_filename(name: str, max_length: int = 100) -> str:
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
    if len(name) > max_length:
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
    
    # Sanitize base name
    base = sanitize_filename(base, max_length)
    
    if preserve_exact:
        # Try exact name first
        candidate = f"{base}{ext}"
        full_path = os.path.join(vid_dir, candidate)
        
        if not os.path.exists(full_path) and candidate.lower() not in used_names:
            return candidate
        
        # Try with incrementing numbers
        for i in range(1, 100):
            candidate = f"{base}_{i}{ext}"
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
        
        # Build full name
        if fixed and tag_str:
            full = f"{base} {fixed} {tag_str}"
        elif fixed:
            full = f"{base} {fixed}"
        elif tag_str:
            full = f"{base} {tag_str}"
        else:
            full = base
        
        full = full.strip()
        
        # Truncate intelligently
        full = truncate_intelligently(full, max_length)
        
        candidate = f"{full}{ext}"
        full_path = os.path.join(vid_dir, candidate)
        
        if not os.path.exists(full_path) and candidate.lower() not in used_names:
            return candidate
    
    # Fallback: use base with random number
    return f"{base}_{random.randint(1000, 9999)}{ext}"


def generate_name_from_shazam(
    shazam_result: dict,
    vid_name: str,
    vid_dir: str,
    used_names: Set[str],
    fixed_tags: str = "",
    pool_tags: str = "",
    max_length: int = 100
) -> str:
    """
    Generate filename from Shazam identification result.
    
    Args:
        shazam_result: Dict with 'title', 'artist', 'album', etc.
        vid_name: Original video filename
        vid_dir: Directory where video will be saved
        used_names: Set of already-used lowercase filenames
        fixed_tags: Fixed tags to append
        pool_tags: Space-separated pool of random tags
        max_length: Maximum filename length
    
    Returns:
        Unique filename with proper extension
    """
    artist = shazam_result.get('artist', 'Unknown Artist')
    title = shazam_result.get('title', 'Unknown Title')
    
    # Create base name: "Artist - Title"
    base = f"{artist} - {title}"
    
    # Use the standard generate_name with preserve_exact=False to add tags
    return generate_name(
        ref_name=base,
        vid_name=vid_name,
        vid_dir=vid_dir,
        used_names=used_names,
        fixed_tags=fixed_tags,
        pool_tags=pool_tags,
        preserve_exact=False,
        max_length=max_length
    )
