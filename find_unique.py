#!/usr/bin/env python3
"""
Find Unique Audio Files - Uses Chromaprint to identify duplicate audio files
"""

import os
import sys
import shutil
import subprocess
import argparse
from collections import defaultdict

try:
    import numpy as np
except ImportError:
    print("Error: numpy is required.\npip install numpy")
    sys.exit(1)

try:
    from moviepy import VideoFileClip
except ImportError:
    print("Error: moviepy is required.\npip install moviepy")
    sys.exit(1)

def get_fingerprint(path, fpcalc_path):
    """Extract Chromaprint fingerprint from audio/video file."""
    try:
        cmd = [fpcalc_path, "-raw", path]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        for line in res.stdout.splitlines():
            if line.startswith("FINGERPRINT="):
                raw = line[12:]
                if not raw: return None
                return np.array([int(x) for x in raw.split(',')], dtype=np.uint32)
    except Exception:
        return None
    return None

def extract_audio_from_video(video_path, output_path):
    """Extract audio from video file to temporary WAV."""
    try:
        video = VideoFileClip(video_path)
        if not video.audio:
            video.close()
            return False
        video.audio.write_audiofile(output_path, logger=None, codec='pcm_s16le')
        video.close()
        return True
    except Exception:
        return False

def compare_fingerprints(fp1, fp2, threshold=0.15):
    """Compare two fingerprints using Bit Error Rate (BER)."""
    if fp1 is None or fp2 is None:
        return False
    
    bits1 = np.unpackbits(fp1.view(np.uint8))
    bits2 = np.unpackbits(fp2.view(np.uint8))
    
    # Make sure they're the same length (use shorter)
    min_len = min(len(bits1), len(bits2))
    bits1 = bits1[:min_len]
    bits2 = bits2[:min_len]
    
    # Calculate BER
    diff = np.count_nonzero(np.bitwise_xor(bits1, bits2))
    ber = diff / min_len
    
    return ber < threshold

