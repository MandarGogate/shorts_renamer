#!/usr/bin/env python3
"""
ShortsSync CLI - Command-line version that runs with default settings from config.py
"""

import os
import sys
import shutil
import subprocess
import numpy as np
import random
import argparse
import asyncio
import re
import tempfile
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shortssync import (
    get_fingerprint_cached,
    generate_slowed_fingerprints,
    generate_name,
    get_fpcalc_path,
    VideoAudioExtractor,
    ShazamClient,
    is_shazam_available,
    RenameLogger,
    ReferenceIndexCache
)

# Import config with better error handling
try:
    import config
    defaults = config.get_defaults()
except Exception as e:
    print(f"Error: Could not load config.py: {e}")
    print("Please ensure config.py exists and is valid.")
    sys.exit(1)


def rename_audio_command(args):
    """Rename audio files based on Shazam identification."""
    # asyncio is imported at module level
    
    if not is_shazam_available():
        print("❌ Error: shazamio not installed. Run: pip install shazamio")
        return
    
    audio_dir = args.audio_dir or defaults.get('audio_dir', '')
    if not audio_dir or not os.path.exists(audio_dir):
        print(f"❌ Error: Audio directory not found: {audio_dir}")
        return
    
    print("=" * 60)
    print("Rename Audio Files with Shazam")
    print("=" * 60)
    print(f"Directory: {audio_dir}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    
    # Find audio files
    audio_exts = ('.mp3', '.wav', '.m4a', '.flac', '.ogg')
    audio_files = [f for f in os.listdir(audio_dir) 
                   if f.lower().endswith(audio_exts)]
    
    if not audio_files:
        print("❌ No audio files found")
        return
    
    print(f"Found {len(audio_files)} file(s)\n")
    
    client = ShazamClient()
    renamed = skipped = failed = 0
    
    for i, filename in enumerate(audio_files, 1):
        file_path = os.path.join(audio_dir, filename)
        print(f"[{i}/{len(audio_files)}] {filename}")
        
        try:
            result = asyncio.run(client.identify(file_path))
            if not result:
                print("  ⚠️  Not identified")
                failed += 1
                continue
            
            # Create new name
            def sanitize(name):
                for c in '<>:\"/\\|?*':
                    name = name.replace(c, '_')
                return name.strip()
            
            new_name = f"{sanitize(result.artist)} - {sanitize(result.title)}"
            _, ext = os.path.splitext(filename)
            new_filename = f"{new_name}{ext}"
            
            if filename == new_filename:
                print("  ✓ Already correct")
                skipped += 1
                continue
            
            new_path = os.path.join(audio_dir, new_filename)
            
            # Handle duplicates
            counter = 1
            while os.path.exists(new_path):
                new_filename = f"{new_name} ({counter}){ext}"
                new_path = os.path.join(audio_dir, new_filename)
                counter += 1
            
            print(f"  → {new_filename}")
            
            if args.dry_run:
                print("  [DRY RUN]")
            else:
                os.rename(file_path, new_path)
                print("  ✅ Renamed")
                renamed += 1
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
            failed += 1
    
    print(f"\n{'='*60}")
    print(f"Renamed: {renamed}, Skipped: {skipped}, Failed: {failed}")


def process_single_video(
    video_path: str,
    video_dir: str,
    ref_fps: dict,
    rename_logger: RenameLogger,
    config: dict
) -> tuple:
    """
    Process a single video file for matching.
    
    Returns:
        Tuple of (success: bool, new_name: str or None, match_info: dict)
    """
    import tempfile
    
    filename = os.path.basename(video_path)
    fpcalc = get_fpcalc_path()
    
    # Config values
    threshold = config.get('threshold', 0.15)
    fixed_tags = config.get('fixed_tags', '#shorts')
    pool_tags = config.get('pool_tags', '#fyp #viral #trending')
    preserve_exact = config.get('preserve_exact_names', False)
    use_shazam_fallback = config.get('use_shazam_fallback', False)
    shazam_fallback_any = config.get('shazam_fallback_any', False)
    shazam_fallback_client = config.get('shazam_fallback_client', None)
    save_new_audio = config.get('save_new_audio', False)
    audio_dir = config.get('audio_dir', '')
    proposed_names = config.get('proposed_names', set())
    
    # Create temp file for audio extraction
    temp_wav = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    temp_wav.close()
    
    try:
        with VideoAudioExtractor(video_path, temp_wav.name) as extractor:
            if not extractor.has_audio:
                return False, None, {'error': 'No audio track'}
            
            extractor.extract_audio()
            
            q_fp = get_fingerprint_cached(temp_wav.name, fpcalc)
            if q_fp is None or len(q_fp) == 0:
                return False, None, {'error': 'Fingerprint error'}
            
            q_bits = np.unpackbits(q_fp.view(np.uint8))
            n_q = len(q_bits)
            
            best_ber = 1.0
            best_ref = None
            
            for ref_name, r_bits in ref_fps.items():
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
            
            if best_ref and best_ber < threshold:
                is_slowed = '[SLOWED' in best_ref
                slowed_speed = None
                if is_slowed:
                    speed_match = re.search(r'\[SLOWED ([\d.]+)x\]', best_ref)
                    if speed_match:
                        slowed_speed = float(speed_match.group(1))
                
                match_info = {
                    'method': 'slowed' if is_slowed else 'chromaprint',
                    'reference': best_ref,
                    'ber': best_ber,
                    'is_slowed': is_slowed,
                    'slowed_speed': slowed_speed
                }
                
                new_name = generate_name(
                    ref_name=best_ref,
                    vid_name=filename,
                    vid_dir=video_dir,
                    used_names=proposed_names,
                    fixed_tags=fixed_tags,
                    pool_tags=pool_tags,
                    preserve_exact=preserve_exact
                )
                
                return True, new_name, match_info
            
            # Try Shazam fallback if no match
            if use_shazam_fallback and shazam_fallback_client:
                try:
                    result = asyncio.run(shazam_fallback_client.identify(temp_wav.name, timeout=30))
                    
                    if result:
                        shazam_name = result.get_filename_base()
                        
                        # Look for match in reference library by name
                        shazam_lower = shazam_name.lower()
                        shazam_parts = shazam_lower.split(' - ', 1)
                        shazam_artist = shazam_parts[0].strip() if len(shazam_parts) > 0 else ""
                        shazam_title = shazam_parts[1].strip() if len(shazam_parts) > 1 else ""
                        
                        def word_match_score(a, b):
                            a_words = set(a.replace('_', ' ').replace('-', ' ').split())
                            b_words = set(b.replace('_', ' ').replace('-', ' ').split())
                            if not a_words or not b_words:
                                return 0
                            return len(a_words & b_words) / max(len(a_words), len(b_words))
                        
                        best_match = None
                        best_score = 0
                        
                        for ref_name in ref_fps.keys():
                            ref_base = os.path.splitext(ref_name)[0].lower()
                            
                            if shazam_lower in ref_base or ref_base in shazam_lower:
                                best_match = ref_name
                                best_score = 100
                                break
                            
                            ref_parts = ref_base.split(' - ', 1)
                            ref_artist = ref_parts[0].strip() if len(ref_parts) > 0 else ""
                            ref_title = ref_parts[1].strip() if len(ref_parts) > 1 else ""
                            
                            artist_score = word_match_score(shazam_artist, ref_artist)
                            title_score = word_match_score(shazam_title, ref_title)
                            score = (artist_score * 0.3 + title_score * 0.7) * 100
                            
                            if score > best_score and score >= 50:
                                best_score = score
                                best_match = ref_name
                        
                        if best_match:
                            new_name = generate_name(
                                ref_name=best_match,
                                vid_name=filename,
                                vid_dir=video_dir,
                                used_names=proposed_names,
                                fixed_tags=fixed_tags,
                                pool_tags=pool_tags,
                                preserve_exact=preserve_exact
                            )
                            match_info = {
                                'method': 'shazam',
                                'reference': best_match,
                                'ber': 0.0,
                                'shazam_name': shazam_name,
                                'similarity_score': best_score
                            }
                            return True, new_name, match_info
                        
                        elif shazam_fallback_any:
                            new_name = generate_name(
                                ref_name=shazam_name,
                                vid_name=filename,
                                vid_dir=video_dir,
                                used_names=proposed_names,
                                fixed_tags=fixed_tags,
                                pool_tags=pool_tags,
                                preserve_exact=preserve_exact
                            )
                            match_info = {
                                'method': 'shazam_new',
                                'reference': shazam_name,
                                'ber': 0.0,
                                'shazam_name': shazam_name
                            }
                            return True, new_name, match_info
                        
                except Exception:
                    pass
            
            return False, None, {'error': f'No match (best BER: {best_ber:.3f})'}
            
    finally:
        try:
            if os.path.exists(temp_wav.name):
                os.remove(temp_wav.name)
        except OSError:
            pass


def monitor_mode(args, defaults):
    """
    Run in continuous monitor mode, watching for new video files.
    """
    import time
    from datetime import datetime
    
    video_dir = args.video_dir if args.video_dir else defaults.get('video_dir', '')
    audio_dir = args.audio_dir if args.audio_dir else defaults.get('audio_dir', '')
    interval = args.monitor_interval
    
    if not video_dir or not os.path.exists(video_dir):
        print(f"❌ Error: Video directory not found: {video_dir}")
        sys.exit(1)
    
    if not audio_dir or not os.path.exists(audio_dir):
        print(f"❌ Error: Audio directory not found: {audio_dir}")
        sys.exit(1)
    
    # Check fpcalc
    fpcalc = get_fpcalc_path()
    if not fpcalc:
        print("\n❌ Error: fpcalc not found.")
        print("Install with: brew install chromaprint")
        sys.exit(1)
    
    # Load config
    threshold = args.threshold
    fixed_tags = defaults.get('fixed_tags', '#shorts')
    pool_tags = defaults.get('pool_tags', '#fyp #viral #trending')
    preserve_exact = defaults.get('preserve_exact_names', False)
    move_files = defaults.get('move_files', False)
    detect_slowed = defaults.get('detect_slowed', False)
    slowed_speeds = defaults.get('slowed_speeds', [0.8, 0.7])
    
    # Shazam settings
    use_shazam_fallback = defaults.get('use_shazam_fallback', False) and is_shazam_available()
    shazam_fallback_any = defaults.get('shazam_fallback_any', False)
    save_new_audio = defaults.get('save_new_audio', False)
    
    print("=" * 60)
    print("🎬 ShortsSync Monitor Mode")
    print("=" * 60)
    print(f"📁 Watching: {video_dir}")
    print(f"⏱️  Interval: {interval}s")
    print(f"🎯 BER Threshold: {threshold}")
    print()
    print("Press Ctrl+C to stop monitoring")
    print("=" * 60)
    
    # Build/load reference index
    print("\n📚 Loading reference index...")
    index_cache = ReferenceIndexCache()
    config_for_cache = {
        'detect_slowed': detect_slowed,
        'slowed_speeds': slowed_speeds
    }
    
    ref_fps = {}
    shazam_names = {}
    audio_exts = ('.mp3', '.wav', '.m4a', '.flac', '.ogg')
    video_exts = ('.mp4', '.mov', '.mkv')
    
    use_cached_index = False
    if not args.reindex:
        try:
            if index_cache.is_cache_valid(audio_dir, config_for_cache):
                print("📦 Using cached reference index")
                cached = index_cache.load_index()
                if cached:
                    ref_fps, shazam_names = cached
                    print(f"✅ Loaded {len(ref_fps)} fingerprints")
                    use_cached_index = True
        except Exception as e:
            print(f"⚠️  Cache check failed: {e}")
    
    if not use_cached_index:
        print("🔄 Building index...")
        # Simple index build (just fingerprints, no Shazam for now)
        all_files = []
        for root, dirs, files in os.walk(audio_dir):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for f in files:
                # Skip temporary files
                if f.startswith('._temp_') or f.startswith('.temp_'):
                    continue
                if f.lower().endswith(audio_exts) or f.lower().endswith(video_exts):
                    rel_path = os.path.relpath(os.path.join(root, f), audio_dir)
                    all_files.append(rel_path)
        
        for i, rel_path in enumerate(all_files, 1):
            file_path = os.path.join(audio_dir, rel_path)
            filename = os.path.basename(rel_path)
            
            if rel_path.lower().endswith(video_exts):
                temp_audio = os.path.join(audio_dir, f".temp_ref_audio_{i}.wav")
                try:
                    with VideoAudioExtractor(file_path, temp_audio) as extractor:
                        if extractor.has_audio:
                            extractor.extract_audio()
                            fp = get_fingerprint_cached(temp_audio, fpcalc)
                            if fp is not None and len(fp) > 0:
                                ref_fps[filename] = np.unpackbits(fp.view(np.uint8))
                except Exception:
                    pass
                finally:
                    try:
                        if os.path.exists(temp_audio):
                            os.remove(temp_audio)
                    except OSError:
                        pass
            else:
                fp = get_fingerprint_cached(file_path, fpcalc)
                if fp is not None and len(fp) > 0:
                    ref_fps[filename] = np.unpackbits(fp.view(np.uint8))
            
            # Generate slowed fingerprints
            if detect_slowed and rel_path.lower().endswith(audio_exts):
                try:
                    slowed_fps = generate_slowed_fingerprints(file_path, slowed_speeds, fpcalc, audio_dir)
                    for speed, slowed_fp in slowed_fps.items():
                        if slowed_fp is not None and len(slowed_fp) > 0:
                            slowed_name = f"{filename} [SLOWED {speed}x]"
                            ref_fps[slowed_name] = np.unpackbits(slowed_fp.view(np.uint8))
                except Exception:
                    pass
        
        if ref_fps:
            index_cache.save_index(audio_dir, ref_fps, shazam_names, config_for_cache)
        print(f"✅ Indexed {len(ref_fps)} tracks")
    
    # Initialize Shazam client if needed
    shazam_fallback_client = None
    if use_shazam_fallback:
        try:
            shazam_fallback_client = ShazamClient()
            print("🎵 Shazam fallback enabled")
        except Exception as e:
            print(f"⚠️  Shazam init failed: {e}")
            use_shazam_fallback = False
    
    # Initialize rename logger
    rename_log_file = defaults.get('rename_log_file', 'rename_history.jsonl')
    rename_logger = RenameLogger(rename_log_file)
    
    # Track processed files by inode (unique file ID) to handle renames
    processed_inodes = set()
    target_dir = os.path.join(video_dir, "_Ready") if move_files else video_dir
    
    def get_file_inode(filepath):
        """Get inode of a file, returns None if file doesn't exist."""
        try:
            return os.stat(filepath).st_ino
        except (OSError, IOError):
            return None
    
    def get_video_files_with_inodes(directory):
        """Get all video files with their inodes."""
        files = {}
        try:
            for f in os.listdir(directory):
                if f.lower().endswith(video_exts):
                    filepath = os.path.join(directory, f)
                    inode = get_file_inode(filepath)
                    if inode:
                        files[inode] = f
        except OSError:
            pass
        return files
    
    print(f"\n👀 Monitoring for new video files...\n")
    
    # Initial scan - track inodes of existing files
    initial_files = get_video_files_with_inodes(video_dir)
    processed_inodes = set(initial_files.keys())
    
    print(f"   Found {len(processed_inodes)} existing files (will be ignored)")
    print()
    
    processed_count = 0
    
    try:
        while True:
            # Scan for current files with inodes
            current_files = get_video_files_with_inodes(video_dir)
            
            # Find new files (inodes not seen before)
            new_inodes = set(current_files.keys()) - processed_inodes
            
            for inode in new_inodes:
                filename = current_files[inode]
                filepath = os.path.join(video_dir, filename)
                
                # Check if file is still being written (wait for stability)
                try:
                    initial_size = os.path.getsize(filepath)
                    time.sleep(1)
                    if os.path.getsize(filepath) != initial_size:
                        # File still being written, skip for now
                        # Don't mark as processed yet
                        continue
                except OSError:
                    continue
                
                # File is stable, now mark inode as processed
                processed_inodes.add(inode)
                
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"[{timestamp}] 📥 New file detected: {filename}")
                
                # Process the file
                config = {
                    'threshold': threshold,
                    'fixed_tags': fixed_tags,
                    'pool_tags': pool_tags,
                    'preserve_exact_names': preserve_exact,
                    'use_shazam_fallback': use_shazam_fallback,
                    'shazam_fallback_any': shazam_fallback_any,
                    'shazam_fallback_client': shazam_fallback_client,
                    'save_new_audio': save_new_audio,
                    'audio_dir': audio_dir,
                    'proposed_names': set()  # Empty for each file in monitor mode
                }
                
                success, new_name, match_info = process_single_video(
                    filepath, video_dir, ref_fps, rename_logger, config
                )
                
                if success and new_name:
                    try:
                        # Ensure target directory exists
                        if move_files and not os.path.exists(target_dir):
                            os.makedirs(target_dir)
                        
                        src = filepath
                        dst = os.path.join(target_dir, new_name)
                        os.rename(src, dst)
                        
                        processed_count += 1
                        method_icon = {'chromaprint': '🔊', 'slowed': '🐌', 'shazam': '🎵', 'shazam_new': '🎵✨'}.get(match_info.get('method'), '❓')
                        print(f"[{timestamp}] ✅ Renamed: {new_name} {method_icon}")
                        
                        # Log the rename
                        rename_logger.log_rename(
                            original_name=filename,
                            new_name=new_name,
                            video_dir=video_dir,
                            match_method=match_info.get('method', 'unknown'),
                            reference_name=match_info.get('reference'),
                            ber_score=match_info.get('ber'),
                            shazam_name=match_info.get('shazam_name'),
                            is_slowed=match_info.get('is_slowed', False),
                            slowed_speed=match_info.get('slowed_speed'),
                            tags_added=fixed_tags
                        )
                        
                    except Exception as e:
                        print(f"[{timestamp}] ❌ Error renaming: {e}")
                else:
                    error = match_info.get('error', 'Unknown error')
                    print(f"[{timestamp}] ❌ {error}")
                
                print()
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print(f"\n\n{'='*60}")
        print("🛑 Monitor stopped")
        print(f"📊 Total files processed this session: {processed_count}")
        print(f"📝 Total logged renames: {rename_logger.get_stats()['total_renames']}")
        print("=" * 60)


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='ShortsSync CLI - Chromaprint Audio Matcher',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli.py
  python cli.py --video-dir /path/to/videos --audio-dir /path/to/audio
  python cli.py -v /path/to/videos -a /path/to/audio --shazam
  python cli.py --rename-audio --audio-dir /path/to/audio --dry-run
  
