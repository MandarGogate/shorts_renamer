"""
Rename logging module - tracks all file renames with metadata.
Uses JSON Lines format for easy appending and parsing.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List


class RenameLogger:
    """Logger for tracking file renames with metadata."""
    
    def __init__(self, log_file: str = "rename_history.jsonl"):
        self.log_path = Path(log_file)
        self._ensure_dir()
    
    def _ensure_dir(self):
        """Ensure log directory exists."""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
    
    def log_rename(
        self,
        original_name: str,
        new_name: str,
        video_dir: str,
        match_method: str = "chromaprint",  # chromaprint, shazam, slowed, manual
        reference_name: Optional[str] = None,
        ber_score: Optional[float] = None,
        shazam_name: Optional[str] = None,
        is_slowed: bool = False,
        slowed_speed: Optional[float] = None,
        tags_added: Optional[str] = None
    ) -> bool:
        """
        Log a file rename operation.
        
        Args:
            original_name: Original filename
            new_name: New filename after rename
            video_dir: Directory where video was processed
            match_method: How the match was found (chromaprint, shazam, slowed, manual)
            reference_name: Name of the reference audio file that matched
            ber_score: Bit Error Rate score (if chromaprint match)
            shazam_name: Shazam-identified song name (if Shazam match)
            is_slowed: Whether this was identified as a slowed version
            slowed_speed: Speed factor if slowed (e.g., 0.8)
            tags_added: Tags that were added to the filename
        
        Returns:
            True if logged successfully
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "original_name": original_name,
            "new_name": new_name,
            "video_dir": video_dir,
            "match_method": match_method,
            "reference_name": reference_name,
            "ber_score": ber_score,
            "shazam_name": shazam_name,
            "is_slowed": is_slowed,
            "slowed_speed": slowed_speed,
            "tags_added": tags_added
        }
        
        # Remove None values for cleaner output
        entry = {k: v for k, v in entry.items() if v is not None}
        
        try:
            with open(self.log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            return True
        except (IOError, OSError) as e:
            print(f"⚠️  Failed to log rename: {e}")
            return False
    
    def get_history(
        self,
        limit: Optional[int] = None,
        match_method: Optional[str] = None,
        since: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get rename history with optional filtering.
        
        Args:
            limit: Maximum number of entries to return (most recent first)
            match_method: Filter by match method
            since: ISO timestamp to get entries since
        
        Returns:
            List of rename log entries
        """
        if not self.log_path.exists():
            return []
        
        entries = []
        try:
            with open(self.log_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        
                        # Apply filters
                        if match_method and entry.get('match_method') != match_method:
                            continue
                        if since and entry.get('timestamp', '') < since:
                            continue
                        
                        entries.append(entry)
                    except json.JSONDecodeError:
                        continue
        except (IOError, OSError):
            return []
        
        # Sort by timestamp (newest first)
        entries.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        if limit:
            entries = entries[:limit]
        
        return entries
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about rename history."""
        history = self.get_history()
        
        if not history:
            return {
                "total_renames": 0,
                "by_method": {},
                "slowed_count": 0,
                "log_file": str(self.log_path),
                "newest_entry": None,
                "oldest_entry": None
            }
        
        by_method = {}
        slowed_count = 0
        
        for entry in history:
            method = entry.get('match_method', 'unknown')
            by_method[method] = by_method.get(method, 0) + 1
            
            if entry.get('is_slowed'):
                slowed_count += 1
        
        return {
            "total_renames": len(history),
            "by_method": by_method,
            "slowed_count": slowed_count,
            "log_file": str(self.log_path),
            "newest_entry": history[0].get('timestamp') if history else None,
            "oldest_entry": history[-1].get('timestamp') if history else None
        }
    
    def search(self, query: str) -> List[Dict[str, Any]]:
        """
        Search rename history by filename or reference name.
        
        Args:
            query: Search string (case-insensitive)
        
        Returns:
            List of matching entries
        """
        query_lower = query.lower()
        history = self.get_history()
        
        results = []
        for entry in history:
            searchable = ' '.join([
                entry.get('original_name', ''),
                entry.get('new_name', ''),
                entry.get('reference_name', ''),
                entry.get('shazam_name', '')
            ]).lower()
            
            if query_lower in searchable:
                results.append(entry)
        
        return results
    
    def clear_history(self) -> bool:
        """Clear all rename history. Use with caution!"""
        try:
            if self.log_path.exists():
                self.log_path.unlink()
            return True
        except (IOError, OSError) as e:
            print(f"⚠️  Failed to clear history: {e}")
            return False


# Convenience function for quick logging
def log_rename(
    original_name: str,
    new_name: str,
    video_dir: str,
    log_file: str = "rename_history.jsonl",
    **kwargs
) -> bool:
    """Quick function to log a rename without creating a logger instance."""
    logger = RenameLogger(log_file)
    return logger.log_rename(original_name, new_name, video_dir, **kwargs)
