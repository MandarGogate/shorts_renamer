# ShazamIO Integration

ShortsSync now includes integration with **ShazamIO** - a free, unofficial Python library for Shazam song identification. This allows you to automatically identify songs in your reference audio library and use proper artist/title metadata instead of filenames.

## Features

- 🎵 **Automatic Song Identification**: Identify songs in your audio library
- 💾 **Smart Caching**: Shazam results are cached to avoid repeated API calls
- 🏷️ **Better Naming**: Use "Artist - Title" format instead of filenames
- 🔍 **Duplicate Detection**: Identify duplicate songs even with different filenames
- 🆓 **Free to Use**: No API key required

## Installation

```bash
pip install shazamio
```

Or install with all optional dependencies:

```bash
pip install -r requirements.txt
```

## Usage

### CLI Mode

Add the `--shazam` flag to enable Shazam identification:

```bash
python cli.py --shazam
```

Shazam will identify each reference audio file and use the proper artist/title for matching.

### GUI Mode

Check the "Use Shazam to identify songs" checkbox in the Configuration section.

### Web Interface

Enable Shazam in the web interface by checking the "Use Shazam" option when indexing reference audio.

### find_unique.py

Use `--shazam` to identify unique songs:

```bash
python find_unique.py /path/to/audio --shazam
```

This will show Shazam identifications for each file and use proper names when copying.

## How It Works

1. When indexing reference audio, each file is analyzed by Shazam
2. Shazam returns artist, title, album, genre, and other metadata
3. Results are cached in `.shazam_cache/` directory
4. The fingerprint is stored with the Shazam name as the key
5. When matching videos, the Shazam name is used for renaming

## Cache System

Shazam results are cached based on file content hash, so:
- ✅ Same file won't be analyzed twice
- ✅ Cache persists across runs
- ✅ Automatically invalidated if file changes

### Cache Location

Default: `.shazam_cache/`

### View Cache Stats

```python
from shortssync import ShazamClient

client = ShazamClient()
stats = client.get_cache_stats()
print(f"Cached songs: {stats['total_cached']}")
```

### Clear Cache

```python
from shortssync import ShazamClient

client = ShazamClient()
client.clear_cache()
```

## Example Output

```
📁 Video Source: /Users/me/Videos
🎵 Audio Reference: /Users/me/Music
🎵 Shazam Integration: Enabled

Indexing Reference Audio...
  [1/10] song1.mp3
    🎵 Shazam: The Weeknd - Blinding Lights
  [2/10] song2.mp3
    🎵 Shazam: Dua Lipa - Levitating
  ...

✅ Indexed 10 reference tracks
🎵 Shazam identified 10 tracks

Matching Videos...
  [1/5] video1.mp4
    ✅ Match: The Weeknd - Blinding Lights (BER: 0.023)
       → The Weeknd - Blinding Lights #shorts #fyp #viral.mp4
```

## API Usage

### Identify a Single Song

```python
import asyncio
from shortssync import ShazamClient

client = ShazamClient()
result = asyncio.run(client.identify('song.mp3'))

if result:
    print(f"Artist: {result.artist}")
    print(f"Title: {result.title}")
    print(f"Album: {result.album}")
    print(f"Filename: {result.get_filename_base()}")
```

### Batch Identification

```python
import asyncio
from shortssync import ShazamClient

client = ShazamClient()
files = ['song1.mp3', 'song2.mp3', 'song3.mp3']

results = asyncio.run(client.identify_batch(files))
for path, result in results.items():
    if result:
        print(f"{path}: {result.artist} - {result.title}")
```

### Synchronous API

```python
from shortssync import identify_song, get_song_name

# Get full result
result = identify_song('song.mp3')

# Or just get the name
name = get_song_name('song.mp3')
print(name)  # "The Weeknd - Blinding Lights"
```

## Limitations

- Requires internet connection for identification
- Unofficial API (could break if Shazam changes)
- Some songs may not be in Shazam's database
- Rate limits may apply for large batches

## Privacy

- Audio fingerprints are sent to Shazam's servers
- Only fingerprint data is sent, not the full audio file
- Cached locally after first identification
