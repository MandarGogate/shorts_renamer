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
from datetime import datetime
from pathlib import Path
import secrets

import numpy as np
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename

try:
    from moviepy import VideoFileClip
except ImportError:
    from moviepy.editor import VideoFileClip

import config

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

# ==================== Utility Functions ====================

def get_fpcalc_path():
    """Find fpcalc executable."""
    fpcalc = shutil.which("fpcalc")
    if not fpcalc and os.path.exists("/opt/homebrew/bin/fpcalc"):
        fpcalc = "/opt/homebrew/bin/fpcalc"
    return fpcalc

def emit_status(message, progress=None, total=None):
    """Send status update via WebSocket."""
    global processing_status
    processing_status['message'] = message
    if progress is not None:
        processing_status['progress'] = progress
    if total is not None:
        processing_status['total'] = total

    socketio.emit('status_update', processing_status, broadcast=True)
    print(f"[Status] {message}")

def get_fingerprint(path, fpcalc_path):
    """Extract Chromaprint fingerprint from audio file."""
    try:
        cmd = [fpcalc_path, "-raw", path]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
        for line in res.stdout.splitlines():
            if line.startswith("FINGERPRINT="):
                raw = line[12:]
                if not raw:
                    return None
                return np.array([int(x) for x in raw.split(',')], dtype=np.uint32)
    except Exception as e:
        print(f"Error getting fingerprint for {path}: {e}")
        return None
    return None

def get_fingerprint_cached(path, fpcalc_path, cache_dir):
    """Get fingerprint with caching support."""
    cache_path = Path(cache_dir)
    cache_path.mkdir(exist_ok=True)

    # Create cache filename from file path hash
    cache_file = cache_path / f"{hash(path)}.npy"
    file_stat = os.stat(path)

    # Check if cached fingerprint exists and is up-to-date
    if cache_file.exists():
        cache_stat = os.stat(cache_file)
        if cache_stat.st_mtime > file_stat.st_mtime:
            try:
                cached_fp = np.load(cache_file, allow_pickle=False)
                return cached_fp
            except Exception:
                pass  # Fall through to re-generate

    # Generate new fingerprint
    fp = get_fingerprint(path, fpcalc_path)
    if fp is not None and len(fp) > 0:
        try:
            np.save(cache_file, fp)
        except Exception:
            pass  # Caching failed, but we still have the fingerprint

    return fp

def generate_name(ref_name, vid_name, used_names, fixed_tags, pool_tags, preserve_exact):
    """Generate unique filename based on reference."""
    import random

    base = os.path.splitext(ref_name)[0]
    ext = os.path.splitext(vid_name)[1]

    if preserve_exact:
        candidate = f"{base}{ext}"
        if candidate.lower() not in used_names:
            return candidate
        for i in range(1, 100):
            c = f"{base}_{i}{ext}"
            if c.lower() not in used_names:
                return c

    pool = pool_tags.split() if pool_tags else []

    # Try 20 random tag combinations
    for _ in range(20):
        tags = random.sample(pool, k=min(2, len(pool))) if pool else []
        tag_str = " ".join(tags)
        full = f"{base} {fixed_tags} {tag_str}".strip()
        candidate = f"{full}{ext}"
        if candidate.lower() not in used_names:
            return candidate

    # Fallback to random number
    return f"{base}_{random.randint(1000,9999)}{ext}"

