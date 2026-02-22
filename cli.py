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
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shortssync import (
    get_fingerprint_cached,
    generate_name,
    get_fpcalc_path,
    VideoAudioExtractor,
    ShazamClient,
    is_shazam_available
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
    import asyncio
    
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
        """
    )
    parser.add_argument('-v', '--video-dir', help='Video source directory (overrides config.py)')
    parser.add_argument('-a', '--audio-dir', help='Audio reference directory (overrides config.py)')
    parser.add_argument('--rename-audio', action='store_true', 
                       help='Rename audio files based on Shazam identification')
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview changes without renaming (use with --rename-audio)')
    parser.add_argument('--shazam', action='store_true', help='Use Shazam to identify reference audio files during indexing')
    parser.add_argument('--shazam-fallback', action='store_true', help='Use Shazam as fallback for unmatched videos')
    parser.add_argument('--threshold', type=float, default=0.15, help='BER threshold for matching (default: 0.15)')
    
    args = parser.parse_args()
    
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
    
    # Check Shazam availability
    use_shazam = args.shazam and is_shazam_available()
    use_shazam_fallback = args.shazam_fallback and is_shazam_available()
    
    if (args.shazam or args.shazam_fallback) and not is_shazam_available():
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
    
    try:
        # Recursively find all audio and video files
        all_files = []
        for root, dirs, files in os.walk(audio_dir):
            for f in files:
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
                                import asyncio
                                result = asyncio.run(shazam_client.identify(temp_audio))
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
                        import asyncio
                        result = asyncio.run(shazam_client.identify(file_path))
                        if result:
                            shazam_names[filename] = result.get_filename_base()
                            print(f"    🎵 Shazam: {result.artist} - {result.title}")
                    except Exception as e:
                        print(f"    ⚠️  Shazam error: {e}")
            
            if fp is not None and len(fp) > 0:
                # Use Shazam name if available, otherwise use filename
                display_name = shazam_names.get(filename, filename)
                ref_fps[display_name] = np.unpackbits(fp.view(np.uint8))
                
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
                    matches.append((f, new_name, best_ber))
                    print(f"  ✅ Match: {best_ref} (BER: {best_ber:.3f})")
                    print(f"     → {new_name}")
                    matched = True
                
                # Try Shazam fallback if no match
                if not matched and use_shazam_fallback and shazam_fallback_client:
                    try:
                        print(f"  🔍 Trying Shazam fallback...")
                        result = asyncio.run(shazam_fallback_client.identify(temp_wav))
                        
                        if result:
                            shazam_name = result.get_filename_base()
                            # Look for match in reference library by name
                            for ref_name in ref_fps.keys():
                                ref_base = os.path.splitext(ref_name)[0].lower()
                                shazam_lower = shazam_name.lower()
                                
                                if shazam_lower in ref_base or ref_base in shazam_lower:
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
                                    matches.append((f, new_name, 0.0))
                                    print(f"  🎵 Shazam match: {ref_name}")
                                    print(f"     → {new_name}")
                                    shazam_fallback_matches += 1
                                    matched = True
                                    break
                            
                            if not matched:
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
    if shazam_fallback_matches > 0:
        print(f"Found {len(matches)} matches ({shazam_fallback_matches} via Shazam fallback)")
    else:
        print(f"Found {len(matches)} matches")
    print("=" * 60)
    
    if not matches:
        print("\nNo files to rename.")
        sys.exit(0)
    
    # Confirm
    print("\nProposed renames:")
    for orig, new, ber in matches:
        print(f"  {orig}")
        print(f"  → {new} (BER: {ber:.3f})\n")
    
    response = input(f"\nRename {len(matches)} files? [y/N]: ").strip().lower()
    if response != 'y':
        print("Cancelled.")
        sys.exit(0)
    
    # Rename
    target_dir = os.path.join(video_dir, "_Ready") if move_files else video_dir
    
    if move_files and not os.path.exists(target_dir):
        os.makedirs(target_dir)
        print(f"\n📁 Created: {target_dir}")
    
    count = 0
    for orig, new, _ in matches:
        src = os.path.join(video_dir, orig)
        dst = os.path.join(target_dir, new)
        try:
            os.rename(src, dst)
            count += 1
            print(f"✅ {orig} → {new}")
        except Exception as e:
            print(f"❌ Error renaming {orig}: {e}")
    
    print(f"\n✅ Successfully renamed {count}/{len(matches)} files")
    
    # Print Shazam cache stats if used
    if use_shazam and shazam_client:
        stats = shazam_client.get_cache_stats()
        print(f"\n🎵 Shazam cache: {stats['total_cached']} songs cached")


if __name__ == "__main__":
    main()
