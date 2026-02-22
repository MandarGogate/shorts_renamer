#!/usr/bin/env python3
"""
Rename Audio Files with Shazam
Automatically rename reference audio files based on Shazam identification.

Usage:
    python rename_audio_files.py /path/to/audio
    python rename_audio_files.py /path/to/audio --dry-run
    python rename_audio_files.py /path/to/audio --recursive
"""

import os
import sys
import argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shortssync import ShazamClient, is_shazam_available
import asyncio


def sanitize_filename(name):
    """Remove invalid filename characters."""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, '_')
    return name.strip(' .')


def rename_audio_files(audio_dir, dry_run=False, recursive=False):
    """
    Rename audio files based on Shazam identification.
    
    Args:
        audio_dir: Directory containing audio files
        dry_run: Preview changes without renaming
        recursive: Process subdirectories
    """
    if not is_shazam_available():
        print("❌ Error: shazamio not installed")
        print("   pip install shazamio")
        return
    
    print("=" * 70)
    print("Rename Audio Files with Shazam")
    print("=" * 70)
    print(f"\nDirectory: {audio_dir}")
    print(f"Mode: {'DRY RUN (preview only)' if dry_run else 'LIVE (will rename)'}")
    print(f"Recursive: {'Yes' if recursive else 'No'}")
    
    # Supported formats
    audio_exts = ('.mp3', '.wav', '.m4a', '.flac', '.ogg', '.aac', '.wma')
    
    # Find all audio files
    audio_files = []
    if recursive:
        for root, dirs, files in os.walk(audio_dir):
            for f in files:
                if f.lower().endswith(audio_exts):
                    audio_files.append(os.path.join(root, f))
    else:
        for f in os.listdir(audio_dir):
            if f.lower().endswith(audio_exts):
                audio_files.append(os.path.join(audio_dir, f))
    
    if not audio_files:
        print("\n❌ No audio files found")
        return
    
    print(f"\nFound {len(audio_files)} audio file(s)")
    print("\n" + "=" * 70)
    print("Processing...")
    print("=" * 70)
    
    # Initialize Shazam client
    client = ShazamClient()
    
    renamed = 0
    failed = 0
    skipped = 0
    
    for i, file_path in enumerate(audio_files, 1):
        original_name = os.path.basename(file_path)
        print(f"\n[{i}/{len(audio_files)}] {original_name}")
        
        try:
            # Identify with Shazam
            result = asyncio.run(client.identify(file_path))
            
            if not result:
                print("  ⚠️  Could not identify")
                failed += 1
                continue
            
            # Create new filename
            artist = sanitize_filename(result.artist)
            title = sanitize_filename(result.title)
            
            if not artist or not title:
                print(f"  ⚠️  Invalid identification: {artist} - {title}")
                failed += 1
                continue
            
            new_name = f"{artist} - {title}"
            
            # Get file extension
            _, ext = os.path.splitext(original_name)
            new_filename = f"{new_name}{ext}"
            
            # Check if already correctly named
            if original_name == new_filename:
                print(f"  ✓ Already correctly named")
                skipped += 1
                continue
            
            # Full path for new file
            dir_path = os.path.dirname(file_path)
            new_path = os.path.join(dir_path, new_filename)
            
            # Handle duplicates
            counter = 1
            base_new_name = new_name
            while os.path.exists(new_path) and new_path != file_path:
                new_filename = f"{base_new_name} ({counter}){ext}"
                new_path = os.path.join(dir_path, new_filename)
                counter += 1
            
            print(f"  🎵 Identified: {result.artist} - {result.title}")
            print(f"  📝 {original_name}")
            print(f"  → {new_filename}")
            
            if dry_run:
                print("  [DRY RUN - no changes made]")
            else:
                # Perform rename
                os.rename(file_path, new_path)
                print("  ✅ Renamed successfully")
                renamed += 1
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
            failed += 1
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total files: {len(audio_files)}")
    print(f"✅ Renamed: {renamed}")
    print(f"⏭️  Skipped (already correct): {skipped}")
    print(f"❌ Failed: {failed}")
    
    if dry_run:
        print("\n💡 This was a DRY RUN. No files were actually renamed.")
        print("   Remove --dry-run to perform actual renaming.")
    
    print(f"\n💾 Shazam cache: {client.get_cache_stats()['total_cached']} songs cached")


def main():
    parser = argparse.ArgumentParser(
        description='Rename audio files based on Shazam identification',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview changes (dry run)
  python rename_audio_files.py /path/to/audio --dry-run
  
  # Actually rename files
  python rename_audio_files.py /path/to/audio
  
  # Include subdirectories
  python rename_audio_files.py /path/to/audio --recursive
  
  # Use config.py audio_dir
  python rename_audio_files.py
        """
    )
    parser.add_argument('directory', nargs='?', default=None,
                       help='Directory containing audio files (default: config audio_dir)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview changes without renaming')
    parser.add_argument('--recursive', '-r', action='store_true',
                       help='Process subdirectories')
    
    args = parser.parse_args()
    
    # Get directory
    audio_dir = args.directory
    if not audio_dir:
        try:
            import config
            defaults = config.get_defaults()
            audio_dir = defaults.get('audio_dir')
        except Exception:
            pass
    
    if not audio_dir:
        print("❌ Error: No directory specified")
        print("Set audio_dir in config.py or provide as argument")
        sys.exit(1)
    
    if not os.path.exists(audio_dir):
        print(f"❌ Error: Directory not found: {audio_dir}")
        sys.exit(1)
    
    rename_audio_files(audio_dir, args.dry_run, args.recursive)


if __name__ == "__main__":
    main()
