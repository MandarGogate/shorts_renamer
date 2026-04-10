"""
Audio fingerprinting module using Chromaprint.
Provides caching and robust fingerprint extraction.
"""

import os
import hashlib
import shutil
import subprocess
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Tuple
import json
import time


class FingerprintCache:
    """Thread-safe fingerprint cache with metadata tracking."""
    
    def __init__(self, cache_dir: str = ".fingerprints"):
        self.cache_path = Path(cache_dir)
        self.cache_path.mkdir(exist_ok=True)
        self._metadata_file = self.cache_path / ".cache_metadata.json"
        self._metadata = self._load_metadata()
    
    def _normalize_cache_source(self, file_path: str, cache_key_source: Optional[str] = None) -> str:
        """Normalize the file identity used for cache lookups."""
        source_path = cache_key_source or file_path
        return os.path.abspath(os.fspath(source_path))
    
    def _get_cache_key(self, file_path: str, cache_key_source: Optional[str] = None) -> str:
        """Generate stable cache key using a source file path and modification time."""
        source_path = self._normalize_cache_source(file_path, cache_key_source)
        try:
            stat = os.stat(source_path)
            # Use source path + mtime + size for a deterministic key
            key_data = f"{source_path}:{stat.st_mtime}:{stat.st_size}"
            return hashlib.md5(key_data.encode()).hexdigest()
        except (OSError, IOError):
            # Fallback to path-only hash
            return hashlib.md5(source_path.encode()).hexdigest()
    
    def _load_metadata(self) -> Dict:
        """Load cache metadata."""
        if self._metadata_file.exists():
            try:
                with open(self._metadata_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {}
    
    def _save_metadata(self):
        """Save cache metadata."""
        try:
            with open(self._metadata_file, 'w') as f:
                json.dump(self._metadata, f)
        except IOError:
            pass
    
    def get(self, file_path: str, cache_key_source: Optional[str] = None) -> Optional[np.ndarray]:
        """Get cached fingerprint if valid."""
        source_path = self._normalize_cache_source(file_path, cache_key_source)
        cache_key = self._get_cache_key(file_path, cache_key_source)
        cache_file = self.cache_path / f"{cache_key}.npy"
        
        if not cache_file.exists():
            return None
        
        try:
            # Verify the source file identity hasn't changed
            current_stat = os.stat(source_path)
            cached_info = self._metadata.get(cache_key, {})
            
            if cached_info.get('mtime') == current_stat.st_mtime and \
               cached_info.get('size') == current_stat.st_size:
                return np.load(cache_file, allow_pickle=False)
        except (OSError, IOError, ValueError):
            pass
        
        # Cache invalid or corrupted
        self._remove_cache_entry(cache_key)
        return None
    
    def set(self, file_path: str, fingerprint: np.ndarray, cache_key_source: Optional[str] = None):
        """Cache a fingerprint."""
        source_path = self._normalize_cache_source(file_path, cache_key_source)
        cache_key = self._get_cache_key(file_path, cache_key_source)
        cache_file = self.cache_path / f"{cache_key}.npy"
        
        try:
            np.save(cache_file, fingerprint)
            
            # Update metadata
            stat = os.stat(source_path)
            self._metadata[cache_key] = {
                'mtime': stat.st_mtime,
                'size': stat.st_size,
                'path': source_path,
                'cached_at': time.time()
            }
            self._save_metadata()
        except (IOError, OSError):
            pass  # Caching failed, but fingerprint is still valid
    
    def _remove_cache_entry(self, cache_key: str):
        """Remove a cache entry and its metadata."""
        cache_file = self.cache_path / f"{cache_key}.npy"
        try:
            if cache_file.exists():
                cache_file.unlink()
        except OSError:
            pass
        
        if cache_key in self._metadata:
            del self._metadata[cache_key]
            self._save_metadata()
    
    def clear(self):
        """Clear all cached fingerprints."""
        for f in self.cache_path.glob("*.npy"):
            try:
                f.unlink()
            except OSError:
                pass
        self._metadata = {}
        self._save_metadata()
    
# Global cache instance
_global_cache: Optional[FingerprintCache] = None


def get_cache(cache_dir: str = ".fingerprints") -> FingerprintCache:
    """Get or create global cache instance."""
    global _global_cache
    if _global_cache is None or _global_cache.cache_path != Path(cache_dir):
        _global_cache = FingerprintCache(cache_dir)
    return _global_cache


def get_fpcalc_path() -> Optional[str]:
    """Find fpcalc executable."""
    fpcalc = shutil.which("fpcalc")
    if not fpcalc and os.path.exists("/opt/homebrew/bin/fpcalc"):
        fpcalc = "/opt/homebrew/bin/fpcalc"
    if not fpcalc and os.path.exists("/usr/local/bin/fpcalc"):
        fpcalc = "/usr/local/bin/fpcalc"
    return fpcalc


def get_fingerprint(path: str, fpcalc_path: Optional[str] = None, timeout: int = 30) -> Optional[np.ndarray]:
    """
    Extract Chromaprint fingerprint from audio file.
    
    Args:
        path: Path to audio file
        fpcalc_path: Path to fpcalc executable (auto-detected if None)
        timeout: Maximum time to wait for fpcalc
    
    Returns:
        Numpy array of fingerprint data or None on error
    """
    if fpcalc_path is None:
        fpcalc_path = get_fpcalc_path()
    
    if not fpcalc_path:
        raise RuntimeError("fpcalc not found. Install chromaprint.")
    
    try:
        cmd = [fpcalc_path, "-raw", path]
        res = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            check=True, 
            timeout=timeout
        )
        
        for line in res.stdout.splitlines():
            if line.startswith("FINGERPRINT="):
                raw = line[12:]
                if not raw:
                    return None
                return np.array([int(x) for x in raw.split(',')], dtype=np.uint32)
        
        return None
        
    except subprocess.TimeoutExpired:
        return None
    except subprocess.CalledProcessError:
        return None
    except Exception:
        return None


