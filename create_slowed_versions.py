#!/usr/bin/env python3
"""
Create slowed versions of reference audio for matching slowed videos.
Uses ffmpeg to generate speed-variated versions of your trending songs.
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import config
    defaults = config.get_defaults()
    AUDIO_DIR = defaults.get('audio_dir', '')
except Exception:
    AUDIO_DIR = ''


def create_slowed_version(input_path, output_path, speed):
    """
    Create a slowed version of an audio file using ffmpeg.
    
    Args:
        input_path: Path to original audio file
        output_path: Path for output file
        speed: Speed factor (0.5 = half speed, 0.7 = 70% speed)
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # ffmpeg atempo filter: 0.5 to 2.0 range
        # For speeds outside this range, we chain multiple atempo filters
        
        if speed >= 0.5:
            # Single atempo filter
            filter_str = f"atempo={speed}"
        else:
            # Chain filters for speeds < 0.5
            # 0.25x = atempo=0.5,atempo=0.5
            # 0.5x = atempo=0.5
            filter_str = f"atempo=0.5,atempo={speed/0.5}"
        
        cmd = [
            'ffmpeg',
            '-y',  # Overwrite output
            '-i', input_path,
            '-filter:a', filter_str,
            '-vn',  # No video
            '-c:a', 'libmp3lame',
            '-q:a', '2',  # High quality
            output_path
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        return result.returncode == 0
        
    except subprocess.TimeoutExpired:
        print(f"  ❌ Timeout processing {os.path.basename(input_path)}")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Create slowed versions of reference audio',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create 0.7x and 0.5x versions of all songs in audio dir
  python create_slowed_versions.py
  
  # Create specific speeds
  python create_slowed_versions.py --speeds 0.8 0.7 0.6 0.5
  
  # Process specific folder
  python create_slowed_versions.py --input-dir /path/to/audio --output-dir /path/to/slowed
        """
    )
    parser.add_argument('--input-dir', default=AUDIO_DIR,
                       help='Input directory with original audio files')
    parser.add_argument('--output-dir', default=None,
                       help='Output directory (default: input_dir/slowed)')
    parser.add_argument('--speeds', nargs='+', type=float, 
                       default=[0.8, 0.7, 0.5],
                       help='Speed factors to create (default: 0.8 0.7 0.5)')
    parser.add_argument('--formats', nargs='+', default=['.mp3', '.wav', '.m4a'],
                       help='Audio formats to process')
    
    args = parser.parse_args()
    
    if not args.input_dir:
        print("❌ Error: No input directory specified")
        print("Set audio_dir in config.py or use --input-dir")
        sys.exit(1)
    
    if not os.path.exists(args.input_dir):
        print(f"❌ Error: Input directory not found: {args.input_dir}")
        sys.exit(1)
    
    # Default output dir
    if not args.output_dir:
        args.output_dir = os.path.join(args.input_dir, 'slowed_versions')
    
    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Check ffmpeg
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Error: ffmpeg not found. Install with: brew install ffmpeg")
        sys.exit(1)
    
    print("=" * 70)
    print("Create Slowed Audio Versions")
    print("=" * 70)
    print(f"\nInput: {args.input_dir}")
    print(f"Output: {args.output_dir}")
    print(f"Speeds: {args.speeds}")
    
    # Find all audio files
    audio_files = []
    for root, dirs, files in os.walk(args.input_dir):
        # Skip already slowed versions
        if 'slowed_versions' in root:
            continue
            
        for f in files:
            if any(f.lower().endswith(ext) for ext in args.formats):
                audio_files.append(os.path.join(root, f))
    
    if not audio_files:
        print("\n❌ No audio files found")
        sys.exit(1)
    
    print(f"\nFound {len(audio_files)} audio files")
    print("\n" + "=" * 70)
    
    # Process each file
    total_created = 0
    
    for i, audio_path in enumerate(audio_files, 1):
        filename = os.path.basename(audio_path)
        name, ext = os.path.splitext(filename)
        
        print(f"\n[{i}/{len(audio_files)}] {filename}")
        
        for speed in args.speeds:
            # Create speed-specific subfolder
            speed_folder = os.path.join(args.output_dir, f"{speed}x")
            os.makedirs(speed_folder, exist_ok=True)
            
            output_name = f"{name}_{speed}x.mp3"
            output_path = os.path.join(speed_folder, output_name)
            
            # Skip if already exists
            if os.path.exists(output_path):
                print(f"  ⏭️  {speed}x already exists")
                continue
            
            print(f"  🐌 Creating {speed}x version...", end=' ')
            
            if create_slowed_version(audio_path, output_path, speed):
                print("✅")
                total_created += 1
            else:
                print("❌")
    
    print("\n" + "=" * 70)
    print("Complete!")
    print("=" * 70)
    print(f"\nCreated {total_created} slowed versions")
    print(f"\nFolder structure:")
    for speed in args.speeds:
        speed_folder = os.path.join(args.output_dir, f"{speed}x")
        count = len([f for f in os.listdir(speed_folder) if f.endswith('.mp3')]) if os.path.exists(speed_folder) else 0
        print(f"  {speed}x/: {count} files")
    
    print("\nUsage in ShortsSync:")
    print("  # Match normal speed videos")
    print(f"  python cli.py -a \"{args.input_dir}\"")
    print()
    print("  # Match slowed videos (0.7x)")
    print(f"  python cli.py -a \"{os.path.join(args.output_dir, '0.7x')}\"")
    print()
    print("  # Match heavily slowed videos (0.5x)")
    print(f"  python cli.py -a \"{os.path.join(args.output_dir, '0.5x')}\"")


if __name__ == "__main__":
    main()
