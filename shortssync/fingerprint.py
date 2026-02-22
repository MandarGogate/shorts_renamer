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
    
    def _get_cache_key(self, file_path: str) -> str:
        """Generate stable cache key using file path and modification time."""
        try:
            stat = os.stat(file_path)
            # Use file path + mtime + size for unique key
            key_data = f"{file_path}:{stat.st_mtime}:{stat.st_size}"
            return hashlib.md5(key_data.encode()).hexdigest()
        except (OSError, IOError):
            # Fallback to path-only hash
            return hashlib.md5(file_path.encode()).hexdigest()
    
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
    
    def get(self, file_path: str) -> Optional[np.ndarray]:
        """Get cached fingerprint if valid."""
        cache_key = self._get_cache_key(file_path)
        cache_file = self.cache_path / f"{cache_key}.npy"
        
        if not cache_file.exists():
            return None
        
        try:
            # Verify file hasn't been modified
            current_stat = os.stat(file_path)
            cached_info = self._metadata.get(cache_key, {})
            
            if cached_info.get('mtime') == current_stat.st_mtime and \
               cached_info.get('size') == current_stat.st_size:
                return np.load(cache_file, allow_pickle=False)
        except (OSError, IOError, ValueError):
            pass
        
        # Cache invalid or corrupted
        self._remove_cache_entry(cache_key)
        return None
    
    def set(self, file_path: str, fingerprint: np.ndarray):
        """Cache a fingerprint."""
        cache_key = self._get_cache_key(file_path)
        cache_file = self.cache_path / f"{cache_key}.npy"
        
        try:
            np.save(cache_file, fingerprint)
            
            # Update metadata
            stat = os.stat(file_path)
            self._metadata[cache_key] = {
                'mtime': stat.st_mtime,
                'size': stat.st_size,
                'path': file_path,
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
    
    def cleanup_old(self, max_age_days: int = 30):
        """Remove cache entries older than specified days."""
        cutoff = time.time() - (max_age_days * 86400)
        to_remove = []
        
        for cache_key, info in self._metadata.items():
            if info.get('cached_at', 0) < cutoff:
                to_remove.append(cache_key)
        
        for cache_key in to_remove:
            self._remove_cache_entry(cache_key)


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
    use_cache: bool = True
) -> Optional[np.ndarray]:
    """
    Get fingerprint with caching support.
    
    Args:
        path: Path to audio file
        fpcalc_path: Path to fpcalc executable
        cache_dir: Directory for cache files
        use_cache: Whether to use caching
    
    Returns:
        Numpy array of fingerprint data or None on error
    """
    if not use_cache:
        return get_fingerprint(path, fpcalc_path)
    
    cache = get_cache(cache_dir)
    
    # Try cache first
    cached = cache.get(path)
    if cached is not None:
        return cached
    
    # Generate new fingerprint
    fp = get_fingerprint(path, fpcalc_path)
    
    if fp is not None and len(fp) > 0:
        cache.set(path, fp)
    
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


def find_best_match(
    query_fp: np.ndarray,
    reference_fps: Dict[str, np.ndarray],
    threshold: float = 0.15
) -> Tuple[Optional[str], float]:
    """
    Find best matching reference fingerprint using sliding window.
    
    Args:
        query_fp: Query fingerprint
        reference_fps: Dictionary of reference fingerprints
        threshold: BER threshold for match
    
    Returns:
        Tuple of (best_match_name, best_ber)
    """
    q_bits = np.unpackbits(query_fp.view(np.uint8))
    n_q = len(q_bits)
    
    best_ber = 1.0
    best_ref = None
    
    for ref_name, r_fp in reference_fps.items():
        r_bits = np.unpackbits(r_fp.view(np.uint8))
        n_r = len(r_bits)
        
        if n_q > n_r:
            continue
        
        n_windows = (n_r // 32) - len(query_fp) + 1
        if n_windows < 1:
            continue
        
        min_dist = float('inf')
        for w in range(n_windows):
            start = w * 32
            end = start + n_q
            sub_r = r_bits[start:end]
            dist = np.count_nonzero(np.bitwise_xor(q_bits, sub_r))
            if dist < min_dist:
                min_dist = dist
                if min_dist == 0:
                    break
        
        ber = min_dist / n_q if n_q > 0 else 1.0
        if ber < best_ber:
            best_ber = ber
            best_ref = ref_name
            if best_ber == 0:
                break
    
    return best_ref, best_ber
