#!/usr/bin/env python3
"""
ShortsSync Web Backend - Flask API Server
Provides RESTful API and WebSocket support for browser-based access
"""

import os
import sys
import json
import shutil
import subprocess
import threading
import time
import socket
from datetime import datetime
from pathlib import Path
import secrets

import numpy as np
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shortssync import (
    get_fingerprint,
    get_fingerprint_cached,
    generate_name,
    get_fpcalc_path,
    VideoAudioExtractor,
    ShazamClient,
    is_shazam_available,
    ShazamCache
)

try:
    from moviepy import VideoFileClip
except ImportError:
    from moviepy.editor import VideoFileClip

try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False

# Import config with better error handling
try:
    import config
    defaults = config.get_defaults()
except Exception as e:
    print(f"Warning: Could not load config.py: {e}")
    # Create minimal defaults
    class MockConfig:
        @staticmethod
        def get_defaults():
            return {
                'video_dir': '',
                'audio_dir': '',
                'fixed_tags': '#shorts',
                'pool_tags': '#fyp #viral #trending',
                'preserve_exact_names': False,
                'move_files': False,
            }
    config = MockConfig()

# ==================== Configuration ====================
app = Flask(__name__, static_folder='web_frontend', static_url_path='')
app.config['SECRET_KEY'] = secrets.token_hex(32)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max upload
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['FINGERPRINT_CACHE'] = '.fingerprints'

CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Global state
processing_status = {
    'is_processing': False,
    'current_task': None,
    'progress': 0,
    'total': 0,
    'message': ''
}

reference_fingerprints = {}
match_results = []
processing_lock = threading.Lock()

# Check Shazam availability
SHAZAM_AVAILABLE = is_shazam_available()

# ==================== Utility Functions ====================

def emit_status(message, progress=None, total=None):
    """Send status update via WebSocket."""
    global processing_status
    processing_status['message'] = message
    if progress is not None:
        processing_status['progress'] = progress
    if total is not None:
        processing_status['total'] = total

    # Emit to all connected clients
    socketio.emit('status_update', processing_status)
    print(f"[Status] {message}")

def extract_audio_from_video(video_path, output_path):
    """Extract audio track from video file using safe extractor."""
    try:
        with VideoAudioExtractor(video_path, output_path) as extractor:
            if not extractor.has_audio:
                return False
            extractor.extract_audio()
            return True
    except Exception as e:
        print(f"Error extracting audio: {e}")
        return False

# ==================== API Routes ====================

