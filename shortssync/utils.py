"""
Utility functions and context managers for safe video/audio handling.
"""

import os
import shutil
from pathlib import Path
from typing import Optional, Generator
from contextlib import contextmanager

# Try to import moviepy
try:
    from moviepy import VideoFileClip
    MOVIEPY_AVAILABLE = True
except ImportError:
    try:
        from moviepy.editor import VideoFileClip
        MOVIEPY_AVAILABLE = True
    except ImportError:
        MOVIEPY_AVAILABLE = False


def get_fpcalc_path() -> Optional[str]:
    """Find fpcalc executable in common locations."""
    fpcalc = shutil.which("fpcalc")
    
    # Common macOS locations
    if not fpcalc:
        common_paths = [
            "/opt/homebrew/bin/fpcalc",  # Apple Silicon Homebrew
            "/usr/local/bin/fpcalc",      # Intel Homebrew
            "/usr/bin/fpcalc",            # System
        ]
        for path in common_paths:
            if os.path.exists(path):
                fpcalc = path
                break
    
    return fpcalc


class VideoAudioExtractor:
    """
    Context manager for safe video audio extraction.
    Ensures VideoFileClip is always closed and temp files cleaned up.
    """
    
    def __init__(self, video_path: str, temp_audio_path: Optional[str] = None):
        self.video_path = video_path
        self.temp_audio_path = temp_audio_path
        self.video_clip = None
        self._audio_extracted = False
        self._extraction_path = None
    
    def __enter__(self):
        if not MOVIEPY_AVAILABLE:
            raise ImportError("moviepy not installed")
        
        self.video_clip = VideoFileClip(self.video_path)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Ensure video clip is closed and temp files are cleaned up."""
        # Close video clip
        if self.video_clip is not None:
            try:
                self.video_clip.close()
            except Exception:
                pass
            self.video_clip = None
        
        # Clean up temp audio file
        if self._extraction_path and os.path.exists(self._extraction_path):
            try:
                os.remove(self._extraction_path)
            except OSError:
                pass
        
        # Don't suppress exceptions
        return False
    
    @property
    def has_audio(self) -> bool:
        """Check if video has an audio track."""
        return self.video_clip is not None and self.video_clip.audio is not None
    
    @property
    def duration(self) -> float:
        """Get video duration in seconds."""
        return self.video_clip.duration if self.video_clip else 0.0
    
    def extract_audio(self, output_path: Optional[str] = None, codec: str = 'pcm_s16le') -> str:
        """
        Extract audio to a file.
        
        Args:
            output_path: Path for output audio file (auto-generated if None)
            codec: Audio codec to use
        
        Returns:
            Path to extracted audio file
        """
        if not self.has_audio:
            raise ValueError("Video has no audio track")
        
        if output_path is None:
            if self.temp_audio_path:
                output_path = self.temp_audio_path
            else:
                # Generate temp path in same directory as video
                video_dir = os.path.dirname(self.video_path) or "."
                base_name = f".temp_audio_{os.getpid()}_{id(self)}.wav"
                output_path = os.path.join(video_dir, base_name)
        
        self.video_clip.audio.write_audiofile(
            output_path,
            logger=None,
            codec=codec,
            verbose=False
        )
        
        self._extraction_path = output_path
        self._audio_extracted = True
        
        return output_path
    
    def get_audio_array(self):
        """Get audio as numpy array."""
        if not self.has_audio:
            raise ValueError("Video has no audio track")
        return self.video_clip.audio.to_soundarray()


@contextmanager
def extract_audio_safe(
    video_path: str,
    output_path: Optional[str] = None,
    codec: str = 'pcm_s16le'
) -> Generator[Optional[str], None, None]:
    """
    Context manager for safe audio extraction.
    
    Automatically closes video clip and cleans up temp files on exit.
    
    Args:
        video_path: Path to video file
        output_path: Path for output audio (auto-generated if None)
        codec: Audio codec
    
    Yields:
        Path to extracted audio file, or None if no audio/extraction failed
    
    Example:
        with extract_audio_safe('video.mp4') as audio_path:
            if audio_path:
                fingerprint = get_fingerprint(audio_path)
    """
    if not MOVIEPY_AVAILABLE:
        raise ImportError("moviepy not installed")
    
    video_clip = None
    actual_output_path = output_path
    
    try:
        video_clip = VideoFileClip(video_path)
        
        if not video_clip.audio:
            yield None
            return
        
        if actual_output_path is None:
            video_dir = os.path.dirname(video_path) or "."
            base_name = f".temp_audio_{os.getpid()}_{hash(video_path) & 0xFFFFFFFF}.wav"
            actual_output_path = os.path.join(video_dir, base_name)
        
        video_clip.audio.write_audiofile(
            actual_output_path,
            logger=None,
            codec=codec,
            verbose=False
        )
        
        yield actual_output_path
        
    except Exception:
        yield None
    
    finally:
        # Always clean up
        if video_clip is not None:
            try:
                video_clip.close()
            except Exception:
                pass
        
        if actual_output_path and os.path.exists(actual_output_path):
            try:
                os.remove(actual_output_path)
            except OSError:
                pass


@contextmanager
def temp_audio_file(suffix: str = ".wav") -> Generator[str, None, None]:
    """
    Context manager for temporary audio file.
    
    Yields:
        Path to temp file
    """
    import tempfile
    
    fd, temp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    
    try:
        yield temp_path
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass


def get_video_duration(video_path: str) -> Optional[float]:
    """Get video duration without loading full video."""
    if not MOVIEPY_AVAILABLE:
        return None
    
    clip = None
    try:
        clip = VideoFileClip(video_path)
        duration = clip.duration
        return duration
    except Exception:
        return None
    finally:
        if clip is not None:
            try:
                clip.close()
            except Exception:
                pass


def is_valid_video(video_path: str) -> bool:
    """Check if file is a valid video."""
    if not MOVIEPY_AVAILABLE:
        return False
    
    clip = None
    try:
        clip = VideoFileClip(video_path)
        return True
    except Exception:
        return False
    finally:
        if clip is not None:
            try:
                clip.close()
            except Exception:
                pass


def get_video_info(video_path: str) -> dict:
    """Get basic video information."""
    if not MOVIEPY_AVAILABLE:
        return {'error': 'moviepy not installed'}
    
    clip = None
    try:
        clip = VideoFileClip(video_path)
        return {
            'duration': clip.duration,
            'fps': clip.fps,
            'size': clip.size,
            'has_audio': clip.audio is not None,
            'audio_fps': clip.audio.fps if clip.audio else None,
        }
    except Exception as e:
        return {'error': str(e)}
    finally:
        if clip is not None:
            try:
                clip.close()
            except Exception:
                pass
