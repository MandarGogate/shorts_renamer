# Slowed Audio Guide

Short-form videos often use **slowed/reverb** versions of songs (0.5x - 0.8x speed). This guide explains how to handle them with ShortsSync.

## The Challenge

| Speed | Shazam | Chromaprint | Recommendation |
|-------|--------|-------------|----------------|
| 1.0x (normal) | ✅ Works | ✅ Works | Use as-is |
| 0.8x-0.9x | ⚠️ May work | ✅ Works | Try normal first |
| 0.5x-0.7x | ❌ Fails | ⚠️ May fail | Use slowed reference |

## Understanding the Technologies

### Shazam
- Designed for **normal-speed** audio identification
- Uses frequency/timing patterns that change with speed
- **Fails** with significant slowdowns (>20%)

### Chromaprint (Audio Fingerprinting)
- More robust than Shazam
- Handles slight variations (±10-15%)
- Uses **sliding window matching** for partial matches
- Still needs similar speeds for best results

## Solution: Multi-Speed Reference Library

### Step 1: Create Slowed Versions

Use the included helper script:

```bash
# Create 0.8x, 0.7x, and 0.5x versions of all your songs
python create_slowed_versions.py

# Or specify custom speeds
python create_slowed_versions.py --speeds 0.9 0.8 0.7 0.6 0.5
```

This creates:
```
09trending/
├── LNGSHOT - Moonwalkin'.mp3          # Original
├── slowed_versions/
│   ├── 0.8x/
│   │   └── LNGSHOT - Moonwalkin'_0.8x.mp3
│   ├── 0.7x/
│   │   └── LNGSHOT - Moonwalkin'_0.7x.mp3
│   └── 0.5x/
│       └── LNGSHOT - Moonwalkin'_0.5x.mp3
```

### Step 2: Match Videos by Speed

**For normal speed videos:**
```bash
python cli.py -a "/Users/me/Work/CC/09trending" --shazam
```

**For slowed videos (0.7x):**
```bash
python cli.py -a "/Users/me/Work/CC/09trending/slowed_versions/0.7x"
```

**For heavily slowed (0.5x):**
```bash
python cli.py -a "/Users/me/Work/CC/09trending/slowed_versions/0.5x"
```

### Step 3: Shazam for Proper Names

Even with slowed matching, use Shazam to get proper song titles:

```bash
# Use Shazam on original files for best identification
python cli.py -a "/Users/me/Work/CC/09trending" --shazam

# Then match slowed videos (Shazam names cached from above)
python cli.py -a "/Users/me/Work/CC/09trending/slowed_versions/0.7x"
```

## Workflow Examples

### Scenario 1: Mixed Speed Videos

You have videos with different speeds:

```bash
# 1. Identify all your reference songs with Shazam (one time setup)
python cli.py -a "/Users/me/Work/CC/09trending" --shazam

# 2. Create slowed versions (one time setup)
python create_slowed_versions.py --speeds 0.8 0.7 0.5

# 3. Sort videos by speed manually into folders:
#    - videos_normal/
#    - videos_0.8x/
#    - videos_0.7x/

# 4. Match each folder with appropriate reference
python cli.py -v "/Users/me/videos_normal" -a "/Users/me/Work/CC/09trending"
python cli.py -v "/Users/me/videos_0.8x" -a "/Users/me/Work/CC/09trending/slowed_versions/0.8x"
python cli.py -v "/Users/me/videos_0.7x" -a "/Users/me/Work/CC/09trending/slowed_versions/0.7x"
```

### Scenario 2: Unknown Speed

If you don't know the speed of your videos:

```bash
# Try normal speed first
python cli.py -v "/Users/me/videos" -a "/Users/me/Work/CC/09trending"

# Check results - if many "No Match", try slowed versions
# Move unmatched videos to separate folder and retry with slowed reference
```

### Scenario 3: Auto-Detect Speed

For advanced users, create a script to try multiple speeds:

```python
#!/usr/bin/env python3
import os
import subprocess

video_dir = "/Users/me/videos"
audio_dirs = [
    "/Users/me/Work/CC/09trending",                      # Normal
    "/Users/me/Work/CC/09trending/slowed_versions/0.8x", # 80%
    "/Users/me/Work/CC/09trending/slowed_versions/0.7x", # 70%
    "/Users/me/Work/CC/09trending/slowed_versions/0.5x", # 50%
]

for speed_dir in audio_dirs:
    print(f"\nTrying {speed_dir}...")
    result = subprocess.run([
        'python', 'cli.py',
        '-v', video_dir,
        '-a', speed_dir
    ])
```

## Tips for Slowed Audio

### 1. Use Shazam for Original Names

Even when matching slowed versions, Shazam can identify the original song:

```bash
# 1. Run with Shazam on original files
python cli.py -a "/Users/me/Work/CC/09trending" --shazam

# 2. This caches Shazam results
# 3. Now rename uses proper "Artist - Title" even for slowed matches
```

### 2. Adjust BER Threshold

For slowed audio, you might need a higher (more lenient) threshold:

```bash
# Default is 0.15, try 0.20 for slowed audio
python cli.py --threshold 0.20
```

### 3. Check Video Duration

Slowed videos are longer than original:
- Original: 30 seconds
- 0.5x slowed: 60 seconds

The sliding window matching handles this automatically!

## Manual FFmpeg Commands

If you prefer manual control:

```bash
# 0.7x speed (70% of original)
ffmpeg -i "input.mp3" -filter:a "atempo=0.7" "output_0.7x.mp3"

# 0.5x speed (50% of original) - requires chaining
ffmpeg -i "input.mp3" -filter:a "atempo=0.5,atempo=1.0" "output_0.5x.mp3"

# With reverb effect (common in slowed + reverb)
ffmpeg -i "input.mp3" -filter:a "atempo=0.7,aecho=0.8:0.9:1000:0.3" "output_slowed_reverb.mp3"
```

## Troubleshooting

### "No matches found" for slowed videos

**Cause:** Reference audio is normal speed, video is slowed

**Solution:**
```bash
# Create and use slowed reference
python create_slowed_versions.py --speeds 0.7
python cli.py -a "/path/to/audio/slowed_versions/0.7x"
```

### Shazam identifies wrong song

**Cause:** Slowed audio confuses Shazam

**Solution:** 
- Use Shazam only on original speed files
- For slowed matching, rely on Chromaprint only

### Poor quality slowed versions

**Cause:** MP3 compression artifacts

**Solution:**
```bash
# Use higher quality settings
python create_slowed_versions.py --quality high

# Or manually with ffmpeg
ffmpeg -i "input.mp3" -q:a 0 -filter:a "atempo=0.7" "output.mp3"
```

## Summary

| What You Want | What To Do |
|---------------|------------|
| Match normal videos | Use normal reference, `--shazam` enabled |
| Match slowed videos | Create slowed reference with `create_slowed_versions.py` |
| Get proper song names | Use `--shazam` on original files first |
| Handle mixed speeds | Create multiple reference folders, match separately |

**Remember:** The tool works best when reference and video have **similar speeds**!
