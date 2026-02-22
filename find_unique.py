#!/usr/bin/env python3
"""
Find Unique Audio Files - Uses Chromaprint to identify duplicate audio files
"""

import os
import sys
import shutil
import argparse
from collections import defaultdict

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shortssync import (
    get_fingerprint,
    get_fpcalc_path,
    VideoAudioExtractor,
    compare_fingerprints,
    ShazamClient,
    is_shazam_available
)

try:
    import numpy as np
except ImportError:
    print("Error: numpy is required.\npip install numpy")
    sys.exit(1)


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
  python find_unique.py /path/to/audio --shazam  # Identify songs with Shazam
        """
    )
    parser.add_argument('directory', help='Directory to scan for audio/video files (includes subdirectories)')
    parser.add_argument('-t', '--threshold', type=float, default=0.15,
                       help='BER threshold for duplicates (default: 0.15)')
    parser.add_argument('-o', '--output', help='Output file to save unique filenames')
    parser.add_argument('-c', '--copy-to', help='Copy unique files to this directory')
    parser.add_argument('--convert-to-mp3', action='store_true',
                       help='Convert video files to MP3 when copying (requires --copy-to)')
    parser.add_argument('--shazam', action='store_true',
                       help='Use Shazam to identify songs')
    
    args = parser.parse_args()
    
    # Check fpcalc
    fpcalc = get_fpcalc_path()
    
    if not fpcalc:
        print("❌ Error: fpcalc not found.")
        print("Install with: brew install chromaprint")
        sys.exit(1)
    
    # Check Shazam availability
    use_shazam = args.shazam and is_shazam_available()
    if args.shazam and not is_shazam_available():
        print("⚠️  Warning: Shazam requested but shazamio not installed.")
        print("   Install with: pip install shazamio")
    
    # Validate directory
    if not os.path.exists(args.directory):
        print(f"❌ Error: Directory not found: {args.directory}")
        sys.exit(1)
    
    print("=" * 70)
    print("Find Unique Audio Files - Chromaprint Deduplicator")
    print("=" * 70)
    print(f"\n📁 Directory: {args.directory}")
    print(f"🎯 BER Threshold: {args.threshold}")
    print(f"🔄 Recursive: Yes (includes subdirectories)")
    print(f"🎵 Shazam Integration: {'Enabled' if use_shazam else 'Disabled'}")
    
    # Initialize Shazam client if needed
    shazam_client = None
    shazam_results = {}
    if use_shazam:
        try:
            shazam_client = ShazamClient()
            print("✅ Shazam client initialized")
        except Exception as e:
            print(f"⚠️  Shazam init failed: {e}")
            use_shazam = False
    
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
    
    for i, file_path in enumerate(all_files, 1):
        filename = os.path.basename(file_path)
        print(f"[{i}/{len(all_files)}] {filename}")
        
        # Check if it's a video file
        if file_path.lower().endswith(video_exts):
            temp_audio = os.path.join(args.directory, f".temp_unique_check_{i}.wav")
            try:
                with VideoAudioExtractor(file_path, temp_audio) as extractor:
                    if not extractor.has_audio:
                        print("  ⚠️  No audio track")
                        continue
                    
                    extractor.extract_audio()
                    fp = get_fingerprint(temp_audio, fpcalc)
                    
                    # Try Shazam identification
                    if use_shazam and fp is not None:
                        try:
                            import asyncio
                            result = asyncio.run(shazam_client.identify(temp_audio))
                            if result:
                                shazam_results[file_path] = result
                                print(f"  🎵 Shazam: {result.artist} - {result.title}")
                        except Exception as e:
                            print(f"  ⚠️  Shazam error: {e}")
            except Exception as e:
                print(f"  ⚠️  Error extracting audio: {e}")
                continue
        else:
            fp = get_fingerprint(file_path, fpcalc)
            
            # Try Shazam identification for audio files too
            if use_shazam and fp is not None:
                try:
                    import asyncio
                    result = asyncio.run(shazam_client.identify(file_path))
                    if result:
                        shazam_results[file_path] = result
                        print(f"  🎵 Shazam: {result.artist} - {result.title}")
                except Exception as e:
                    print(f"  ⚠️  Shazam error: {e}")
        
        if fp is not None:
            fingerprints[file_path] = fp
        else:
            print("  ⚠️  Failed to extract fingerprint")
    
    print(f"\n✅ Extracted {len(fingerprints)} fingerprints")
    if shazam_results:
        print(f"🎵 Shazam identified {len(shazam_results)} tracks")
    
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
            
            is_match, ber = compare_fingerprints(
                fingerprints[file1], 
                fingerprints[file2], 
                args.threshold
            )
            
            if is_match:
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
                shazam_info = ""
                if file_path in shazam_results:
                    r = shazam_results[file_path]
                    shazam_info = f" [{r.artist} - {r.title}]"
                print(f"  {marker}: {os.path.basename(file_path)}{shazam_info}")
    
    # Print Shazam results for unique files
    if shazam_results:
        print("\n" + "=" * 70)
        print("SHAZAM IDENTIFICATIONS")
        print("=" * 70)
        for file_path in unique_files:
            if file_path in shazam_results:
                r = shazam_results[file_path]
                print(f"\n{os.path.basename(file_path)}")
                print(f"  Artist: {r.artist}")
                print(f"  Title: {r.title}")
                print(f"  Album: {r.album or 'N/A'}")
                print(f"  Genre: {r.genre or 'N/A'}")
                if r.shazam_url:
                    print(f"  URL: {r.shazam_url}")
    
    # Save to file if requested
    if args.output:
        with open(args.output, 'w') as f:
            for file_path in unique_files:
                # Include Shazam info if available
                if file_path in shazam_results:
                    r = shazam_results[file_path]
                    f.write(f"{file_path}|{r.artist}|{r.title}\n")
                else:
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
        
        for file_path in unique_files:
            filename = os.path.basename(file_path)
            
            # Use Shazam name for output if available
            if file_path in shazam_results:
                r = shazam_results[file_path]
                base_name = f"{r.artist} - {r.title}"
                # Sanitize filename
                base_name = "".join(c for c in base_name if c.isalnum() or c in (' ', '-', '_')).strip()
            else:
                base_name = os.path.splitext(filename)[0]
            
            # Determine output filename
            if args.convert_to_mp3 and file_path.lower().endswith(video_exts):
                output_filename = f"{base_name}.mp3"
            else:
                ext = os.path.splitext(filename)[1]
                output_filename = f"{base_name}{ext}"
            
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
                    # Extract audio and save as MP3 using moviepy directly
                    try:
                        from moviepy import VideoFileClip
                    except ImportError:
                        from moviepy.editor import VideoFileClip
                    
                    video = None
                    try:
                        video = VideoFileClip(file_path)
                        if not video.audio:
                            print(f"  ⚠️  {filename}: No audio track, skipping")
                            continue
                        
                        video.audio.write_audiofile(
                            dest_path, 
                            logger=None, 
                            codec='mp3', 
                            bitrate='192k',
                            verbose=False
                        )
                        print(f"  ✅ {filename} → {output_filename} (converted)")
                    finally:
                        if video is not None:
                            try:
                                video.close()
                            except:
                                pass
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
        display_name = os.path.basename(file_path)
        if file_path in shazam_results:
            r = shazam_results[file_path]
            display_name = f"{display_name} [{r.artist} - {r.title}]"
        print(f"  {display_name}")
    
    # Print Shazam cache stats
    if use_shazam and shazam_client:
        stats = shazam_client.get_cache_stats()
        print(f"\n🎵 Shazam cache: {stats['total_cached']} songs cached")

if __name__ == "__main__":
    main()