def main():
    parser = argparse.ArgumentParser(
        description='Find unique audio files using Chromaprint fingerprinting',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python find_unique.py /path/to/audio
  python find_unique.py /path/to/audio --threshold 0.10
  python find_unique.py /path/to/audio --output unique_list.txt
  python find_unique.py /path/to/audio --copy-to /path/to/unique_folder
  python find_unique.py /path/to/audio --copy-to /path/to/output --convert-to-mp3
        """
    )
    parser.add_argument('directory', help='Directory to scan for audio/video files (includes subdirectories)')
    parser.add_argument('-t', '--threshold', type=float, default=0.15,
                       help='BER threshold for duplicates (default: 0.15)')
    parser.add_argument('-o', '--output', help='Output file to save unique filenames')
    parser.add_argument('-c', '--copy-to', help='Copy unique files to this directory')
    parser.add_argument('--convert-to-mp3', action='store_true',
                       help='Convert video files to MP3 when copying (requires --copy-to)')
    
    args = parser.parse_args()
    
    # Check fpcalc
    fpcalc = shutil.which("fpcalc")
    if not fpcalc and os.path.exists("/opt/homebrew/bin/fpcalc"):
        fpcalc = "/opt/homebrew/bin/fpcalc"
    
    if not fpcalc:
        print("❌ Error: fpcalc not found.")
        print("Install with: brew install chromaprint")
        sys.exit(1)
    
    if not os.path.exists(args.directory):
        print(f"❌ Error: Directory not found: {args.directory}")
        sys.exit(1)
    
    print("=" * 70)
    print("Find Unique Audio Files - Chromaprint Deduplicator")
    print("=" * 70)
    print(f"\n📁 Directory: {args.directory}")
    print(f"🎯 BER Threshold: {args.threshold}")
    print(f"🔄 Recursive: Yes (includes subdirectories)")
    
    # Find all files (always recursive)
    audio_exts = ('.mp3', '.wav', '.m4a', '.flac', '.ogg')
    video_exts = ('.mp4', '.mov', '.mkv')
    
    all_files = []
    for root, dirs, files in os.walk(args.directory):
        for f in files:
            if f.lower().endswith(audio_exts) or f.lower().endswith(video_exts):
                full_path = os.path.join(root, f)
                all_files.append(full_path)
    
    if not all_files:
        print("\n❌ No audio/video files found.")
        sys.exit(0)
    
    print(f"\n📊 Found {len(all_files)} files to analyze\n")
    
    # Extract fingerprints
    print("=" * 70)
    print("Extracting Fingerprints...")
    print("=" * 70)
    
    fingerprints = {}
    temp_audio = os.path.join(args.directory, ".temp_unique_check.wav")
    
    for i, file_path in enumerate(all_files, 1):
        filename = os.path.basename(file_path)
        print(f"[{i}/{len(all_files)}] {filename}")
        
        # Check if it's a video file
        if file_path.lower().endswith(video_exts):
            if extract_audio_from_video(file_path, temp_audio):
                fp = get_fingerprint(temp_audio, fpcalc)
                if os.path.exists(temp_audio):
                    try: os.remove(temp_audio)
                    except: pass
            else:
                print("  ⚠️  No audio track")
                continue
        else:
            fp = get_fingerprint(file_path, fpcalc)
        
        if fp is not None:
            fingerprints[file_path] = fp
        else:
            print("  ⚠️  Failed to extract fingerprint")
    
    print(f"\n✅ Extracted {len(fingerprints)} fingerprints")
    
    # Find duplicates
    print("\n" + "=" * 70)
    print("Finding Duplicates...")
    print("=" * 70)
    
    unique_files = []
    duplicate_groups = []
    processed = set()
    
    file_list = list(fingerprints.keys())
    
    for i, file1 in enumerate(file_list):
        if file1 in processed:
            continue
        
        group = [file1]
        processed.add(file1)
        
        for file2 in file_list[i+1:]:
            if file2 in processed:
                continue
            
            if compare_fingerprints(fingerprints[file1], fingerprints[file2], args.threshold):
                group.append(file2)
                processed.add(file2)
        
        if len(group) == 1:
            unique_files.append(file1)
        else:
            duplicate_groups.append(group)
            unique_files.append(group[0])  # Keep first one as representative
    
    # Results
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    
    print(f"\n📊 Total files analyzed: {len(fingerprints)}")
    print(f"✅ Unique files: {len(unique_files)}")
    print(f"🔄 Duplicate groups: {len(duplicate_groups)}")
    
    if duplicate_groups:
        print("\n" + "=" * 70)
        print("DUPLICATE GROUPS")
        print("=" * 70)
        
        for i, group in enumerate(duplicate_groups, 1):
            print(f"\n📦 Group {i} ({len(group)} files):")
            for j, file_path in enumerate(group):
                marker = "✓ KEEP" if j == 0 else "  duplicate"
                print(f"  {marker}: {os.path.basename(file_path)}")
    
    # Save to file if requested
    if args.output:
        with open(args.output, 'w') as f:
            for file_path in unique_files:
                f.write(f"{file_path}\n")
        print(f"\n💾 Unique files saved to: {args.output}")
    
    # Copy unique files if requested
    if args.copy_to:
        print("\n" + "=" * 70)
        if args.convert_to_mp3:
            print("COPYING & CONVERTING UNIQUE FILES TO MP3")
        else:
            print("COPYING UNIQUE FILES")
        print("=" * 70)
        
        # Create target directory if it doesn't exist
        if not os.path.exists(args.copy_to):
            os.makedirs(args.copy_to)
            print(f"\n📁 Created directory: {args.copy_to}")
        
        copied = 0
        failed = 0
        
        video_exts = ('.mp4', '.mov', '.mkv')
        
        for file_path in unique_files:
            filename = os.path.basename(file_path)
            
            # Determine output filename
            if args.convert_to_mp3 and file_path.lower().endswith(video_exts):
                # Convert video to MP3
                base_name = os.path.splitext(filename)[0]
                output_filename = f"{base_name}.mp3"
            else:
                # Keep original extension
                output_filename = filename
            
            dest_path = os.path.join(args.copy_to, output_filename)
            
            try:
                # Handle filename conflicts
                if os.path.exists(dest_path):
                    base, ext = os.path.splitext(output_filename)
                    counter = 1
                    while os.path.exists(dest_path):
                        new_filename = f"{base}_{counter}{ext}"
                        dest_path = os.path.join(args.copy_to, new_filename)
                        counter += 1
                    print(f"  ⚠️  Renamed: {output_filename} → {os.path.basename(dest_path)}")
                    output_filename = os.path.basename(dest_path)
                
                # Convert or copy
                if args.convert_to_mp3 and file_path.lower().endswith(video_exts):
                    # Extract audio and save as MP3
                    video = VideoFileClip(file_path)
                    if not video.audio:
                        video.close()
                        print(f"  ⚠️  {filename}: No audio track, skipping")
                        continue
                    
                    video.audio.write_audiofile(dest_path, logger=None, codec='mp3', bitrate='192k')
                    video.close()
                    print(f"  ✅ {filename} → {output_filename} (converted)")
                else:
                    # Regular copy
                    shutil.copy2(file_path, dest_path)
                    print(f"  ✅ {output_filename}")
                
                copied += 1
            except Exception as e:
                failed += 1
                print(f"  ❌ {filename}: {e}")
        
        print(f"\n📊 Copied {copied}/{len(unique_files)} files")
        if failed > 0:
            print(f"⚠️  Failed: {failed} files")
    
    print("\n" + "=" * 70)
    print("UNIQUE FILES")
    print("=" * 70)
    for file_path in unique_files:
        print(f"  {os.path.basename(file_path)}")

if __name__ == "__main__":
    main()