def get_fingerprint_cached(
    path: str, 
    fpcalc_path: Optional[str] = None,
    cache_dir: str = ".fingerprints",
    use_cache: bool = True,
    cache_key_source: Optional[str] = None
) -> Optional[np.ndarray]:
    """
    Get fingerprint with caching support.
    
    Args:
        path: Path to audio file
        fpcalc_path: Path to fpcalc executable
        cache_dir: Directory for cache files
        use_cache: Whether to use caching
        cache_key_source: Stable source path to cache against, useful for temp extracted audio
    
    Returns:
        Numpy array of fingerprint data or None on error
    """
    if not use_cache:
        return get_fingerprint(path, fpcalc_path)
    
    cache = get_cache(cache_dir)
    
    # Try cache first
    cached = cache.get(path, cache_key_source=cache_key_source)
    if cached is not None:
        return cached
    
    # Generate new fingerprint
    fp = get_fingerprint(path, fpcalc_path)
    
    if fp is not None and len(fp) > 0:
        cache.set(path, fp, cache_key_source=cache_key_source)
    
    return fp


def compare_fingerprints(
    fp1: np.ndarray, 
    fp2: np.ndarray, 
    threshold: float = 0.15
) -> Tuple[bool, float]:
    """
    Compare two fingerprints using Bit Error Rate (BER).
    
    Args:
        fp1: First fingerprint
        fp2: Second fingerprint
        threshold: BER threshold for match (lower = stricter)
    
    Returns:
        Tuple of (is_match, ber_value)
    """
    if fp1 is None or fp2 is None:
        return False, 1.0
    
    bits1 = np.unpackbits(fp1.view(np.uint8))
    bits2 = np.unpackbits(fp2.view(np.uint8))
    
    # Make sure they're the same length (use shorter)
    min_len = min(len(bits1), len(bits2))
    bits1 = bits1[:min_len]
    bits2 = bits2[:min_len]
    
    # Calculate BER
    diff = np.count_nonzero(np.bitwise_xor(bits1, bits2))
    ber = diff / min_len if min_len > 0 else 1.0
    
    return ber < threshold, ber


def create_slowed_audio(input_path: str, output_path: str, speed: float = 0.8) -> bool:
    """
    Create a slowed version of an audio file using ffmpeg.
    
    Args:
        input_path: Path to input audio file
        output_path: Path for output slowed audio
        speed: Speed factor (0.5 = half speed, 0.8 = 80% speed)
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # ffmpeg atempo filter: 0.5 to 2.0 range
        if speed >= 0.5:
            filter_str = f"atempo={speed}"
        else:
            # Chain filters for speeds < 0.5
            filter_str = f"atempo=0.5,atempo={speed/0.5}"
        
        cmd = [
            'ffmpeg',
            '-y',  # Overwrite output
            '-i', input_path,
            '-filter:a', filter_str,
            '-vn',  # No video
            '-ar', '44100',  # Standard sample rate for consistent fingerprints
            '-ac', '2',  # Stereo
            output_path
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        return result.returncode == 0
        
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def get_slowed_fingerprint(
    path: str,
    speed: float = 0.8,
    fpcalc_path: Optional[str] = None,
    temp_dir: Optional[str] = None
) -> Optional[np.ndarray]:
    """
    Get fingerprint of a slowed version of an audio file.
    Creates temporary slowed audio, fingerprints it, then cleans up.
    
    Args:
        path: Path to original audio file
        speed: Speed factor for slowing (0.8 = 80% speed)
        fpcalc_path: Path to fpcalc executable
        temp_dir: Directory for temporary files (default: same as input)
    
    Returns:
        Fingerprint of slowed audio or None on error
    """
    if temp_dir is None:
        temp_dir = os.path.dirname(path) or "."
    
    # Create unique temp filename
    base_name = os.path.splitext(os.path.basename(path))[0]
    temp_path = os.path.join(temp_dir, f"._temp_slowed_{speed}_{base_name}.wav")
    
    try:
        # Create slowed version
        if not create_slowed_audio(path, temp_path, speed):
            return None
        
        # Get fingerprint of slowed version
        fp = get_fingerprint(temp_path, fpcalc_path)
        
        return fp
        
    finally:
        # Clean up temp file
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass


def generate_slowed_fingerprints(
    path: str,
    speeds: list = None,
    fpcalc_path: Optional[str] = None,
    temp_dir: Optional[str] = None
) -> Dict[float, Optional[np.ndarray]]:
    """
    Generate fingerprints for multiple slowed versions of an audio file.
    
    Args:
        path: Path to original audio file
        speeds: List of speed factors (default: [0.8, 0.7])
        fpcalc_path: Path to fpcalc executable
        temp_dir: Directory for temporary files
    
    Returns:
        Dictionary mapping speed factor to fingerprint
    """
    if speeds is None:
        speeds = [0.8, 0.7]
    
    result = {}
    for speed in speeds:
        result[speed] = get_slowed_fingerprint(path, speed, fpcalc_path, temp_dir)
    
    return result
