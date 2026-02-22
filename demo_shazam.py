#!/usr/bin/env python3
"""
Demo script for ShazamIO integration.
Shows how to identify songs and use cached results.
"""

import os
import sys
import asyncio

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shortssync import ShazamClient, is_shazam_available, get_song_name


def print_separator():
    print("=" * 60)


def demo_single_file(audio_path):
    """Demonstrate identifying a single file."""
    print_separator()
    print("Demo: Identify Single File")
    print_separator()
    
    if not os.path.exists(audio_path):
        print(f"❌ File not found: {audio_path}")
        return
    
    print(f"File: {audio_path}")
    print("Identifying...")
    
    client = ShazamClient()
    result = asyncio.run(client.identify(audio_path))
    
    if result:
        print(f"\n✅ Identified!")
        print(f"  Artist: {result.artist}")
        print(f"  Title: {result.title}")
        print(f"  Album: {result.album or 'N/A'}")
        print(f"  Genre: {result.genre or 'N/A'}")
        print(f"  Year: {result.year or 'N/A'}")
        print(f"  Shazam URL: {result.shazam_url}")
        print(f"\n  Filename: {result.get_filename_base()}")
    else:
        print("❌ Could not identify song")


def demo_caching(audio_path):
    """Demonstrate caching behavior."""
    print_separator()
    print("Demo: Caching")
    print_separator()
    
    if not os.path.exists(audio_path):
        print(f"❌ File not found: {audio_path}")
        return
    
    client = ShazamClient()
    import time
    
    # First call - hits API
    print("First call (API request)...")
    start = time.time()
    result1 = asyncio.run(client.identify(audio_path))
    elapsed1 = time.time() - start
    
    if result1:
        print(f"  ✅ {result1.artist} - {result1.title}")
        print(f"  ⏱️  Time: {elapsed1:.2f}s")
    
    # Second call - hits cache
    print("\nSecond call (cache)...")
    start = time.time()
    result2 = asyncio.run(client.identify(audio_path))
    elapsed2 = time.time() - start
    
    if result2:
        print(f"  ✅ {result2.artist} - {result2.title}")
        print(f"  ⏱️  Time: {elapsed2:.2f}s")
        if elapsed2 > 0:
            print(f"  💾 Cache speedup: {elapsed1/elapsed2:.1f}x faster")
        else:
            print(f"  💾 Cache speedup: instant!")


def demo_batch(files):
    """Demonstrate batch identification."""
    print_separator()
    print("Demo: Batch Identification")
    print_separator()
    
    client = ShazamClient()
    
    def progress(current, total, path):
        print(f"  [{current}/{total}] {os.path.basename(path)}")
    
    print(f"Processing {len(files)} files...")
    results = asyncio.run(client.identify_batch(files, progress_callback=progress))
    
    print("\nResults:")
    for path, result in results.items():
        if result:
            print(f"  ✅ {os.path.basename(path)}: {result.artist} - {result.title}")
        else:
            print(f"  ❌ {os.path.basename(path)}: Not identified")


def demo_cache_stats():
    """Show cache statistics."""
    print_separator()
    print("Demo: Cache Statistics")
    print_separator()
    
    client = ShazamClient()
    stats = client.get_cache_stats()
    
    print(f"Total cached: {stats['total_cached']}")
    print(f"Cache directory: {stats['cache_dir']}")
    
    if stats['entries']:
        print("\nCached songs:")
        for entry in stats['entries'][:10]:  # Show first 10
            print(f"  - {entry.get('artist', 'Unknown')} - {entry.get('title', 'Unknown')}")


def main():
    print_separator()
    print("ShazamIO Integration Demo")
    print_separator()
    
    # Check availability
    if not is_shazam_available():
        print("\n❌ ShazamIO not installed!")
        print("Install with: pip install shazamio")
        sys.exit(1)
    
    print("\n✅ ShazamIO is available")
    
    # Check for command line argument
    if len(sys.argv) > 1:
        audio_file = sys.argv[1]
        
        # Run demos
        demo_single_file(audio_file)
        demo_caching(audio_file)
        demo_cache_stats()
    else:
        print("\nUsage: python demo_shazam.py <audio_file>")
        print("\nExamples:")
        print("  python demo_shazam.py song.mp3")
        print("  python demo_shazam.py /path/to/audio/file.wav")
        
        # Still show cache stats
        demo_cache_stats()


if __name__ == "__main__":
    main()