@app.route('/')
def index():
    """Serve main web interface."""
    return send_from_directory('web_frontend', 'index.html')

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    fpcalc = get_fpcalc_path()
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'dependencies': {
            'fpcalc': fpcalc is not None,
            'moviepy': True,
            'numpy': True,
            'shazam': SHAZAM_AVAILABLE,
            'yt_dlp': YT_DLP_AVAILABLE
        }
    })

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration."""
    try:
        defaults = config.get_defaults()
    except Exception:
        defaults = {}
    return jsonify({
        'config': defaults,
        'processing': processing_status
    })

@app.route('/api/config', methods=['POST'])
def update_config():
    """Update configuration (runtime only, not saved to file)."""
    data = request.json
    # In a production app, you'd validate and save this
    return jsonify({'success': True, 'message': 'Configuration updated'})

@app.route('/api/shazam/status', methods=['GET'])
def shazam_status():
    """Get Shazam availability status."""
    return jsonify({
        'available': SHAZAM_AVAILABLE,
        'cache_stats': ShazamCache().get_stats() if SHAZAM_AVAILABLE else None
    })

@app.route('/api/reference/index', methods=['POST'])
def index_reference_audio():
    """Index reference audio files."""
    global reference_fingerprints, processing_status

    if processing_status['is_processing']:
        return jsonify({'error': 'Processing already in progress'}), 409

    data = request.json
    audio_dir = data.get('audio_dir')
    use_shazam = data.get('use_shazam', False) and SHAZAM_AVAILABLE

    # Validate and sanitize path (prevent path traversal)
    audio_dir = os.path.abspath(os.path.normpath(audio_dir))
    if not os.path.exists(audio_dir) or not os.path.isdir(audio_dir):
        return jsonify({'error': 'Invalid audio directory'}), 400

    # Start indexing in background thread
    def index_task():
        global reference_fingerprints, processing_status
        
        # Copy use_shazam to local scope to avoid closure issues
        local_use_shazam = use_shazam

        with processing_lock:
            processing_status['is_processing'] = True
            processing_status['current_task'] = 'indexing'

            try:
                emit_status("Starting reference audio indexing...")

                fpcalc = get_fpcalc_path()
                if not fpcalc:
                    emit_status("Error: fpcalc not found. Install chromaprint.")
                    return

                # Initialize Shazam client if needed
                shazam_client = None
                shazam_names = {}
                if local_use_shazam:
                    try:
                        shazam_client = ShazamClient()
                        emit_status("Shazam client initialized")
                    except Exception as e:
                        emit_status(f"Shazam init failed: {e}")
                        local_use_shazam = False

                ref_fps = {}
                audio_exts = ('.mp3', '.wav', '.m4a', '.flac', '.ogg')
                video_exts = ('.mp4', '.mov', '.mkv')

                # Find all audio and video files recursively
                all_files = []
                for root, dirs, files in os.walk(audio_dir):
                    for f in files:
                        if f.lower().endswith(audio_exts) or f.lower().endswith(video_exts):
                            full_path = os.path.join(root, f)
                            all_files.append((f, full_path))

                total = len(all_files)
                emit_status(f"Found {total} reference files", 0, total)

                for i, (filename, file_path) in enumerate(all_files, 1):
                    emit_status(f"Indexing {filename}...", i, total)

                    # Handle video files (extract audio first)
                    if filename.lower().endswith(video_exts):
                        temp_audio = os.path.join(audio_dir, f".temp_ref_audio_{i}.wav")
                        try:
                            with VideoAudioExtractor(file_path, temp_audio) as extractor:
                                if not extractor.has_audio:
                                    emit_status(f"Skipping {filename} (no audio track)", i, total)
                                    continue
                                
                                extractor.extract_audio()
                                fp = get_fingerprint_cached(temp_audio, fpcalc, app.config['FINGERPRINT_CACHE'])
                                
                                # Try Shazam identification
                                if local_use_shazam and fp is not None:
                                    try:
                                        import asyncio
                                        result = asyncio.run(shazam_client.identify(temp_audio))
                                        if result:
                                            shazam_names[filename] = result.get_filename_base()
                                            emit_status(f"🎵 Shazam: {result.artist} - {result.title}", i, total)
                                    except Exception as e:
                                        print(f"Shazam error for {filename}: {e}")
                        except Exception as e:
                            emit_status(f"Error with {filename}: {str(e)}", i, total)
                            continue
                    else:
                        fp = get_fingerprint_cached(file_path, fpcalc, app.config['FINGERPRINT_CACHE'])
                        
                        # Try Shazam identification for audio files too
                        if local_use_shazam and fp is not None:
                            try:
                                import asyncio
                                result = asyncio.run(shazam_client.identify(file_path))
                                if result:
                                    shazam_names[filename] = result.get_filename_base()
                                    emit_status(f"🎵 Shazam: {result.artist} - {result.title}", i, total)
                            except Exception as e:
                                print(f"Shazam error for {filename}: {e}")

                    if fp is not None and len(fp) > 0:
                        # Use Shazam name if available, otherwise use filename
                        display_name = shazam_names.get(filename, filename)
                        ref_fps[display_name] = np.unpackbits(fp.view(np.uint8))

                reference_fingerprints = ref_fps
                emit_status(f"✅ Indexed {len(ref_fps)} reference tracks", total, total)
                
                if shazam_names:
                    emit_status(f"🎵 Shazam identified {len(shazam_names)} tracks")

            except Exception as e:
                emit_status(f"Error during indexing: {str(e)}")
            finally:
                processing_status['is_processing'] = False
                processing_status['current_task'] = None
                # Send final status update to notify frontend that processing is complete
                socketio.emit('status_update', processing_status)

    thread = threading.Thread(target=index_task)
    thread.daemon = True
    thread.start()

    return jsonify({'success': True, 'message': 'Indexing started'})

@app.route('/api/reference/list', methods=['GET'])
def list_reference_audio():
    """Get list of indexed reference audio."""
    return jsonify({
        'count': len(reference_fingerprints),
        'files': list(reference_fingerprints.keys())
    })

@app.route('/api/videos/match', methods=['POST'])
def match_videos():
    """Match videos against reference audio."""
    global match_results, processing_status, reference_fingerprints

    if processing_status['is_processing']:
        return jsonify({'error': 'Processing already in progress'}), 409

    if not reference_fingerprints:
        return jsonify({'error': 'No reference audio indexed. Index first.'}), 400

    data = request.json
    video_dir = data.get('video_dir')
    audio_dir = data.get('audio_dir', '')
    fixed_tags = data.get('fixed_tags', '#shorts')
    pool_tags = data.get('pool_tags', '#fyp #viral #trending')
    preserve_exact = data.get('preserve_exact_names', False)
    threshold = data.get('threshold', 0.15)
    use_shazam_fallback = data.get('use_shazam_fallback', False) and SHAZAM_AVAILABLE
    save_new_audio = data.get('save_new_audio', False) and audio_dir

    # Validate and sanitize paths
    video_dir = os.path.abspath(os.path.normpath(video_dir))
    if not os.path.exists(video_dir) or not os.path.isdir(video_dir):
        return jsonify({'error': 'Invalid video directory'}), 400
    
    if save_new_audio:
        audio_dir = os.path.abspath(os.path.normpath(audio_dir))
        if not os.path.exists(audio_dir):
            return jsonify({'error': 'Invalid audio directory for saving'}), 400

    # Start matching in background thread
    def match_task():
        global match_results, processing_status
        
        local_use_shazam = use_shazam_fallback

        with processing_lock:
            processing_status['is_processing'] = True
            processing_status['current_task'] = 'matching'
            match_results = []

            try:
                emit_status("Starting video matching...")

                fpcalc = get_fpcalc_path()
                if not fpcalc:
                    emit_status("Error: fpcalc not found")
                    return
                
                # Initialize Shazam client if fallback is enabled
                shazam_client = None
                if local_use_shazam:
                    try:
                        shazam_client = ShazamClient()
                        emit_status("Shazam fallback enabled for unmatched videos")
                    except Exception as e:
                        emit_status(f"Shazam init failed: {e}")
                        local_use_shazam = False

                # Find all video files (non-recursive for video dir)
                vid_files = [f for f in os.listdir(video_dir)
                           if f.lower().endswith(('.mp4', '.mov', '.mkv'))]

                total = len(vid_files)
                emit_status(f"Found {total} video files", 0, total)

                matches = []
                proposed_names = set()
                shazam_matches = 0

                for i, f in enumerate(vid_files, 1):
                    emit_status(f"Matching {f}...", i, total)

                    full_path = os.path.join(video_dir, f)
                    temp_wav = os.path.join(video_dir, f".temp_extract_{i}.wav")

                    try:
                        # Extract audio from video using safe extractor
                        with VideoAudioExtractor(full_path, temp_wav) as extractor:
                            if not extractor.has_audio:
                                emit_status(f"Skipping {f} (no audio)", i, total)
                                continue

                            extractor.extract_audio()

                            # Get fingerprint
                            q_fp = get_fingerprint(temp_wav, fpcalc)
                            if q_fp is None or len(q_fp) == 0:
                                emit_status(f"Fingerprint error for {f}", i, total)
                                continue

                            q_bits = np.unpackbits(q_fp.view(np.uint8))
                            n_q = len(q_bits)

                            # Find best match using sliding window
                            best_ber = 1.0
                            best_ref = None

                            for ref_name, r_bits in reference_fingerprints.items():
                                n_r = len(r_bits)
                                if n_q > n_r:
                                    continue

                                n_windows = (n_r // 32) - len(q_fp) + 1
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

                            # Check if match is good enough
                            matched = False
                            if best_ref and best_ber < threshold:
                                # Use generate_name which now properly checks both used_names and file existence
                                new_name = generate_name(
                                    ref_name=best_ref,
                                    vid_name=f,
                                    vid_dir=video_dir,
                                    used_names=proposed_names,
                                    fixed_tags=fixed_tags,
                                    pool_tags=pool_tags,
                                    preserve_exact=preserve_exact
                                )
                                proposed_names.add(new_name.lower())

                                match = {
                                    'original': f,
                                    'new_name': new_name,
                                    'matched_ref': best_ref,
                                    'ber': float(best_ber),
                                    'confidence': float(1.0 - best_ber),
                                    'match_type': 'fingerprint'
                                }
                                matches.append(match)
                                emit_status(f"✅ Matched {f} → {best_ref} (BER: {best_ber:.3f})", i, total)
                                matched = True
                            
                            # Try Shazam fallback if no match and Shazam is enabled
                            if not matched and local_use_shazam and shazam_client:
                                try:
                                    import asyncio
                                    emit_status(f"🔍 Trying Shazam for {f}...", i, total)
                                    result = asyncio.run(shazam_client.identify(temp_wav))
                                    
                                    if result:
                                        shazam_name = result.get_filename_base()
                                        # Look for this song in reference library by name
                                        for ref_name in reference_fingerprints.keys():
                                            # Check if Shazam name matches reference (case insensitive, allow partial)
                                            ref_base = os.path.splitext(ref_name)[0].lower()
                                            shazam_lower = shazam_name.lower()
                                            
                                            if shazam_lower in ref_base or ref_base in shazam_lower:
                                                # Found a match via Shazam!
                                                new_name = generate_name(
                                                    ref_name=ref_name,
                                                    vid_name=f,
                                                    vid_dir=video_dir,
                                                    used_names=proposed_names,
                                                    fixed_tags=fixed_tags,
                                                    pool_tags=pool_tags,
                                                    preserve_exact=preserve_exact
                                                )
                                                proposed_names.add(new_name.lower())

                                                match = {
                                                    'original': f,
                                                    'new_name': new_name,
                                                    'matched_ref': ref_name,
                                                    'ber': 0.0,  # Perfect match via Shazam
                                                    'confidence': 1.0,
                                                    'match_type': 'shazam',
                                                    'shazam_artist': result.artist,
                                                    'shazam_title': result.title
                                                }
                                                matches.append(match)
                                                emit_status(f"🎵 Shazam matched {f} → {ref_name}", i, total)
                                                shazam_matches += 1
                                                matched = True
                                                break
                                        
                                        if not matched:
                                            emit_status(f"🎵 Shazam found '{shazam_name}' but not in reference library", i, total)
                                            
                                            # Optionally save audio to reference library
                                            if save_new_audio and audio_dir:
                                                try:
                                                    import shutil
                                                    safe_name = "".join(c for c in shazam_name if c.isalnum() or c in (' ', '-', '_')).strip()
                                                    new_audio_path = os.path.join(audio_dir, f"{safe_name}.mp3")
                                                    
                                                    # Handle duplicates
                                                    counter = 1
                                                    base_path = new_audio_path
                                                    while os.path.exists(new_audio_path):
                                                        new_audio_path = base_path.replace('.mp3', f' ({counter}).mp3')
                                                        counter += 1
                                                    
                                                    # Copy the temp audio file
                                                    shutil.copy2(temp_wav, new_audio_path)
                                                    
                                                    # Add to reference fingerprints immediately
                                                    saved_fp = get_fingerprint_cached(new_audio_path, fpcalc, app.config['FINGERPRINT_CACHE'])
                                                    if saved_fp is not None and len(saved_fp) > 0:
                                                        ref_fps[os.path.basename(new_audio_path)] = np.unpackbits(saved_fp.view(np.uint8))
                                                        reference_fingerprints = ref_fps  # Update global
                                                        emit_status(f"💾 Saved to reference library: {os.path.basename(new_audio_path)}", i, total)
                                                except Exception as e:
                                                    emit_status(f"⚠️  Could not save audio: {e}", i, total)
                                except Exception as e:
                                    emit_status(f"Shazam error for {f}: {e}", i, total)
                            
                            if not matched:
                                emit_status(f"❌ No match for {f} (best BER: {best_ber:.3f})", i, total)

                    except Exception as e:
                        emit_status(f"Error processing {f}: {str(e)}", i, total)
                    # VideoAudioExtractor context manager handles cleanup

                match_results = matches
                if shazam_matches > 0:
                    emit_status(f"✅ Matching complete: {len(matches)} matches ({shazam_matches} via Shazam)", total, total)
                else:
                    emit_status(f"✅ Matching complete: {len(matches)} matches found", total, total)

            except Exception as e:
                emit_status(f"Error during matching: {str(e)}")
            finally:
                processing_status['is_processing'] = False
                processing_status['current_task'] = None
                # Send final status update to notify frontend that processing is complete
                socketio.emit('status_update', processing_status)

    thread = threading.Thread(target=match_task)
    thread.daemon = True
    thread.start()

    return jsonify({'success': True, 'message': 'Matching started'})

@app.route('/api/matches', methods=['GET'])
def get_matches():
    """Get current match results."""
    return jsonify({
        'count': len(match_results),
        'matches': match_results
    })

@app.route('/api/videos/rename', methods=['POST'])
def rename_videos():
    """Commit renames for matched videos."""
    global processing_status

    if processing_status['is_processing']:
        return jsonify({'error': 'Processing already in progress'}), 409

    if not match_results:
        return jsonify({'error': 'No matches to rename'}), 400

    data = request.json
    video_dir = data.get('video_dir')
    move_files = data.get('move_files', False)

    # Validate and sanitize path
    video_dir = os.path.abspath(os.path.normpath(video_dir))
    if not os.path.exists(video_dir) or not os.path.isdir(video_dir):
        return jsonify({'error': 'Invalid video directory'}), 400

    # Start renaming in background thread
    def rename_task():
        global processing_status

        with processing_lock:
            processing_status['is_processing'] = True
            processing_status['current_task'] = 'renaming'

            try:
                total = len(match_results)
                emit_status("Starting rename operation...", 0, total)

                target_dir = os.path.join(video_dir, "_Ready") if move_files else video_dir

                if move_files and not os.path.exists(target_dir):
                    os.makedirs(target_dir)
                    emit_status(f"Created directory: {target_dir}")

                success_count = 0
                errors = []

                for i, match in enumerate(match_results, 1):
                    orig = match['original']
                    new = match['new_name']

                    emit_status(f"Renaming {orig}...", i, total)

                    src = os.path.join(video_dir, orig)
                    dst = os.path.join(target_dir, new)

                    try:
                        os.rename(src, dst)
                        success_count += 1
                        emit_status(f"✅ Renamed {orig} → {new}", i, total)
                    except Exception as e:
                        error_msg = f"Error renaming {orig}: {str(e)}"
                        errors.append(error_msg)
                        emit_status(f"❌ {error_msg}", i, total)

                message = f"✅ Successfully renamed {success_count}/{total} files"
                if errors:
                    message += f" ({len(errors)} errors)"
                emit_status(message, total, total)

            except Exception as e:
                emit_status(f"Error during rename: {str(e)}")
            finally:
                processing_status['is_processing'] = False
                processing_status['current_task'] = None
                # Send final status update to notify frontend that processing is complete
                socketio.emit('status_update', processing_status)

    thread = threading.Thread(target=rename_task)
    thread.daemon = True
    thread.start()

    return jsonify({'success': True, 'message': 'Rename operation started'})

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get current processing status."""
    return jsonify(processing_status)

