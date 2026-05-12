#!/usr/bin/env python3
"""
ShortsSync Web Backend - Flask API Server
Provides RESTful API and WebSocket support for browser-based access
"""

import os
import sys
import threading
import socket
from datetime import datetime
import secrets

import numpy as np
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shortssync import (
    get_fingerprint_cached,
    generate_name,
    build_reference_label,
    get_fpcalc_path,
    VideoAudioExtractor,
    ShazamClient,
    is_shazam_available,
    ShazamCache
)
from shortssync.web_state import WebStateStore, validate_review_filename

try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False

# Import config with better error handling
try:
    import config
    default_config = config.get_defaults()
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
    default_config = config.get_defaults()


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
processing_lock = threading.Lock()
state_store = WebStateStore(
    os.environ.get('SHORTSSYNC_WEB_STATE', os.path.join('.shortssync', 'web_state.json')),
    default_config,
)

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


def json_object_body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None

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
    return jsonify({
        'config': state_store.get_config(),
        'processing': processing_status
    })

@app.route('/api/config', methods=['POST'])
def update_config():
    """Persist runtime configuration for the web app."""
    data = json_object_body()
    if data is None:
        return jsonify({'error': 'JSON object body is required'}), 400

    updated = state_store.update_config(data)
    return jsonify({
        'success': True,
        'message': 'Configuration updated',
        'config': updated,
    })

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

    data = json_object_body()
    if data is None:
        return jsonify({'error': 'JSON object body is required'}), 400

    audio_dir = data.get('audio_dir')
    use_shazam = data.get('use_shazam', False) and SHAZAM_AVAILABLE

    if not audio_dir:
        return jsonify({'error': 'Audio directory is required'}), 400

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
                used_ref_labels = set()
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
                            rel_path = os.path.relpath(full_path, audio_dir)
                            all_files.append((rel_path, full_path))

                total = len(all_files)
                emit_status(f"Found {total} reference files", 0, total)

                for i, (rel_path, file_path) in enumerate(all_files, 1):
                    filename = os.path.basename(rel_path)
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
                                fp = get_fingerprint_cached(
                                    temp_audio,
                                    fpcalc,
                                    app.config['FINGERPRINT_CACHE'],
                                    cache_key_source=file_path,
                                )
                                
                                # Try Shazam identification
                                if local_use_shazam and fp is not None:
                                    try:
                                        import asyncio
                                        result = asyncio.run(shazam_client.identify(temp_audio))
                                        if result:
                                            shazam_names[rel_path] = result.get_filename_base()
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
                                    shazam_names[rel_path] = result.get_filename_base()
                                    emit_status(f"🎵 Shazam: {result.artist} - {result.title}", i, total)
                            except Exception as e:
                                print(f"Shazam error for {filename}: {e}")

                    if fp is not None and len(fp) > 0:
                        # Use Shazam name if available, otherwise use filename
                        display_name = build_reference_label(
                            rel_path,
                            shazam_names.get(rel_path, filename),
                            used_ref_labels
                        )
                        used_ref_labels.add(display_name.lower())
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
    global processing_status, reference_fingerprints

    if processing_status['is_processing']:
        return jsonify({'error': 'Processing already in progress'}), 409

    if not reference_fingerprints:
        return jsonify({'error': 'No reference audio indexed. Index first.'}), 400

    data = json_object_body()
    if data is None:
        return jsonify({'error': 'JSON object body is required'}), 400

    video_dir = data.get('video_dir')
    audio_dir = data.get('audio_dir', '')
    fixed_tags = data.get('fixed_tags', '#shorts')
    pool_tags = data.get('pool_tags', '#fyp #viral #trending')
    preserve_exact = data.get('preserve_exact_names', False)
    use_shazam_fallback = data.get('use_shazam_fallback', False) and SHAZAM_AVAILABLE
    save_new_audio = data.get('save_new_audio', False) and audio_dir

    if not video_dir:
        return jsonify({'error': 'Video directory is required'}), 400

    try:
        threshold = float(data.get('threshold', 0.15))
    except (TypeError, ValueError):
        return jsonify({'error': 'Threshold must be a number'}), 400

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
        global processing_status, reference_fingerprints
        
        local_use_shazam = use_shazam_fallback

        with processing_lock:
            processing_status['is_processing'] = True
            processing_status['current_task'] = 'matching'

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
                            q_fp = get_fingerprint_cached(
                                temp_wav,
                                fpcalc,
                                app.config['FINGERPRINT_CACHE'],
                                cache_key_source=full_path,
                            )
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
                                                        saved_name = os.path.basename(new_audio_path)
                                                        reference_fingerprints[saved_name] = np.unpackbits(saved_fp.view(np.uint8))
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

                state_store.set_review_batch(video_dir, matches)
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
    """Get current staged match results."""
    review_batch = state_store.get_review_batch()
    if review_batch is None:
        return jsonify({
            'count': 0,
            'matches': [],
            'summary': {'pending': 0, 'approved': 0, 'skipped': 0, 'total': 0},
            'batch': None,
        })

    return jsonify({
        'count': len(review_batch['matches']),
        'matches': review_batch['matches'],
        'summary': review_batch['summary'],
        'batch': {
            'id': review_batch.get('id'),
            'video_dir': review_batch.get('video_dir'),
            'created_at': review_batch.get('created_at'),
        },
    })


@app.route('/api/matches', methods=['DELETE'])
def clear_matches():
    """Clear the current staged review batch."""
    state_store.clear_review_batch()
    return jsonify({'success': True})


@app.route('/api/matches/approve-all', methods=['POST'])
def approve_all_matches():
    """Approve all staged matches except explicitly skipped ones."""
    batch = state_store.approve_all()
    if batch is None:
        return jsonify({'error': 'No matches to approve'}), 404

    return jsonify({
        'success': True,
        'matches': batch['matches'],
        'summary': batch['summary'],
    })