Monitor Mode (auto-process new files):
  python cli.py --monitor
  python cli.py --monitor --monitor-interval 2
        """
    )
    parser.add_argument('-v', '--video-dir', help='Video source directory (overrides config.py)')
    parser.add_argument('-a', '--audio-dir', help='Audio reference directory (overrides config.py)')
    parser.add_argument('--rename-audio', action='store_true', 
                       help='Rename audio files based on Shazam identification')
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview changes without renaming (use with --rename-audio)')
    parser.add_argument('--shazam', action='store_true', default=None, help='Use Shazam to identify reference audio files during indexing (overrides config)')
    parser.add_argument('--no-shazam', dest='shazam', action='store_false', default=None, help='Disable Shazam for reference audio identification')
    parser.add_argument('--shazam-fallback', action='store_true', default=None, help='Use Shazam as fallback for unmatched videos (overrides config)')
    parser.add_argument('--no-shazam-fallback', dest='shazam_fallback', action='store_false', default=None, help='Disable Shazam fallback for unmatched videos')
    parser.add_argument('--save-new-audio', action='store_true', default=None, help='Save Shazam-identified audio to reference library (overrides config)')
    parser.add_argument('--no-save-new-audio', dest='save_new_audio', action='store_false', default=None, help='Disable saving Shazam-identified audio')
    parser.add_argument('--shazam-fallback-any', action='store_true', default=None, help='Use Shazam name even when song not in reference library (overrides config)')
    parser.add_argument('--no-shazam-fallback-any', dest='shazam_fallback_any', action='store_false', default=None, help='Disable using Shazam name when not in reference library')
    parser.add_argument('--threshold', type=float, default=0.15, help='BER threshold for matching (default: 0.15)')
    parser.add_argument('--history', action='store_true', help='Show rename history and exit')
    parser.add_argument('--history-limit', type=int, default=20, help='Number of history entries to show (default: 20)')
    parser.add_argument('--stats', action='store_true', help='Show rename statistics and exit')
    parser.add_argument('--search', type=str, help='Search rename history for a filename or song')
    parser.add_argument('--reindex', action='store_true', help='Force re-indexing of reference audio (ignore cache)')
    parser.add_argument('--index-stats', action='store_true', help='Show reference index cache statistics')
    parser.add_argument('--monitor', action='store_true', help='Continuously monitor video directory and process new files automatically')
    parser.add_argument('--monitor-interval', type=float, default=5.0, help='Polling interval in seconds for monitor mode (default: 5)')
    
    args = parser.parse_args()
    
    # Handle history/stats commands
    if args.history or args.stats or args.search or args.index_stats:
        rename_logger = RenameLogger()
        
        if args.stats:
            stats = rename_logger.get_stats()
            print("=" * 60)
            print("Rename Statistics")
            print("=" * 60)
            print(f"Total renames: {stats['total_renames']}")
            print(f"Slowed matches: {stats['slowed_count']}")
            print(f"Log file: {stats['log_file']}")
            if stats['by_method']:
                print("\nBy method:")
                for method, count in sorted(stats['by_method'].items()):
                    print(f"  {method}: {count}")
            if stats['newest_entry']:
                print(f"\nNewest: {stats['newest_entry']}")
            sys.exit(0)
        
        if args.search:
            results = rename_logger.search(args.search)
            print("=" * 60)
            print(f"Search results for: {args.search}")
            print("=" * 60)
            if not results:
                print("No matches found.")
            else:
                for entry in results[:args.history_limit]:
                    print(f"\n{entry['timestamp']}")
                    print(f"  {entry['original_name']}")
                    print(f"  → {entry['new_name']}")
                    print(f"  Method: {entry.get('match_method', 'unknown')}")
            sys.exit(0)
        
        if args.history:
            history = rename_logger.get_history(limit=args.history_limit)
            print("=" * 60)
            print(f"Recent Renames (last {args.history_limit})")
            print("=" * 60)
            if not history:
                print("No rename history found.")
            else:
                for entry in history:
                    print(f"\n{entry['timestamp']}")
                    print(f"  {entry['original_name']}")
                    print(f"  → {entry['new_name']}")
                    method = entry.get('match_method', 'unknown')
                    method_icon = {'chromaprint': '🔊', 'slowed': '🐌', 'shazam': '🎵', 'shazam_new': '🎵✨'}.get(method, '❓')
                    print(f"  Method: {method_icon} {method}")
            sys.exit(0)
        
        if args.index_stats:
            index_cache = ReferenceIndexCache()
            stats = index_cache.get_stats()
            print("=" * 60)
            print("Reference Index Cache Statistics")
            print("=" * 60)
            if stats['exists']:
                print(f"Status: ✅ Cached")
                print(f"Entries: {stats.get('entry_count', 'N/A')}")
                print(f"Audio dir: {stats.get('audio_dir', 'N/A')}")
                if stats.get('config'):
                    print(f"Config: {stats['config']}")
            else:
                print("Status: ❌ No cache found")
                print(f"Cache location: {stats['index_file']}")
            sys.exit(0)
    
    # Handle rename audio command
    if args.rename_audio:
        rename_audio_command(args)
        return
    

    
    print("=" * 60)
    print("ShortsSync CLI - Chromaprint Audio Matcher")
    print("=" * 60)
    
    # Check fpcalc
    fpcalc = get_fpcalc_path()
    
    if not fpcalc:
        print("\n❌ Error: fpcalc not found.")
        print("Install with: brew install chromaprint")
        sys.exit(1)
    
    # Load config
    try:
        defaults = config.get_defaults()
    except Exception as e:
        print(f"\n❌ Error loading config: {e}")
        sys.exit(1)
        
    # Handle monitor mode
    if args.monitor:
        monitor_mode(args, defaults)
        return
    
    # Use command-line args if provided, otherwise use config
    video_dir = args.video_dir if args.video_dir else defaults.get('video_dir', '')
    audio_dir = args.audio_dir if args.audio_dir else defaults.get('audio_dir', '')
    
    fixed_tags = defaults.get('fixed_tags', '#shorts')
    pool_tags = defaults.get('pool_tags', '#fyp #viral #trending')
    move_files = defaults.get('move_files', False)
    preserve_exact = defaults.get('preserve_exact_names', False)
    threshold = args.threshold
    
    if not video_dir or not audio_dir:
        print("\n❌ Error: video_dir and audio_dir must be set in config.py")
        sys.exit(1)
    
    if not os.path.exists(video_dir):
        print(f"\n❌ Error: Video directory not found: {video_dir}")
        sys.exit(1)
    
    if not os.path.exists(audio_dir):
        print(f"\n❌ Error: Audio directory not found: {audio_dir}")
        sys.exit(1)
    
    # Check Shazam availability - use CLI args if provided, otherwise fall back to config
    use_shazam_config = defaults.get('use_shazam', False)
    use_shazam_fallback_config = defaults.get('use_shazam_fallback', False)
    save_new_audio_config = defaults.get('save_new_audio', False)
    shazam_fallback_any_config = defaults.get('shazam_fallback_any', False)
    
    use_shazam = (args.shazam if args.shazam is not None else use_shazam_config) and is_shazam_available()
    use_shazam_fallback = (args.shazam_fallback if args.shazam_fallback is not None else use_shazam_fallback_config) and is_shazam_available()
    save_new_audio = (args.save_new_audio if args.save_new_audio is not None else save_new_audio_config) and is_shazam_available()
    shazam_fallback_any = (args.shazam_fallback_any if args.shazam_fallback_any is not None else shazam_fallback_any_config)
    detect_slowed = defaults.get('detect_slowed', False)
    slowed_speeds = defaults.get('slowed_speeds', [0.8, 0.7])
    
    # Initialize rename logger
    rename_log_file = defaults.get('rename_log_file', 'rename_history.jsonl')
    rename_logger = RenameLogger(rename_log_file)
    
    # Warn if Shazam is requested (via args or config) but not available
    shazam_requested = (args.shazam if args.shazam is not None else use_shazam_config) or \
                       (args.shazam_fallback if args.shazam_fallback is not None else use_shazam_fallback_config) or \
                       (args.save_new_audio if args.save_new_audio is not None else save_new_audio_config) or \
                       (args.shazam_fallback_any if args.shazam_fallback_any is not None else shazam_fallback_any_config)
    if shazam_requested and not is_shazam_available():
        print("\n⚠️  Warning: Shazam requested but shazamio not installed.")
        print("   Install with: pip install shazamio")
    
    print(f"\n📁 Video Source: {video_dir}")
    print(f"🎵 Audio Reference: {audio_dir}")
    print(f"🏷️  Fixed Tags: {fixed_tags}")
    print(f"🎲 Random Tags: {pool_tags}")
    print(f"📦 Move to _Ready: {move_files}")
    print(f"📝 Exact Names: {preserve_exact}")
    print(f"💾 Cache Directory: .fingerprints/")
    print(f"🎵 Shazam (reference ID): {'Enabled' if use_shazam else 'Disabled'}")
    print(f"🎵 Shazam (fallback): {'Enabled' if use_shazam_fallback else 'Disabled'}")
    print(f"💾 Save new audio: {'Enabled' if save_new_audio else 'Disabled'}")
    print(f"🎵 Shazam fallback any: {'Enabled' if shazam_fallback_any else 'Disabled'}")
    print(f"🐌 Slowed Detection: {'Enabled' if detect_slowed else 'Disabled'}")
    if detect_slowed:
        print(f"   Speeds checked: {slowed_speeds}")
    print(f"🎯 BER Threshold: {threshold}")
    
    # Initialize Shazam client if needed
    shazam_client = None
    if use_shazam:
        try:
            shazam_client = ShazamClient()
            print("✅ Shazam client initialized")
        except Exception as e:
            print(f"⚠️  Shazam init failed: {e}")
            use_shazam = False
    
    # Index reference audio
    print("\n" + "=" * 60)
    print("Indexing Reference Audio...")
    print("=" * 60)
    
    ref_fps = {}
    shazam_names = {}  # Maps original filename to Shazam-identified name
    audio_exts = ('.mp3', '.wav', '.m4a', '.flac', '.ogg')
    video_exts = ('.mp4', '.mov', '.mkv')
    
    # Check if we have a valid cached index
    index_cache = ReferenceIndexCache()
    config_for_cache = {
        'detect_slowed': detect_slowed,
        'slowed_speeds': slowed_speeds
    }
    
    use_cached_index = False
    if not args.reindex:
        try:
            if index_cache.is_cache_valid(audio_dir, config_for_cache):
                print("📦 Using cached reference index (no changes detected)")
                cached = index_cache.load_index()
                if cached:
                    ref_fps, shazam_names = cached
                    print(f"✅ Loaded {len(ref_fps)} fingerprints from cache")
                    use_cached_index = True
        except Exception as e:
            print(f"⚠️  Cache check failed: {e}")
    else:
        print("🔄 Force re-index requested (--reindex)")
    
    if not use_cached_index:
        print("🔄 Building reference index...")
        try:
            # Full indexing needed
            all_files = []
            for root, dirs, files in os.walk(audio_dir):
                # Skip hidden directories
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for f in files:
                    # Skip temporary files
                    if f.startswith('._temp_') or f.startswith('.temp_'):
                        continue
                    if f.lower().endswith(audio_exts) or f.lower().endswith(video_exts):
                        rel_path = os.path.relpath(os.path.join(root, f), audio_dir)
                        all_files.append(rel_path)
            
            audio_count = sum(1 for f in all_files if f.lower().endswith(audio_exts))
            video_count = sum(1 for f in all_files if f.lower().endswith(video_exts))
            print(f"Found {audio_count} audio files and {video_count} video files (including nested)")
            
            for i, rel_path in enumerate(all_files, 1):
                print(f"  [{i}/{len(all_files)}] {rel_path}")
                file_path = os.path.join(audio_dir, rel_path)
                filename = os.path.basename(rel_path)
                
                # If it's a video file, extract audio first
                if rel_path.lower().endswith(video_exts):
                    temp_audio = os.path.join(audio_dir, f".temp_ref_audio_{i}.wav")
                    try:
                        with VideoAudioExtractor(file_path, temp_audio) as extractor:
                            if not extractor.has_audio:
                                print("    ⚠️  No audio track")
                                continue
                            
                            extractor.extract_audio()
                            fp = get_fingerprint_cached(temp_audio, fpcalc)
                            
                            # Try Shazam identification
                            if use_shazam and fp is not None:
                                try:
                                    result = asyncio.run(shazam_client.identify(temp_audio, timeout=30))
                                    if result:
                                        shazam_names[filename] = result.get_filename_base()
                                        print(f"    🎵 Shazam: {result.artist} - {result.title}")
                                except Exception as e:
                                    print(f"    ⚠️  Shazam error: {e}")
                    except Exception as e:
                        print(f"    ⚠️  Error extracting audio: {e}")
                        continue
                else:
                    fp = get_fingerprint_cached(file_path, fpcalc)
                    
                    # Try Shazam identification for audio files too
                    if use_shazam and fp is not None:
                        try:
                            result = asyncio.run(shazam_client.identify(file_path, timeout=30))
                            if result:
                                shazam_names[filename] = result.get_filename_base()
                                print(f"    🎵 Shazam: {result.artist} - {result.title}")
                        except Exception as e:
                            print(f"    ⚠️  Shazam error: {e}")
                
                if fp is not None and len(fp) > 0:
                    # Use Shazam name if available, otherwise use filename
                    display_name = shazam_names.get(filename, filename)
                    ref_fps[display_name] = np.unpackbits(fp.view(np.uint8))
                    
                    # Generate slowed fingerprints for detection
                    if detect_slowed and rel_path.lower().endswith(audio_exts):
                        try:
                            slowed_fps = generate_slowed_fingerprints(file_path, slowed_speeds, fpcalc, audio_dir)
                            for speed, slowed_fp in slowed_fps.items():
                                if slowed_fp is not None and len(slowed_fp) > 0:
                                    slowed_name = f"{display_name} [SLOWED {speed}x]"
                                    ref_fps[slowed_name] = np.unpackbits(slowed_fp.view(np.uint8))
                        except Exception as e:
                            print(f"    ⚠️  Slowed fingerprint error: {e}")
            
            # Save the index to cache
            if ref_fps:
                print("\n💾 Saving index to cache...")
                if index_cache.save_index(audio_dir, ref_fps, shazam_names, config_for_cache):
                    print("✅ Index cached for next run")
                else:
                    print("⚠️  Failed to save cache")
                    
        except Exception as e:
            print(f"❌ Error indexing: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    if not ref_fps:
        print("\n❌ No reference fingerprints generated.")
        sys.exit(1)
    
    print(f"\n✅ Indexed {len(ref_fps)} reference tracks")
    if shazam_names:
        print(f"🎵 Shazam identified {len(shazam_names)} tracks")
    
    # Match videos
    print("\n" + "=" * 60)
    print("Matching Videos...")
    print("=" * 60)
    
    try:
        vid_files = [f for f in os.listdir(video_dir) if f.lower().endswith(('.mp4', '.mov', '.mkv'))]
    except Exception:
        vid_files = []
    
    if not vid_files:
        print("\n❌ No video files found.")
        sys.exit(0)
    
    print(f"Found {len(vid_files)} video files\n")
    
    matches = []
    proposed_names = set()
    shazam_fallback_matches = 0
    slowed_matches = 0
    
    # Initialize Shazam client for fallback if needed
    shazam_fallback_client = None
    if use_shazam_fallback:
        try:
            shazam_fallback_client = ShazamClient()
            print("\n🎵 Shazam fallback enabled for unmatched videos")
        except Exception as e:
            print(f"\n⚠️  Shazam fallback init failed: {e}")
            use_shazam_fallback = False
    
    for i, f in enumerate(vid_files, 1):
        print(f"[{i}/{len(vid_files)}] {f}")
        full_path = os.path.join(video_dir, f)
        temp_wav = os.path.join(video_dir, f".temp_extract_{i}.wav")
        
        matched = False
        
        try:
            with VideoAudioExtractor(full_path, temp_wav) as extractor:
                if not extractor.has_audio:
                    print("  ⚠️  No audio track")
                    continue
                
                extractor.extract_audio()
                
                q_fp = get_fingerprint_cached(temp_wav, fpcalc)
                if q_fp is None or len(q_fp) == 0:
                    print("  ⚠️  Fingerprint error")
                    continue
                
                q_bits = np.unpackbits(q_fp.view(np.uint8))
                n_q = len(q_bits)
                
                best_ber = 1.0
                best_ref = None
                
                for ref_name, r_bits in ref_fps.items():
                    n_r = len(r_bits)
                    if n_q > n_r: continue
                    
                    n_windows = (n_r // 32) - len(q_fp) + 1
                    if n_windows < 1: continue
                    
                    min_dist = float('inf')
                    for w in range(n_windows):
                        start = w * 32
                        end = start + n_q
                        sub_r = r_bits[start:end]
                        dist = np.count_nonzero(np.bitwise_xor(q_bits, sub_r))
                        if dist < min_dist:
                            min_dist = dist
                            if min_dist == 0: break
                    
                    ber = min_dist / n_q if n_q > 0 else 1.0
                    if ber < best_ber:
                        best_ber = ber
                        best_ref = ref_name
                        if best_ber == 0: break
                
                if best_ref and best_ber < threshold:
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
                    # Determine if slowed and extract speed
                    is_slowed = '[SLOWED' in best_ref
                    slowed_speed = None
                    if is_slowed:
                        speed_match = re.search(r'\[SLOWED ([\d.]+)x\]', best_ref)
                        if speed_match:
                            slowed_speed = float(speed_match.group(1))
                    
                    match_info = {
                        'method': 'slowed' if is_slowed else 'chromaprint',
                        'reference': best_ref,
                        'ber': best_ber,
                        'is_slowed': is_slowed,
                        'slowed_speed': slowed_speed
                    }
                    matches.append((f, new_name, match_info))
                    slowed_indicator = " 🐌" if is_slowed else ""
                    if slowed_indicator:
                        slowed_matches += 1
                    print(f"  ✅ Match: {best_ref} (BER: {best_ber:.3f}){slowed_indicator}")
                    print(f"     → {new_name}")
                    matched = True
                
                # Try Shazam fallback if no match
                if not matched and use_shazam_fallback and shazam_fallback_client:
                    try:
                        print(f"  🔍 Trying Shazam fallback... (max 30s)")
                        result = asyncio.run(shazam_fallback_client.identify(temp_wav, timeout=30))
                        
                        if result:
                            shazam_name = result.get_filename_base()
                            shazam_lower = shazam_name.lower()
                            
                            # Parse Shazam result (format: "Artist - Title")
                            shazam_parts = shazam_lower.split(' - ', 1)
                            shazam_artist = shazam_parts[0].strip() if len(shazam_parts) > 0 else ""
                            shazam_title = shazam_parts[1].strip() if len(shazam_parts) > 1 else ""
                            
                            # Look for match in reference library by name
                            best_match = None
                            best_score = 0
                            
                            for ref_name in ref_fps.keys():
                                ref_base = os.path.splitext(ref_name)[0].lower()
                                
                                # Check for exact substring match first
                                if shazam_lower in ref_base or ref_base in shazam_lower:
                                    best_match = ref_name
                                    best_score = 100
                                    break
                                
                                # Parse reference name and compare word-by-word
                                ref_parts = ref_base.split(' - ', 1)
                                ref_artist = ref_parts[0].strip() if len(ref_parts) > 0 else ""
                                ref_title = ref_parts[1].strip() if len(ref_parts) > 1 else ""
                                
                                # Calculate match score based on word overlap
                                def word_match_score(a, b):
                                    a_words = set(a.replace('_', ' ').replace('-', ' ').split())
                                    b_words = set(b.replace('_', ' ').replace('-', ' ').split())
                                    if not a_words or not b_words:
                                        return 0
                                    return len(a_words & b_words) / max(len(a_words), len(b_words))
                                
                                artist_score = word_match_score(shazam_artist, ref_artist)
                                title_score = word_match_score(shazam_title, ref_title)
                                
                                # Combined score weighted toward title match
                                score = (artist_score * 0.3 + title_score * 0.7) * 100
                                
                                if score > best_score and score >= 50:  # Threshold: 50% match
                                    best_score = score
                                    best_match = ref_name
                            
                            if best_match:
                                new_name = generate_name(
                                    ref_name=best_match,
                                    vid_name=f,
                                    vid_dir=video_dir,
                                    used_names=proposed_names,
                                    fixed_tags=fixed_tags,
                                    pool_tags=pool_tags,
                                    preserve_exact=preserve_exact
                                )
                                proposed_names.add(new_name.lower())
                                match_info = {
                                    'method': 'shazam',
                                    'reference': best_match,
                                    'ber': 0.0,
                                    'shazam_name': shazam_name,
                                    'similarity_score': best_score
                                }
                                matches.append((f, new_name, match_info))
                                if best_score == 100:
                                    print(f"  🎵 Shazam match: {best_match}")
                                else:
                                    print(f"  🎵 Shazam match: {best_match} ({best_score:.0f}% similarity)")
                                print(f"     → {new_name}")
                                shazam_fallback_matches += 1
                                matched = True
                                
                                # Save to reference library if enabled and this was a close match
                                if save_new_audio and temp_wav and os.path.exists(temp_wav):
                                    try:
                                        from shortssync import sanitize_filename
                                        safe_name = sanitize_filename(shazam_name)
                                        target_path = os.path.join(audio_dir, f"{safe_name}.mp3")
                                        # Handle duplicates
                                        counter = 1
                                        base_target = target_path
                                        while os.path.exists(target_path):
                                            target_path = base_target.replace('.mp3', f' ({counter}).mp3')
                                            counter += 1
                                        # Convert to mp3 using ffmpeg
                                        cmd = ['ffmpeg', '-y', '-i', temp_wav, '-q:a', '2', '-map', 'a', target_path]
                                        subprocess.run(cmd, capture_output=True, check=True)
                                        print(f"     💾 Saved to library: {os.path.basename(target_path)}")
                                    except Exception as e:
                                        print(f"     ⚠️  Could not save to library: {e}")
                                        
                            elif shazam_fallback_any:
                                # Use Shazam name directly even if not in reference library
                                new_name = generate_name(
                                    ref_name=shazam_name,
                                    vid_name=f,
                                    vid_dir=video_dir,
                                    used_names=proposed_names,
                                    fixed_tags=fixed_tags,
                                    pool_tags=pool_tags,
                                    preserve_exact=preserve_exact
                                )
                                proposed_names.add(new_name.lower())
                                match_info = {
                                    'method': 'shazam_new',
                                    'reference': shazam_name,
                                    'ber': 0.0,
                                    'shazam_name': shazam_name
                                }
                                matches.append((f, new_name, match_info))
                                print(f"  🎵 Shazam ID (not in library): {shazam_name}")
                                print(f"     → {new_name}")
                                shazam_fallback_matches += 1
                                matched = True
                                
                                # Save to reference library if enabled
                                if save_new_audio and temp_wav and os.path.exists(temp_wav):
                                    try:
                                        from shortssync import sanitize_filename
                                        safe_name = sanitize_filename(shazam_name)
                                        target_path = os.path.join(audio_dir, f"{safe_name}.mp3")
                                        # Handle duplicates
                                        counter = 1
                                        base_target = target_path
                                        while os.path.exists(target_path):
                                            target_path = base_target.replace('.mp3', f' ({counter}).mp3')
                                            counter += 1
                                        # Convert to mp3 using ffmpeg
                                        cmd = ['ffmpeg', '-y', '-i', temp_wav, '-q:a', '2', '-map', 'a', target_path]
                                        subprocess.run(cmd, capture_output=True, check=True)
                                        print(f"     💾 Saved to library: {os.path.basename(target_path)}")
                                    except Exception as e:
                                        print(f"     ⚠️  Could not save to library: {e}")
                            else:
                                print(f"  🎵 Shazam found '{shazam_name}' but not in reference library")
                    except Exception as e:
                        print(f"  ⚠️  Shazam error: {e}")
                
                if not matched:
                    print(f"  ❌ No match (best BER: {best_ber:.3f})")
        
        except Exception as e:
            print(f"  ❌ Error: {e}")
        # VideoAudioExtractor context manager handles cleanup
    
    # Summary
    print("\n" + "=" * 60)
    summary_parts = []
    if shazam_fallback_matches > 0:
        summary_parts.append(f"{shazam_fallback_matches} via Shazam")
    if slowed_matches > 0:
        summary_parts.append(f"{slowed_matches} slowed 🐌")
    
    if summary_parts:
        print(f"Found {len(matches)} matches ({', '.join(summary_parts)})")
    else:
        print(f"Found {len(matches)} matches")
    print("=" * 60)
    
    if not matches:
        print("\nNo files to rename.")
        sys.exit(0)
    
    # Confirm
    print("\nProposed renames:")
    for orig, new, info in matches:
        method = info.get('method', 'unknown')
        ber = info.get('ber', 0.0)
        method_icon = {'chromaprint': '🔊', 'slowed': '🐌', 'shazam': '🎵', 'shazam_new': '🎵✨'}.get(method, '❓')
        print(f"  {orig}")
        print(f"  → {new} ({method_icon} BER: {ber:.3f})\n")
    
    # response = input(f"\nRename {len(matches)} files? [y/N]: ").strip().lower()
    # if response != 'y':
    #     print("Cancelled.")
    #     sys.exit(0)
    
    # Rename
    target_dir = os.path.join(video_dir, "_Ready") if move_files else video_dir
    
    if move_files and not os.path.exists(target_dir):
        os.makedirs(target_dir)
        print(f"\n📁 Created: {target_dir}")
    
    count = 0
    for orig, new, info in matches:
        src = os.path.join(video_dir, orig)
        dst = os.path.join(target_dir, new)
        try:
            os.rename(src, dst)
            count += 1
            print(f"✅ {orig} → {new}")
            
            # Log the rename
            rename_logger.log_rename(
                original_name=orig,
                new_name=new,
                video_dir=video_dir,
                match_method=info.get('method', 'unknown'),
                reference_name=info.get('reference'),
                ber_score=info.get('ber'),
                shazam_name=info.get('shazam_name'),
                is_slowed=info.get('is_slowed', False),
                slowed_speed=info.get('slowed_speed'),
                tags_added=fixed_tags
            )
        except Exception as e:
            print(f"❌ Error renaming {orig}: {e}")
    
    print(f"\n✅ Successfully renamed {count}/{len(matches)} files")
    
    # Print Shazam cache stats if used
    if use_shazam and shazam_client:
        stats = shazam_client.get_cache_stats()
        print(f"\n🎵 Shazam cache: {stats['total_cached']} songs cached")
    
    # Print rename log location
    print(f"📝 Rename history: {rename_log_file}")
    
    # Show quick stats
    log_stats = rename_logger.get_stats()
    if log_stats['total_renames'] > 0:
        print(f"   Total logged renames: {log_stats['total_renames']}")


if __name__ == "__main__":
    main()