@app.route('/api/download', methods=['POST'])
def download_video():
    """Download video from URL using yt-dlp."""
    global processing_status

    if not YT_DLP_AVAILABLE:
        return jsonify({'error': 'yt-dlp not installed. Run: pip install yt-dlp'}), 400

    if processing_status['is_processing']:
        return jsonify({'error': 'Processing already in progress'}), 409

    data = request.json
    url = data.get('url')
    output_dir = data.get('output_dir')
    format_type = data.get('format', 'video')  # 'video' or 'audio'

    if not url:
        return jsonify({'error': 'URL is required'}), 400

    if not output_dir:
        output_dir = os.path.join(os.getcwd(), 'downloads')

    # Validate output directory
    output_dir = os.path.abspath(os.path.normpath(output_dir))

    # Start download in background thread
    def download_task():
        global processing_status

        with processing_lock:
            processing_status['is_processing'] = True
            processing_status['current_task'] = 'downloading'

            try:
                os.makedirs(output_dir, exist_ok=True)
                emit_status(f"Starting download from URL...")

                # Configure yt-dlp options
                ydl_opts = {
                    'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
                    'progress_hooks': [lambda d: download_progress_hook(d)],
                    'quiet': True,
                    'no_warnings': True,
                }

                if format_type == 'audio':
                    ydl_opts.update({
                        'format': 'bestaudio/best',
                        'postprocessors': [{
                            'key': 'FFmpegExtractAudio',
                            'preferredcodec': 'mp3',
                            'preferredquality': '192',
                        }],
                    })
                else:
                    # Download best video with height <= 1080p
                    ydl_opts['format'] = 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/best'

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    title = info.get('title', 'Unknown')
                    emit_status(f"Downloading: {title}")

                    ydl.download([url])

                emit_status(f"✅ Download complete: {title}")

            except Exception as e:
                emit_status(f"Error during download: {str(e)}")
            finally:
                processing_status['is_processing'] = False
                processing_status['current_task'] = None
                socketio.emit('status_update', processing_status)

    def download_progress_hook(d):
        """Hook for download progress updates."""
        if d['status'] == 'downloading':
            try:
                downloaded = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                if total > 0:
                    progress = int((downloaded / total) * 100)
                    emit_status(f"Downloading: {progress}%", progress, 100)
            except:
                pass
        elif d['status'] == 'finished':
            emit_status("Download finished, processing...")

    thread = threading.Thread(target=download_task)
    thread.daemon = True
    thread.start()

    return jsonify({'success': True, 'message': 'Download started'})


