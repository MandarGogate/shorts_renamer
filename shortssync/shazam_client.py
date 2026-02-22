"""
ShazamIO integration for song identification with caching.
"""

import os
import json
import hashlib
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
import time

# Try to import shazamio
try:
    from shazamio import Shazam
    SHAZAM_AVAILABLE = True
except ImportError:
    SHAZAM_AVAILABLE = False


@dataclass
class ShazamResult:
    """Structured result from Shazam identification."""
    title: str
    artist: str
    album: str = ""
    genre: str = ""
    year: str = ""
    shazam_id: str = ""
    shazam_url: str = ""
    album_art_url: str = ""
    identified_at: float = 0.0
    confidence: str = "high"  # Shazam doesn't give numeric confidence
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ShazamResult':
        return cls(**data)
    
    def get_filename_base(self) -> str:
        """Get a clean filename base from the result."""
        if self.artist and self.title:
            return f"{self.artist} - {self.title}"
        return self.title or self.artist or "Unknown"


class ShazamCache:
    """Cache for Shazam identification results."""
    
    def __init__(self, cache_dir: str = ".shazam_cache"):
        self.cache_path = Path(cache_dir)
        self.cache_path.mkdir(exist_ok=True)
        self._index_file = self.cache_path / "index.json"
        self._index = self._load_index()
    
    def _get_cache_key(self, audio_path: str) -> str:
        """Generate cache key from file content hash."""
        try:
            # Use file content hash for true fingerprint-based caching
            stat = os.stat(audio_path)
            key_data = f"{stat.st_size}:{stat.st_mtime}"
            return hashlib.md5(key_data.encode()).hexdigest()
        except (OSError, IOError):
            return hashlib.md5(audio_path.encode()).hexdigest()
    
    def _get_cache_file(self, cache_key: str) -> Path:
        """Get path to cache file for a key."""
        return self.cache_path / f"{cache_key}.json"
    
    def _load_index(self) -> Dict[str, Any]:
        """Load cache index."""
        if self._index_file.exists():
            try:
                with open(self._index_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {}
    
    def _save_index(self):
        """Save cache index."""
        try:
            with open(self._index_file, 'w', encoding='utf-8') as f:
                json.dump(self._index, f, indent=2)
        except IOError:
            pass
    
    def get(self, audio_path: str) -> Optional[ShazamResult]:
        """Get cached result if valid."""
        cache_key = self._get_cache_key(audio_path)
        cache_file = self._get_cache_file(cache_key)
        
        if not cache_file.exists():
            return None
        
        try:
            # Verify file hasn't changed
            current_stat = os.stat(audio_path)
            cached_info = self._index.get(cache_key, {})
            
            if (cached_info.get('size') == current_stat.st_size and
                cached_info.get('mtime') == current_stat.st_mtime):
                
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return ShazamResult.from_dict(data)
                    
        except (OSError, IOError, json.JSONDecodeError, KeyError):
            pass
        
        # Cache invalid
        self._remove_cache_entry(cache_key)
        return None
    
    def set(self, audio_path: str, result: ShazamResult):
        """Cache a Shazam result."""
        cache_key = self._get_cache_key(audio_path)
        cache_file = self._get_cache_file(cache_key)
        
        try:
            # Save result
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(result.to_dict(), f, indent=2)
            
            # Update index
            stat = os.stat(audio_path)
            self._index[cache_key] = {
                'path': audio_path,
                'size': stat.st_size,
                'mtime': stat.st_mtime,
                'cached_at': time.time(),
                'title': result.title,
                'artist': result.artist
            }
            self._save_index()
            
        except (IOError, OSError):
            pass
    
    def _remove_cache_entry(self, cache_key: str):
        """Remove a cache entry."""
        cache_file = self._get_cache_file(cache_key)
        try:
            if cache_file.exists():
                cache_file.unlink()
        except OSError:
            pass
        
        if cache_key in self._index:
            del self._index[cache_key]
            self._save_index()
    
    def clear(self):
        """Clear all cached results."""
        for f in self.cache_path.glob("*.json"):
            try:
                f.unlink()
            except OSError:
                pass
        self._index = {}
        self._save_index()
    
    def list_cached(self) -> Dict[str, Any]:
        """List all cached entries."""
        return self._index.copy()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            'total_cached': len(self._index),
            'cache_dir': str(self.cache_path),
            'entries': [
                {
                    'path': info.get('path'),
                    'title': info.get('title'),
                    'artist': info.get('artist'),
                    'cached_at': info.get('cached_at')
                }
                for info in self._index.values()
            ]
        }