def extract_audio_from_video(video_path, output_path):
    """Extract audio track from video file."""
    video = VideoFileClip(video_path)
    if not video.audio:
        video.close()
        return False
    video.audio.write_audiofile(output_path, logger=None, codec='pcm_s16le')
    video.close()
    return True

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
            'numpy': True
        }
    })

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration."""
    defaults = config.get_defaults()
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

@app.route('/api/reference/index', methods=['POST'])
def index_reference_audio():
    """Index reference audio files."""
    global reference_fingerprints, processing_status

    if processing_status['is_processing']:
        return jsonify({'error': 'Processing already in progress'}), 409

    data = request.json
    audio_dir = data.get('audio_dir')

    if not audio_dir or not os.path.exists(audio_dir):
        return jsonify({'error': 'Invalid audio directory'}), 400

    # Start indexing in background thread
    def index_task():
        global reference_fingerprints, processing_status

        with processing_lock:
            processing_status['is_processing'] = True
            processing_status['current_task'] = 'indexing'

            try:
                emit_status("Starting reference audio indexing...")

                fpcalc = get_fpcalc_path()
                if not fpcalc:
                    emit_status("Error: fpcalc not found. Install chromaprint.")
                    return

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
                        temp_audio = os.path.join(audio_dir, ".temp_ref_audio.wav")
                        try:
                            if not extract_audio_from_video(file_path, temp_audio):
                                emit_status(f"Skipping {filename} (no audio track)", i, total)
                                continue
                            fp = get_fingerprint_cached(temp_audio, fpcalc, app.config['FINGERPRINT_CACHE'])
                            if os.path.exists(temp_audio):
                                os.remove(temp_audio)
                        except Exception as e:
                            emit_status(f"Error with {filename}: {str(e)}", i, total)
                            continue
                    else:
                        fp = get_fingerprint_cached(file_path, fpcalc, app.config['FINGERPRINT_CACHE'])

                    if fp is not None and len(fp) > 0:
                        ref_fps[filename] = np.unpackbits(fp.view(np.uint8))

                reference_fingerprints = ref_fps
                emit_status(f"✅ Indexed {len(ref_fps)} reference tracks", total, total)

            except Exception as e:
                emit_status(f"Error during indexing: {str(e)}")
            finally:
                processing_status['is_processing'] = False
                processing_status['current_task'] = None

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
    global match_results, processing_status

    if processing_status['is_processing']:
        return jsonify({'error': 'Processing already in progress'}), 409

    if not reference_fingerprints:
        return jsonify({'error': 'No reference audio indexed. Index first.'}), 400

    data = request.json
    video_dir = data.get('video_dir')
    fixed_tags = data.get('fixed_tags', '#shorts')
    pool_tags = data.get('pool_tags', '#fyp #viral #trending')
    preserve_exact = data.get('preserve_exact_names', False)
    threshold = data.get('threshold', 0.15)

    if not video_dir or not os.path.exists(video_dir):
        return jsonify({'error': 'Invalid video directory'}), 400

    # Start matching in background thread
    def match_task():
        global match_results, processing_status

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

                # Find all video files (non-recursive for video dir)
                vid_files = [f for f in os.listdir(video_dir)
                           if f.lower().endswith(('.mp4', '.mov', '.mkv'))]

                total = len(vid_files)
                emit_status(f"Found {total} video files", 0, total)

                matches = []
                proposed_names = set()

                for i, f in enumerate(vid_files, 1):
                    emit_status(f"Matching {f}...", i, total)

                    full_path = os.path.join(video_dir, f)
                    temp_wav = os.path.join(video_dir, f".temp_extract_{i}.wav")

                    try:
                        # Extract audio from video
                        if not extract_audio_from_video(full_path, temp_wav):
                            emit_status(f"Skipping {f} (no audio)", i, total)
                            continue

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

                            ber = min_dist / n_q
                            if ber < best_ber:
                                best_ber = ber
                                best_ref = ref_name
                                if best_ber == 0:
                                    break

                        # Check if match is good enough
                        if best_ref and best_ber < threshold:
                            new_name = generate_name(best_ref, f, proposed_names,
                                                    fixed_tags, pool_tags, preserve_exact)
                            proposed_names.add(new_name.lower())

                            match = {
                                'original': f,
                                'new_name': new_name,
                                'matched_ref': best_ref,
                                'ber': float(best_ber),
                                'confidence': float(1.0 - best_ber)
                            }
                            matches.append(match)
                            emit_status(f"✅ Matched {f} → {best_ref} (BER: {best_ber:.3f})", i, total)
                        else:
                            emit_status(f"❌ No match for {f} (best BER: {best_ber:.3f})", i, total)

                    except Exception as e:
                        emit_status(f"Error processing {f}: {str(e)}", i, total)
                    finally:
                        if os.path.exists(temp_wav):
                            try:
                                os.remove(temp_wav)
                            except:
                                pass

                match_results = matches
                emit_status(f"✅ Matching complete: {len(matches)} matches found", total, total)

            except Exception as e:
                emit_status(f"Error during matching: {str(e)}")
            finally:
                processing_status['is_processing'] = False
                processing_status['current_task'] = None

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

    if not video_dir or not os.path.exists(video_dir):
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

    thread = threading.Thread(target=rename_task)
    thread.daemon = True
    thread.start()

    return jsonify({'success': True, 'message': 'Rename operation started'})

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get current processing status."""
    return jsonify(processing_status)

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

# ==================== Main ====================

if __name__ == '__main__':
    print("=" * 60)
    print("ShortsSync Web Backend")
    print("=" * 60)
    print(f"Starting server on http://localhost:5000")
    print(f"Web UI: http://localhost:5000")
    print(f"API: http://localhost:5000/api/*")
    print("=" * 60)

    # Create necessary directories
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['FINGERPRINT_CACHE'], exist_ok=True)

    # Check dependencies
    fpcalc = get_fpcalc_path()
    if not fpcalc:
        print("\n⚠️  Warning: fpcalc not found. Audio fingerprinting will not work.")
        print("Install with: brew install chromaprint (macOS) or apt install libchromaprint-tools (Linux)")

    # Start server
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