@app.route('/api/download_mp3', methods=['POST'])
def download_mp3():
    """Download MP3s from URLs to audio_dir with multiline support."""
    global processing_status

    if not YT_DLP_AVAILABLE:
        return jsonify({'error': 'yt-dlp not installed. Run: pip install yt-dlp'}), 400

    if processing_status['is_processing']:
        return jsonify({'error': 'Processing already in progress'}), 409

    data = request.json
    urls_data = data.get('urls', [])  # List of {url, filename} objects
    
    if not urls_data or not isinstance(urls_data, list):
        return jsonify({'error': 'URLs list is required'}), 400

    # Get audio_dir from config
    try:
        settings = config.get_defaults()
        audio_dir = settings.get('audio_dir')
        if not audio_dir:
            return jsonify({'error': 'audio_dir not configured in config.py'}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to load config: {str(e)}'}), 500

    # Validate audio directory
    audio_dir = os.path.abspath(os.path.normpath(audio_dir))

    # Start download in background thread
    def download_task():
        global processing_status

        with processing_lock:
            processing_status['is_processing'] = True
            processing_status['current_task'] = 'downloading_mp3'

            try:
                os.makedirs(audio_dir, exist_ok=True)
                emit_status(f"Starting MP3 download of {len(urls_data)} item(s)...")

                successful = 0
                failed = 0

                for i, item in enumerate(urls_data, 1):
                    url = item.get('url', '').strip()
                    filename = item.get('filename', '').strip() or None
                    
                    if not url:
                        emit_status(f"[{i}/{len(urls_data)}] Skipped: Empty URL")
                        failed += 1
                        continue

                    try:
                        # Update progress
                        processing_status['progress'] = i - 1
                        processing_status['total'] = len(urls_data)
                        socketio.emit('status_update', processing_status)
                        
                        emit_status(f"[{i}/{len(urls_data)}] Downloading: {url[:60]}...")

                        # Configure yt-dlp options
                        ydl_opts = {
                            'format': 'bestaudio/best',
                            'postprocessors': [{
                                'key': 'FFmpegExtractAudio',
                                'preferredcodec': 'mp3',
                                'preferredquality': '192',
                            }],
                            'quiet': True,
                            'no_warnings': True,
                        }

                        if filename:
                            ydl_opts['outtmpl'] = os.path.join(audio_dir, f'{filename}.%(ext)s')
                            emit_status(f"  → Saving as: {filename}.mp3")
                        else:
                            ydl_opts['outtmpl'] = os.path.join(audio_dir, '%(title)s.%(ext)s')

                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(url, download=False)
                            title = info.get('title', 'Unknown')
                            
                            ydl.download([url])

                        emit_status(f"  ✅ Downloaded: {filename or title}")
                        successful += 1

                    except Exception as e:
                        emit_status(f"  ❌ Error: {str(e)}")
                        failed += 1
                
                # Final progress update
                processing_status['progress'] = len(urls_data)
                processing_status['total'] = len(urls_data)
                socketio.emit('status_update', processing_status)

                # Summary
                emit_status(f"✅ MP3 Download Complete!")
                emit_status(f"   Successful: {successful}, Failed: {failed}")
                emit_status(f"   Output: {audio_dir}")

            except Exception as e:
                emit_status(f"Error during MP3 download: {str(e)}")
            finally:
                processing_status['is_processing'] = False
                processing_status['current_task'] = None
                socketio.emit('status_update', processing_status)

    thread = threading.Thread(target=download_task)
    thread.daemon = True
    thread.start()

    return jsonify({'success': True, 'message': 'MP3 download started', 'count': len(urls_data)})


# ==================== WebSocket Events ====================

@socketio.on('connect')
def handle_connect():
    """Handle client connection."""
    emit('status_update', processing_status)
    print(f"Client connected")

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection."""
    print(f"Client disconnected")

# ==================== Utility Functions ====================

def find_available_port(start_port=5001, max_attempts=100):
    """Find an available port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
                return port
        except OSError:
            continue
    # Fallback: let the OS assign a random port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

# ==================== Main ====================

if __name__ == '__main__':
    # Determine environment
    is_production = os.environ.get('FLASK_ENV') == 'production'
    
    # Find available port
    start_port = int(os.environ.get('PORT', 5001))
    port = find_available_port(start_port=start_port)

    print("=" * 60)
    print("ShortsSync Web Backend")
    print("=" * 60)
    print(f"Starting server on http://localhost:{port}")
    print(f"Web UI: http://localhost:{port}")
    print(f"API: http://localhost:{port}/api/*")
    if port != start_port:
        print(f"\n⚠️  Note: Using port {port} (port {start_port} was unavailable)")
    print("=" * 60)

    # Create necessary directories
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['FINGERPRINT_CACHE'], exist_ok=True)

    # Check dependencies
    fpcalc = get_fpcalc_path()
    if not fpcalc:
        print("\n⚠️  Warning: fpcalc not found. Audio fingerprinting will not work.")
        print("Install with: brew install chromaprint (macOS) or apt install libchromaprint-tools (Linux)")
    
    # Check Shazam
    if SHAZAM_AVAILABLE:
        print("✅ Shazam integration available")
    else:
        print("ℹ️  Shazam not available (pip install shazamio to enable)")

    # Start server
    # In production, debug=False and don't allow unsafe werkzeug
    debug_mode = not is_production
    allow_unsafe = not is_production
    
    socketio.run(
        app, 
        host='0.0.0.0', 
        port=port, 
        debug=debug_mode, 
        allow_unsafe_werkzeug=allow_unsafe
    )
