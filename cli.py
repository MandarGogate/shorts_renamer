#!/usr/bin/env python3
"""
ShortsSync CLI - Command-line version that runs with default settings from config.py
"""

import os
import sys
import shutil
import subprocess
import numpy as np
from moviepy import VideoFileClip
import random
import argparse

try:
    import config
except ImportError:
    print("Error: config.py not found. Please ensure it exists in the same directory.")
    sys.exit(1)

def get_fingerprint(path, fpcalc_path):
    """Extract Chromaprint fingerprint from audio file."""
    try:
        cmd = [fpcalc_path, "-raw", path]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        for line in res.stdout.splitlines():
            if line.startswith("FINGERPRINT="):
                raw = line[12:]
                if not raw: return None
                return np.array([int(x) for x in raw.split(',')], dtype=np.uint32)
    except Exception as e:
        print(f"  Error getting fingerprint: {e}")
        return None
    return None

def generate_name(ref_name, vid_name, vid_dir, used_names, fixed_tags, pool_tags, preserve_exact):
    """Generate unique filename based on reference."""
    base = os.path.splitext(ref_name)[0]
    ext = os.path.splitext(vid_name)[1]
    
    if preserve_exact:
        candidate = f"{base}{ext}"
        if not os.path.exists(os.path.join(vid_dir, candidate)) and candidate.lower() not in used_names:
            return candidate
        for i in range(1, 100):
            c = f"{base}_{i}{ext}"
            if not os.path.exists(os.path.join(vid_dir, c)) and c.lower() not in used_names:
                return c
    
    pool = pool_tags.split() if pool_tags else []
    
    for _ in range(20):
        tags = random.sample(pool, k=min(2, len(pool))) if pool else []
        tag_str = " ".join(tags)
        full = f"{base} {fixed_tags} {tag_str}".strip()
        candidate = f"{full}{ext}"
        if not os.path.exists(os.path.join(vid_dir, candidate)) and candidate.lower() not in used_names:
            return candidate
    
    return f"{base}_{random.randint(1000,9999)}{ext}"

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='ShortsSync CLI - Chromaprint Audio Matcher',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli_sync.py
  python cli_sync.py --video-dir /path/to/videos --audio-dir /path/to/audio
  python cli_sync.py -v /path/to/videos -a /path/to/audio
        """
    )
    parser.add_argument('-v', '--video-dir', help='Video source directory (overrides config.py)')
    parser.add_argument('-a', '--audio-dir', help='Audio reference directory (overrides config.py)')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("ShortsSync CLI - Chromaprint Audio Matcher")
    print("=" * 60)
    
    # Check fpcalc
    fpcalc = shutil.which("fpcalc")
    if not fpcalc and os.path.exists("/opt/homebrew/bin/fpcalc"):
        fpcalc = "/opt/homebrew/bin/fpcalc"
    
    if not fpcalc:
        print("\n❌ Error: fpcalc not found.")
        print("Install with: brew install chromaprint")
        sys.exit(1)
    
    # Load config
    defaults = config.get_defaults()
    
    # Use command-line args if provided, otherwise use config
    video_dir = args.video_dir if args.video_dir else defaults.get('video_dir', '')
    audio_dir = args.audio_dir if args.audio_dir else defaults.get('audio_dir', '')
    
    fixed_tags = defaults.get('fixed_tags', '#shorts')
    pool_tags = defaults.get('pool_tags', '#fyp #viral #trending')
    move_files = defaults.get('move_files', False)
    preserve_exact = defaults.get('preserve_exact_names', False)
    
    if not video_dir or not audio_dir:
        print("\n❌ Error: video_dir and audio_dir must be set in config.py")
        sys.exit(1)
    
    if not os.path.exists(video_dir):
        print(f"\n❌ Error: Video directory not found: {video_dir}")
        sys.exit(1)
    
    if not os.path.exists(audio_dir):
        print(f"\n❌ Error: Audio directory not found: {audio_dir}")
        sys.exit(1)
    
    print(f"\n📁 Video Source: {video_dir}")
    print(f"🎵 Audio Reference: {audio_dir}")
    print(f"🏷️  Fixed Tags: {fixed_tags}")
    print(f"🎲 Random Tags: {pool_tags}")
    print(f"📦 Move to _Ready: {move_files}")
    print(f"📝 Exact Names: {preserve_exact}")
    
    # Index reference audio
    print("\n" + "=" * 60)
    print("Indexing Reference Audio...")
    print("=" * 60)
    
    ref_fps = {}
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
            
            # If it's a video file, extract audio first
            if rel_path.lower().endswith(video_exts):
                temp_audio = os.path.join(audio_dir, ".temp_ref_audio.wav")
                try:
                    video = VideoFileClip(file_path)
                    if not video.audio:
                        video.close()
                        print("    ⚠️  No audio track")
                        continue
                    video.audio.write_audiofile(temp_audio, logger=None, codec='pcm_s16le')
                    video.close()
                    fp = get_fingerprint(temp_audio, fpcalc)
                    if os.path.exists(temp_audio):
                        try: os.remove(temp_audio)
                        except: pass
                except Exception as e:
                    print(f"    ⚠️  Error extracting audio: {e}")
                    continue
            else:
                fp = get_fingerprint(file_path, fpcalc)
            
            if fp is not None and len(fp) > 0:
                # Use just the filename (without path) as the key
                filename = os.path.basename(rel_path)
                ref_fps[filename] = np.unpackbits(fp.view(np.uint8))
    except Exception as e:
        print(f"❌ Error indexing: {e}")
        sys.exit(1)
    
    if not ref_fps:
        print("\n❌ No reference fingerprints generated.")
        sys.exit(1)
    
    print(f"\n✅ Indexed {len(ref_fps)} reference tracks")
    
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
    
    for i, f in enumerate(vid_files, 1):
        print(f"[{i}/{len(vid_files)}] {f}")
        full_path = os.path.join(video_dir, f)
        temp_wav = os.path.join(video_dir, ".temp_extract.wav")
        
        try:
            video = VideoFileClip(full_path)
            if not video.audio:
                video.close()
                print("  ⚠️  No audio track")
                continue
            
            video.audio.write_audiofile(temp_wav, logger=None, codec='pcm_s16le')
            video.close()
            
            q_fp = get_fingerprint(temp_wav, fpcalc)
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
                
                n_windows = (n_r // 32) - (len(q_fp)) + 1
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
                
                ber = min_dist / n_q
                if ber < best_ber:
                    best_ber = ber
                    best_ref = ref_name
                    if best_ber == 0: break
            
            if best_ref and best_ber < 0.15:
                new_name = generate_name(best_ref, f, video_dir, proposed_names, 
                                        fixed_tags, pool_tags, preserve_exact)
                proposed_names.add(new_name.lower())
                matches.append((f, new_name, best_ber))
                print(f"  ✅ Match: {best_ref} (BER: {best_ber:.3f})")
                print(f"     → {new_name}")
            else:
                print(f"  ❌ No match (best BER: {best_ber:.3f})")
        
        except Exception as e:
            print(f"  ❌ Error: {e}")
        finally:
            if os.path.exists(temp_wav):
                try: os.remove(temp_wav)
                except: pass
    
    # Summary
    print("\n" + "=" * 60)
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

if __name__ == "__main__":
    main()
