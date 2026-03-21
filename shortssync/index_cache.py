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
        self.checkpoint_file = self.cache_dir / "reference_index_checkpoint.json"
        self.checkpoint_data_file = self.cache_dir / "reference_index_checkpoint_data.npz"

    def _get_cache_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize the cache-relevant config values."""
        return {
            'detect_slowed': config.get('detect_slowed', False),
            'slowed_speeds': config.get('slowed_speeds', [0.8, 0.7])
        }

    def _serialize_fingerprints(self, ref_fps: Dict[str, np.ndarray]) -> Tuple[Dict[str, str], Dict[str, np.ndarray]]:
        """Convert fingerprint labels into stable NPZ keys."""
        sanitized_names = {}
        npz_data = {}

        for index, (name, fingerprint) in enumerate(ref_fps.items()):
            safe_key = f"fp_{index}"
            sanitized_names[safe_key] = name
            npz_data[safe_key] = fingerprint

        return sanitized_names, npz_data

    def _load_npz_index(
        self,
        metadata_path: Path,
        data_path: Path
    ) -> Optional[Tuple[Dict[str, np.ndarray], Dict[str, str], Dict[str, Any]]]:
        """Load cache metadata and fingerprint arrays from disk."""
        try:
            with open(metadata_path, 'r') as handle:
                cache_info = json.load(handle)

            npz_data = np.load(data_path, allow_pickle=False)

            ref_fps = {}
            name_map = cache_info.get('names', {})
            for key in npz_data.files:
                original_name = name_map.get(key, key)
                ref_fps[original_name] = npz_data[key]

            shazam_names = cache_info.get('shazam_names', {})
            return ref_fps, shazam_names, cache_info

        except (IOError, KeyError, ValueError, json.JSONDecodeError) as exc:
            print(f"  ⚠️  Cache load failed: {exc}")
            return None
    
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
        loaded = self._load_npz_index(self.index_file, self.data_file)
        if not loaded:
            return None

        ref_fps, shazam_names, _ = loaded
        return ref_fps, shazam_names
    
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

            sanitized_names, npz_data = self._serialize_fingerprints(ref_fps)
            
            # Save numpy data
            np.savez_compressed(self.data_file, **npz_data)
            
            # Save metadata
            cache_info = {
                'audio_dir': audio_dir,
                'signature': signature,
                'config': self._get_cache_config(config),
                'names': sanitized_names,
                'shazam_names': shazam_names,
                'count': len(ref_fps)
            }
            
            with open(self.index_file, 'w') as f:
                json.dump(cache_info, f, indent=2)

            self.clear_checkpoint()
            
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

        self.clear_checkpoint()

    def load_checkpoint(
        self,
        audio_dir: str,
        config: Dict[str, Any],
        all_files: List[str]
    ) -> Optional[Tuple[Dict[str, np.ndarray], Dict[str, str], List[str]]]:
        """Load a resumable in-progress index build if it matches the current inputs."""
        if not self.checkpoint_file.exists() or not self.checkpoint_data_file.exists():
            return None

        loaded = self._load_npz_index(self.checkpoint_file, self.checkpoint_data_file)
        if not loaded:
            self.clear_checkpoint()
            return None

        ref_fps, shazam_names, checkpoint_info = loaded
        same_dir = checkpoint_info.get('audio_dir') == audio_dir
        same_config = checkpoint_info.get('config') == self._get_cache_config(config)
        same_files = checkpoint_info.get('all_files') == all_files

        if not (same_dir and same_config and same_files):
            self.clear_checkpoint()
            return None

        completed_files = checkpoint_info.get('completed_files', [])
        return ref_fps, shazam_names, completed_files

    def save_checkpoint(
        self,
        audio_dir: str,
        ref_fps: Dict[str, np.ndarray],
        shazam_names: Dict[str, str],
        config: Dict[str, Any],
        all_files: List[str],
        completed_files: List[str]
    ) -> bool:
        """Persist partial indexing progress so an interrupted run can resume."""
        try:
            sanitized_names, npz_data = self._serialize_fingerprints(ref_fps)
            np.savez_compressed(self.checkpoint_data_file, **npz_data)

            checkpoint_info = {
                'audio_dir': audio_dir,
                'config': self._get_cache_config(config),
                'names': sanitized_names,
                'shazam_names': shazam_names,
                'all_files': all_files,
                'completed_files': completed_files,
                'count': len(ref_fps)
            }

            with open(self.checkpoint_file, 'w') as handle:
                json.dump(checkpoint_info, handle, indent=2)

            return True

        except (IOError, ValueError) as exc:
            print(f"  ⚠️  Checkpoint save failed: {exc}")
            return False

    def clear_checkpoint(self):
        """Remove any saved resume checkpoint."""
        try:
            if self.checkpoint_file.exists():
                self.checkpoint_file.unlink()
            if self.checkpoint_data_file.exists():
                self.checkpoint_data_file.unlink()
        except OSError:
            pass
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        stats = {
            'exists': self.index_file.exists() and self.data_file.exists(),
            'index_file': str(self.index_file),
            'data_file': str(self.data_file),
            'checkpoint_exists': self.checkpoint_file.exists() and self.checkpoint_data_file.exists(),
            'checkpoint_file': str(self.checkpoint_file),
            'checkpoint_data_file': str(self.checkpoint_data_file)
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

        if stats['checkpoint_exists']:
            try:
                with open(self.checkpoint_file, 'r') as handle:
                    checkpoint_info = json.load(handle)
                stats['checkpoint_completed'] = len(checkpoint_info.get('completed_files', []))
                stats['checkpoint_total_files'] = len(checkpoint_info.get('all_files', []))
            except (json.JSONDecodeError, IOError):
                pass
        
        return stats
