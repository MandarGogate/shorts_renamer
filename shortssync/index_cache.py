"""
Reference index caching - avoid re-indexing audio files that haven't changed.
"""

import json
import os
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import numpy as np


class ReferenceIndexCache:
    """Cache for reference audio index to avoid re-indexing unchanged files."""
    
    def __init__(self, cache_dir: str = ".fingerprints"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.index_file = self.cache_dir / "reference_index.json"
        self.data_file = self.cache_dir / "reference_index_data.npz"
    
    def _get_file_signature(self, file_path: str) -> str:
        """Generate a signature for a file based on path, size, and mtime."""
        try:
            stat = os.stat(file_path)
            sig_data = f"{file_path}:{stat.st_size}:{stat.st_mtime}"
            return hashlib.md5(sig_data.encode()).hexdigest()
        except (OSError, IOError):
            return hashlib.md5(file_path.encode()).hexdigest()
    
    def _get_audio_dir_signature(self, audio_dir: str, audio_exts: tuple, video_exts: tuple) -> str:
        """Generate a signature for the entire audio directory."""
        all_sigs = []
        
        for root, dirs, files in os.walk(audio_dir):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for f in sorted(files):  # Sort for consistent ordering
                # Skip temporary files created during processing
                if f.startswith('._temp_') or f.startswith('.temp_'):
                    continue
                if f.lower().endswith(audio_exts) or f.lower().endswith(video_exts):
                    file_path = os.path.join(root, f)
                    all_sigs.append(self._get_file_signature(file_path))
        
        combined = '|'.join(all_sigs)
        return hashlib.md5(combined.encode()).hexdigest()
    
    def is_cache_valid(self, audio_dir: str, config: Dict[str, Any]) -> bool:
        """
        Check if cached index is still valid.
        
        Args:
            audio_dir: Path to audio reference directory
            config: Configuration dict (detect_slowed, slowed_speeds, etc.)
        
        Returns:
            True if cache is valid and can be used
        """
        if not self.index_file.exists() or not self.data_file.exists():
            return False
        
        try:
            with open(self.index_file, 'r') as f:
                cache_info = json.load(f)
            
            # Check if audio directory changed
            cached_dir = cache_info.get('audio_dir', '')
            if cached_dir != audio_dir:
                return False
            
            # Check if config changed (affects slowed generation)
            cached_config = cache_info.get('config', {})
            if cached_config.get('detect_slowed') != config.get('detect_slowed'):
                return False
            if cached_config.get('slowed_speeds') != config.get('slowed_speeds'):
                return False
            
            # Check if any files changed
            audio_exts = ('.mp3', '.wav', '.m4a', '.flac', '.ogg')
            video_exts = ('.mp4', '.mov', '.mkv')
            current_sig = self._get_audio_dir_signature(audio_dir, audio_exts, video_exts)
            
            if current_sig != cache_info.get('signature'):
                return False
            
            return True
            
        except (json.JSONDecodeError, IOError, KeyError):
            return False
    
    def load_index(self) -> Optional[Tuple[Dict[str, np.ndarray], Dict[str, str]]]:
        """
        Load cached reference index.
        
        Returns:
            Tuple of (ref_fps dict, shazam_names dict) or None if failed
        """
        try:
            with open(self.index_file, 'r') as f:
                cache_info = json.load(f)
            
            # Load numpy data
            npz_data = np.load(self.data_file, allow_pickle=False)
            
            ref_fps = {}
            for key in npz_data.files:
                # Keys are sanitized to be valid numpy array names
                original_name = cache_info['names'].get(key, key)
                ref_fps[original_name] = npz_data[key]
            
            shazam_names = cache_info.get('shazam_names', {})
            
            return ref_fps, shazam_names
            
        except (IOError, KeyError, ValueError) as e:
            print(f"  ⚠️  Cache load failed: {e}")
            return None
    
    def save_index(
        self,
        audio_dir: str,
        ref_fps: Dict[str, np.ndarray],
        shazam_names: Dict[str, str],
        config: Dict[str, Any]
    ) -> bool:
        """
        Save reference index to cache.
        
        Args:
            audio_dir: Path to audio reference directory
            ref_fps: Dictionary of reference fingerprints
            shazam_names: Dictionary of Shazam-identified names
            config: Configuration dict
        
        Returns:
            True if saved successfully
        """
        try:
            audio_exts = ('.mp3', '.wav', '.m4a', '.flac', '.ogg')
            video_exts = ('.mp4', '.mov', '.mkv')
            signature = self._get_audio_dir_signature(audio_dir, audio_exts, video_exts)
            
            # Sanitize names for numpy compatibility
            sanitized_names = {}
            npz_data = {}
            
            for i, (name, fp) in enumerate(ref_fps.items()):
                # Create safe key
                safe_key = f"fp_{i}"
                sanitized_names[safe_key] = name
                npz_data[safe_key] = fp
            
            # Save numpy data
            np.savez_compressed(self.data_file, **npz_data)
            
            # Save metadata
            cache_info = {
                'audio_dir': audio_dir,
                'signature': signature,
                'config': {
                    'detect_slowed': config.get('detect_slowed', False),
                    'slowed_speeds': config.get('slowed_speeds', [0.8, 0.7])
                },
                'names': sanitized_names,
                'shazam_names': shazam_names,
                'count': len(ref_fps)
            }
            
            with open(self.index_file, 'w') as f:
                json.dump(cache_info, f, indent=2)
            
            return True
            
        except (IOError, ValueError) as e:
            print(f"  ⚠️  Cache save failed: {e}")
            return False
    
    def clear(self):
        """Clear the index cache."""
        try:
            if self.index_file.exists():
                self.index_file.unlink()
            if self.data_file.exists():
                self.data_file.unlink()
        except OSError:
            pass
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        stats = {
            'exists': self.index_file.exists() and self.data_file.exists(),
            'index_file': str(self.index_file),
            'data_file': str(self.data_file)
        }
        
        if stats['exists']:
            try:
                with open(self.index_file, 'r') as f:
                    cache_info = json.load(f)
                stats['audio_dir'] = cache_info.get('audio_dir')
                stats['entry_count'] = cache_info.get('count', 0)
                stats['config'] = cache_info.get('config', {})
            except (json.JSONDecodeError, IOError):
                pass
        
        return stats
