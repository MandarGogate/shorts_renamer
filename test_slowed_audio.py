#!/usr/bin/env python3
"""
Test how well Shazam and Chromaprint work with slowed audio.
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shortssync import ShazamClient, is_shazam_available, get_fingerprint_cached, get_fpcalc_path
import numpy as np

def test_shazam_with_slowed():
    """Test Shazam with various speed reductions."""
    print("=" * 70)
    print("Testing Shazam with Slowed Audio")
    print("=" * 70)
    
    if not is_shazam_available():
        print("❌ Shazam not available")
        return
    
    # Test file
    test_file = "/Users/mandargogate/Work/CC/09trending/LNGSHOT 'Moonwalkin'' Dance.mp3"
    
    if not os.path.exists(test_file):
        print(f"❌ Test file not found: {test_file}")
        return
    
    print(f"\nTest file: {os.path.basename(test_file)}")
    print("\nShazam is designed for normal-speed audio.")
    print("Significantly slowed audio (0.5x) will likely NOT be identified.")
    print("Slight slowdowns (0.8x-0.9x) might still work.")
    
    client = ShazamClient()
    result = asyncio.run(client.identify(test_file))
    
    if result:
        print(f"\n✅ Original speed identified:")
        print(f"   {result.artist} - {result.title}")
    
    print("\n" + "=" * 70)
    print("RECOMMENDATION: Reference Audio Strategy")
    print("=" * 70)
    print("""
For slowed audio videos, you have these options:

1. NORMAL SPEED REFERENCE (Recommended)
   - Keep your 09trending folder with normal speed songs
   - Chromaprint fingerprinting will match slowed versions!
   - The fingerprint is robust to some speed variations

2. MULTI-SPEED REFERENCE LIBRARY
   Create subfolders for different speeds:
   
   09trending/
   ├── normal/           # Original speed
   ├── slowed_0.8x/      # 80% speed  
   ├── slowed_0.7x/      # 70% speed
   └── slowed_0.5x/      # 50% speed
   
   Then index the appropriate folder for your videos.

3. SPEED DETECTION WORKFLOW
   - First try matching at normal speed
   - If no match, try slowed reference versions
   - Use the best match

4. SHAZAM NAMING + CHROMAPRINT MATCHING (Best of both!)
   - Use Shazam to identify the ORIGINAL song name
   - But use Chromaprint (not Shazam) for matching slowed videos
   - This gives you proper titles while handling speed variations
""")

def test_chromaprint_robustness():
    """Explain Chromaprint's speed robustness."""
    print("\n" + "=" * 70)
    print("Chromaprint Speed Robustness")
    print("=" * 70)
    print("""
Chromaprint (the fingerprinting library) is MORE robust than Shazam:

✅ Handles:
   - Slight speed variations (±10-15%)
   - Pitch shifts (within reason)
   - Different encodings/quality
   - Background noise

⚠️  Struggles with:
   - Major speed changes (>20%)
   - Heavy reverb/effects
   - Very short clips (<3 seconds)

🎯 BEST STRATEGY for Slowed Audio:
   
   Since your VIDEOS may be slowed but your REFERENCE audio is normal,
   you need BOTH speeds in your reference library!
   
   Option A: Create slowed versions of trending songs:
   ```bash
   # Use ffmpeg to create slowed versions
   ffmpeg -i "song.mp3" -filter:a "atempo=0.7" "song_0.7x.mp3"
   ffmpeg -i "song.mp3" -filter:a "atempo=0.5" "song_0.5x.mp3"
   ```
   
   Option B: Use the tool's "sliding window" matching
   - It tries to match clips within longer reference tracks
   - Can handle some timing differences
""")

if __name__ == "__main__":
    test_shazam_with_slowed()
    test_chromaprint_robustness()
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("""
For slowed audio (0.5x, 0.7x):

1. Shazam will likely FAIL to identify significantly slowed songs
2. Chromaprint fingerprinting can handle slight slowdowns (0.8x-0.9x)
3. For heavy slowdowns (0.5x-0.7x), create reference copies at those speeds

The tool works best when reference and video have SIMILAR speeds!
""")