class ShazamClient:
    """Client for Shazam song identification."""
    
    def __init__(self, cache_dir: str = ".shazam_cache"):
        if not SHAZAM_AVAILABLE:
            raise ImportError(
                "shazamio not installed. Install with: pip install shazamio"
            )
        
        self.shazam = Shazam()
        self.cache = ShazamCache(cache_dir)
    
    async def identify(self, audio_path: str, use_cache: bool = True) -> Optional[ShazamResult]:
        """
        Identify a song from audio file.
        
        Args:
            audio_path: Path to audio file
            use_cache: Whether to use caching
        
        Returns:
            ShazamResult or None if not identified
        """
        audio_path = os.path.abspath(audio_path)
        
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        # Check cache first
        if use_cache:
            cached = self.cache.get(audio_path)
            if cached:
                return cached
        
        # Call Shazam API
        result = await self.shazam.recognize(audio_path)
        
        if not result or 'track' not in result:
            return None
        
        track = result['track']
        
        # Extract metadata
        shazam_result = self._parse_track_data(track)
        
        # Cache the result
        if use_cache:
            self.cache.set(audio_path, shazam_result)
        
        return shazam_result
    
    def identify_sync(self, audio_path: str, use_cache: bool = True) -> Optional[ShazamResult]:
        """Synchronous wrapper for identify()."""
        return asyncio.run(self.identify(audio_path, use_cache))
    
    def _parse_track_data(self, track: Dict[str, Any]) -> ShazamResult:
        """Parse Shazam track data into ShazamResult."""
        # Basic info
        title = track.get('title', 'Unknown Title')
        artist = track.get('subtitle', 'Unknown Artist')
        shazam_id = str(track.get('key', ''))
        shazam_url = track.get('url', '')
        
        # Album art
        album_art_url = ''
        images = track.get('images', {})
        if images:
            album_art_url = images.get('coverarthq') or images.get('coverart') or ''
        
        # Extended metadata from sections
        album = ''
        genre = ''
        year = ''
        
        sections = track.get('sections', [])
        for section in sections:
            # Genre
            if 'metadata' in section:
                for meta in section['metadata']:
                    meta_title = meta.get('title', '').lower()
                    if meta_title == 'album':
                        album = meta.get('text', '')
                    elif meta_title == 'released':
                        year = meta.get('text', '')
            
            # Genre from metadata
            if 'genres' in section:
                genre = section['genres'].get('primary', '')
        
        # Alternative genre location
        if not genre:
            genres = track.get('genres', {})
            genre = genres.get('primary', '')
        
        return ShazamResult(
            title=title,
            artist=artist,
            album=album,
            genre=genre,
            year=year,
            shazam_id=shazam_id,
            shazam_url=shazam_url,
            album_art_url=album_art_url,
            identified_at=time.time()
        )
    
    async def identify_batch(
        self, 
        audio_paths: list,
        progress_callback=None,
        use_cache: bool = True
    ) -> Dict[str, Optional[ShazamResult]]:
        """
        Identify multiple songs in batch.
        
        Args:
            audio_paths: List of paths to audio files
            progress_callback: Optional callback(current, total, path)
            use_cache: Whether to use caching
        
        Returns:
            Dict mapping path to ShazamResult or None
        """
        results = {}
        total = len(audio_paths)
        
        for i, path in enumerate(audio_paths, 1):
            if progress_callback:
                progress_callback(i, total, path)
            
            try:
                result = await self.identify(path, use_cache)
                results[path] = result
            except Exception:
                results[path] = None
        
        return results
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return self.cache.get_stats()
    
    def clear_cache(self):
        """Clear identification cache."""
        self.cache.clear()


# Convenience functions for simple use cases

def identify_song(audio_path: str, cache_dir: str = ".shazam_cache") -> Optional[ShazamResult]:
    """
    Quick identify a single song.
    
    Args:
        audio_path: Path to audio file
        cache_dir: Directory for cache
    
    Returns:
        ShazamResult or None
    """
    if not SHAZAM_AVAILABLE:
        raise ImportError("shazamio not installed. Run: pip install shazamio")
    
    client = ShazamClient(cache_dir)
    return client.identify_sync(audio_path)


def get_song_name(audio_path: str, cache_dir: str = ".shazam_cache") -> Optional[str]:
    """
    Get just the song name (Artist - Title) from audio file.
    
    Args:
        audio_path: Path to audio file
        cache_dir: Directory for cache
    
    Returns:
        Formatted song name or None
    """
    result = identify_song(audio_path, cache_dir)
    if result:
        return f"{result.artist} - {result.title}"
    return None


# Check availability
def is_shazam_available() -> bool:
    """Check if ShazamIO is available."""
    return SHAZAM_AVAILABLE