@app.route('/api/matches/<match_id>', methods=['PATCH'])
def update_match_review(match_id):
    """Update the staged review decision for a match."""
    data = request.get_json(silent=True)
    if data is None:
        data = {}
    elif not isinstance(data, dict):
        return jsonify({'error': 'JSON object body is required'}), 400

    try:
        updated = state_store.update_match(
            match_id,
            decision=data.get('decision'),
            new_name=data.get('new_name'),
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    if updated is None:
        return jsonify({'error': 'Match not found'}), 404

    batch = state_store.get_review_batch()
    return jsonify({
        'success': True,
        'match': updated,
        'summary': batch['summary'] if batch else {'pending': 0, 'approved': 0, 'skipped': 0, 'total': 0},
    })

@app.route('/api/videos/rename', methods=['POST'])
def rename_videos():
    """Commit renames for matched videos."""
    global processing_status

    if processing_status['is_processing']:
        return jsonify({'error': 'Processing already in progress'}), 409

    batch = state_store.get_review_batch()
    if not batch:
        return jsonify({'error': 'No approved matches to rename'}), 400

    approved_matches = [
        match for match in batch['matches']
        if match.get('decision') == 'approved'
    ]
    if not approved_matches:
        return jsonify({'error': 'No approved matches to rename'}), 400

    data = request.get_json(silent=True)
    if data is None:
        data = {}
    elif not isinstance(data, dict):
        return jsonify({'error': 'JSON object body is required'}), 400

    batch_video_dir = batch.get('video_dir')
    if not batch_video_dir:
        return jsonify({'error': 'Review batch is missing its video directory'}), 400

    video_dir = os.path.abspath(os.path.normpath(batch_video_dir))
    requested_video_dir = data.get('video_dir')
    if requested_video_dir:
        requested_video_dir = os.path.abspath(os.path.normpath(requested_video_dir))
        if requested_video_dir != video_dir:
            return jsonify({'error': 'Staged review batch belongs to a different video directory'}), 409

    move_files = data.get('move_files', False)
    if not isinstance(move_files, bool):
        return jsonify({'error': 'move_files must be a boolean'}), 400

    # Validate and sanitize path
    if not os.path.exists(video_dir) or not os.path.isdir(video_dir):
        return jsonify({'error': 'Invalid video directory'}), 400

    # Start renaming in background thread
    def rename_task():
        global processing_status

        with processing_lock:
            processing_status['is_processing'] = True
            processing_status['current_task'] = 'renaming'

            try:
                total = len(approved_matches)
                emit_status("Starting rename operation...", 0, total)

                target_dir = os.path.join(video_dir, "_Ready") if move_files else video_dir

                if move_files and not os.path.exists(target_dir):
                    os.makedirs(target_dir)
                    emit_status(f"Created directory: {target_dir}")

                success_count = 0
                success_ids = []
                errors = []

                for i, match in enumerate(approved_matches, 1):
                    orig = match.get('original')
                    new = match.get('new_name')

                    emit_status(f"Renaming {orig}...", i, total)

                    filename_error = (
                        validate_review_filename(orig, 'Original name')
                        or validate_review_filename(new, 'New name')
                    )
                    if filename_error:
                        error_msg = f"Error renaming {orig}: {filename_error}"
                        errors.append(error_msg)
                        emit_status(f"❌ {error_msg}", i, total)
                        continue

                    target_root = os.path.abspath(target_dir)
                    src = os.path.abspath(os.path.join(video_dir, orig))
                    dst = os.path.abspath(os.path.join(target_root, new))

                    try:
                        if os.path.dirname(src) != video_dir or os.path.dirname(dst) != target_root:
                            raise ValueError('Resolved path is outside the expected directory')
                        if not os.path.exists(src):
                            raise FileNotFoundError(src)
                        if os.path.lexists(dst):
                            try:
                                same_file = os.path.samefile(src, dst)
                            except OSError:
                                same_file = False

                            if same_file:
                                success_count += 1
                                if match.get('id'):
                                    success_ids.append(match['id'])
                                emit_status(f"✅ Already named {orig}", i, total)
                                continue
                            raise FileExistsError(dst)

                        os.rename(src, dst)
                        success_count += 1
                        if match.get('id'):
                            success_ids.append(match['id'])
                        emit_status(f"✅ Renamed {orig} → {new}", i, total)
                    except Exception as e:
                        error_msg = f"Error renaming {orig}: {str(e)}"
                        errors.append(error_msg)
                        emit_status(f"❌ {error_msg}", i, total)

                message = f"✅ Successfully renamed {success_count}/{total} files"
                if errors:
                    message += f" ({len(errors)} errors)"
                emit_status(message, total, total)

                if success_ids:
                    state_store.remove_matches(success_ids)

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

    data = json_object_body()
    if data is None:
        return jsonify({'error': 'JSON object body is required'}), 400

    url = data.get('url')
    output_dir = data.get('output_dir')
    format_type = data.get('format', 'video')

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
                emit_status("Starting download from URL...")

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
            except (TypeError, ValueError, ZeroDivisionError):
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

    data = json_object_body()
    if data is None:
        return jsonify({'error': 'JSON object body is required'}), 400

    urls_data = data.get('urls', [])
    
    if not urls_data or not isinstance(urls_data, list):
        return jsonify({'error': 'URLs list is required'}), 400

    settings = state_store.get_config()
    audio_dir = settings.get('audio_dir')
    if not audio_dir:
        return jsonify({'error': 'audio_dir is not configured'}), 400

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
                emit_status("✅ MP3 Download Complete!")
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
    print("Client connected")

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection."""
    print("Client disconnected")

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
