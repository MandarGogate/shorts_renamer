# MP3 Downloader

A CLI tool to download audio from URLs and save as MP3 files to your configured `audio_dir`.

## Features

- Download audio from YouTube, SoundCloud, and other sites supported by yt-dlp
- Multiline input for batch downloads
- Optional custom filenames
- Automatic MP3 conversion at 192kbps
- Progress tracking and summary

## Prerequisites

```bash
pip install yt-dlp
```

Make sure `ffmpeg` is installed on your system for audio conversion:
- macOS: `brew install ffmpeg`
- Ubuntu/Debian: `sudo apt install ffmpeg`
- Windows: Download from https://ffmpeg.org/

## Usage

### Run the script:

```bash
python download_mp3.py
```

or

```bash
./download_mp3.py
```

### Input format:

Each line can contain:
```
URL [optional_filename]
```

### Examples:

```
https://www.youtube.com/watch?v=dQw4w9WgXcQ
https://www.youtube.com/watch?v=jNQXAC9IVRw MeAtZoo
https://soundcloud.com/artist/track MyFavoriteTrack
```

### Interactive usage:

1. Run the script
2. Enter URLs (one per line)
3. Press Enter on a blank line to start processing
4. Or press Ctrl+D (Unix/Mac) or Ctrl+Z (Windows) to finish

### Example session:

```
$ python download_mp3.py
============================================================
MP3 Downloader
============================================================
Output directory: /Users/mandargogate/Work/CC/TrendingMusic

Enter URLs to download (one per line):
Format: URL [optional_filename]
Enter a blank line to start processing, or Ctrl+D/Ctrl+Z when done.
============================================================

https://www.youtube.com/watch?v=dQw4w9WgXcQ
  Queued: https://www.youtube.com/watch?v=dQw4w9WgXcQ
https://www.youtube.com/watch?v=jNQXAC9IVRw DanceTrack
  Queued: https://www.youtube.com/watch?v=jNQXAC9IVRw -> DanceTrack.mp3

============================================================
Starting download of 2 item(s)...
============================================================

[1/2] Processing...

Fetching info for: https://www.youtube.com/watch?v=dQw4w9WgXcQ
Downloading: Rick Astley - Never Gonna Give You Up
✅ Successfully downloaded!

[2/2] Processing...

Fetching info for: https://www.youtube.com/watch?v=jNQXAC9IVRw
Downloading: Me at the zoo -> DanceTrack.mp3
✅ Successfully downloaded!

============================================================
Download Summary
============================================================
Total: 2
Successful: 2
Failed: 0
Output directory: /Users/mandargogate/Work/CC/TrendingMusic
============================================================
```

## Configuration

The output directory is read from `config.py`:
- Default: `audio_dir` setting in `DEFAULT_SETTINGS`
- All MP3 files are saved to this directory

## Notes

- Files are saved with the video title as filename (unless custom name provided)
- If a file with the same name exists, yt-dlp will handle naming conflicts
- Audio quality is set to 192kbps MP3
- The script uses the best available audio stream
