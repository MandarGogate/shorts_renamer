#!/usr/bin/env python3
"""
MP3 Downloader - Download audio from URLs to the configured audio_dir.

Usage:
    python download_mp3.py

Input format (one per line):
    URL [optional_filename]

Examples:
    https://www.youtube.com/watch?v=dQw4w9WgXcQ
    https://www.youtube.com/watch?v=dQw4w9WgXcQ RickRoll
    https://soundcloud.com/artist/track MyTrack

Enter a blank line to start processing.
Press Ctrl+D (Unix) or Ctrl+Z (Windows) to finish input.
"""

import os
import sys

try:
    import yt_dlp
except ImportError:
    print("Error: yt-dlp is required. Install with: pip install yt-dlp")
    sys.exit(1)

try:
    import config
except ImportError:
    print("Error: config.py not found. Please ensure it exists in the same directory.")
    sys.exit(1)


def parse_input_line(line):
    """Parse a line into URL and optional filename."""
    parts = line.strip().split(None, 1)
    if not parts:
        return None, None
    
    url = parts[0]
    filename = parts[1] if len(parts) > 1 else None
    return url, filename


def download_mp3(url, output_dir, filename=None):
    """Download audio from URL and convert to MP3."""
    try:
        # Configure yt-dlp options
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': False,
            'no_warnings': False,
        }
        
        if filename:
            # Use custom filename
            ydl_opts['outtmpl'] = os.path.join(output_dir, f'{filename}.%(ext)s')
        else:
            # Use video title as filename
            ydl_opts['outtmpl'] = os.path.join(output_dir, '%(title)s.%(ext)s')
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"\nFetching info for: {url}")
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'Unknown')
            
            if filename:
                print(f"Downloading: {title} -> {filename}.mp3")
            else:
                print(f"Downloading: {title}")
            
            ydl.download([url])
            
            print(f"✅ Successfully downloaded!\n")
            return True
            
    except Exception as e:
        print(f"❌ Error downloading {url}: {str(e)}\n")
        return False


def main():
    """Main function to handle multiline input and download MP3s."""
    # Get audio directory from config
    settings = config.get_defaults()
    audio_dir = settings.get('audio_dir')
    
    if not audio_dir:
        print("Error: audio_dir not configured in config.py")
        sys.exit(1)
    
    # Create directory if it doesn't exist
    os.makedirs(audio_dir, exist_ok=True)
    
    print("=" * 60)
    print("MP3 Downloader")
    print("=" * 60)
    print(f"Output directory: {audio_dir}")
    print()
    print("Enter URLs to download (one per line):")
    print("Format: URL [optional_filename]")
    print("Enter a blank line to start processing, or Ctrl+D/Ctrl+Z when done.")
    print("=" * 60)
    print()
    
    # Collect input lines
    downloads = []
    
    try:
        while True:
            try:
                line = input()
                
                # Blank line triggers processing
                if not line.strip():
                    if downloads:
                        break
                    else:
                        continue
                
                url, filename = parse_input_line(line)
                if url:
                    downloads.append((url, filename))
                    if filename:
                        print(f"  Queued: {url} -> {filename}.mp3")
                    else:
                        print(f"  Queued: {url}")
                        
            except EOFError:
                # Ctrl+D or Ctrl+Z pressed
                break
                
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        sys.exit(0)
    
    if not downloads:
        print("No URLs provided. Exiting.")
        return
    
    print()
    print("=" * 60)
    print(f"Starting download of {len(downloads)} item(s)...")
    print("=" * 60)
    
    # Process downloads
    successful = 0
    failed = 0
    
    for i, (url, filename) in enumerate(downloads, 1):
        print(f"\n[{i}/{len(downloads)}] Processing...")
        if download_mp3(url, audio_dir, filename):
            successful += 1
        else:
            failed += 1
    
    # Summary
    print("=" * 60)
    print("Download Summary")
    print("=" * 60)
    print(f"Total: {len(downloads)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Output directory: {audio_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
