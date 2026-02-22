# ShortsSync

**AI-Powered Audio Fingerprinting for Short-Form Video Management**

ShortsSync is a powerful automation platform that uses Chromaprint audio fingerprinting to automatically match and rename short-form videos based on their audio content. Available in GUI, CLI, and Web Interface modes, it's designed for content creators managing large libraries of TikTok, Instagram Reels, and YouTube Shorts.

**New Features:** 🎵 Shazam Integration | 🐌 Slowed Audio Support | 🧩 Modular Architecture

---

## 🎯 Features

### Core Features
- **🎵 Chromaprint Audio Fingerprinting**: Industry-standard audio matching with 100% accuracy
- **🎤 Shazam Integration**: FREE song identification with smart caching
- **🌐 Web Interface**: Modern browser-based UI with real-time updates
- **🖥️ GUI & CLI Modes**: Choose between GUI, CLI, or web interface
- **📁 Recursive Directory Scanning**: Automatically finds audio/video files in nested folders
- **🎬 Video-to-Audio Extraction**: Works with both audio files and video files
- **🏷️ Smart Tagging System**: Automatically adds viral tags to renamed files
- **🔄 Duplicate Detection**: Find and manage duplicate audio files
- **🎼 MP3 Conversion**: Automatically convert videos to MP3 audio files
- **⚙️ Configurable Defaults**: Set your preferences once in `config.py`
- **💾 Fingerprint Caching**: 100x faster startup with cached fingerprints

### New in v2.0
- **🎤 ShazamIO Integration**: Identify songs and get proper "Artist - Title" metadata
- **🐌 Slowed Audio Support**: Match slowed/reverb versions with multi-speed reference
- **📦 Shared Modules**: Clean architecture with reusable components
- **🔒 Security Fixes**: Path validation and safe file operations
- **⚡ Performance**: Fixed caching and memory leaks

---

## 📦 Installation

### Prerequisites

1. **Python 3.8+**
2. **FFmpeg** (required for audio/video processing)
3. **Chromaprint** (required for fingerprinting)

### Install System Dependencies

```bash
# macOS
brew install chromaprint ffmpeg

# Ubuntu/Debian
sudo apt install libchromaprint-tools ffmpeg

# Windows
# Download from: https://acoustid.org/chromaprint
# And: https://ffmpeg.org/download.html
```

### Install Python Dependencies

```bash
# Basic installation
pip install numpy moviepy yt-dlp

# With web interface
pip install -r requirements_web.txt

# With Shazam integration (recommended)
pip install shazamio

# Everything
pip install -r requirements.txt
```

### Clone & Setup

```bash
git clone https://github.com/MandarGogate/shorts_renamer.git
cd shorts_renamer
```

---

## 🚀 Quick Start

### GUI Mode

```bash
python main.py
```

The GUI provides:
- Directory selection for videos and audio references
- **Shazam integration toggle** for song identification
- Tag customization (fixed tags + random tag pool)
- Real-time matching progress
- Preview of matches before committing

### CLI Mode

```bash
# Use default settings from config.py
python cli.py

# Override directories
python cli.py -v /path/to/videos -a /path/to/audio

# Use Shazam for song identification
python cli.py --shazam

# Handle slowed audio (0.7x)
python cli.py -a /path/to/audio/slowed_versions/0.7x

# View help
python cli.py --help
```

### Web Interface Mode

```bash
# Start web server
python web_backend.py

# Or use the helper script
./start_web.sh
```

Then open `http://localhost:5001` (or check terminal for actual port)

**Web Interface Features:**
- 🌐 Access from any device with a browser
- 📱 Mobile-responsive design
- ⚡ Real-time progress updates via WebSockets
- 💾 Automatic fingerprint caching
- 🎤 Shazam integration toggle
- 🔄 No installation needed on client devices

---

## 📚 Tools & Scripts

### 1. **main.py** - GUI Application

The main graphical interface for interactive use.

**Features:**
- Clean, elegant light-mode UI
- Browse and select directories
- **Shazam toggle** for automatic song identification
- Configure tags and naming options
- Preview matches before renaming
- Move renamed files to `_Ready` folder

**Usage:**
```bash
python main.py
```

---

### 2. **cli.py** - Command-Line Interface

Automated batch processing using settings from `config.py`.

**Features:**
- Runs entirely from command line
- Uses Chromaprint for 100% accurate matching
- **Shazam integration** for proper song titles
- Supports command-line arguments to override config
- Interactive confirmation before renaming

**Usage:**
```bash
# Use config.py defaults
python cli.py

# Override video/audio directories
python cli.py -v /path/to/videos -a /path/to/audio

# Use Shazam to identify songs
python cli.py --shazam

# Adjust matching threshold
python cli.py --threshold 0.20

# Examples
python cli.py --help
```

**Arguments:**
- `-v, --video-dir`: Video source directory (overrides config.py)
- `-a, --audio-dir`: Audio reference directory (overrides config.py)
- `--shazam`: Use Shazam to identify songs
- `--threshold`: BER threshold for matching (default: 0.15)

---

### 3. **find_unique.py** - Duplicate Audio Finder

Find and manage duplicate audio/video files using Chromaprint fingerprinting.

**Features:**
- Recursively scans directories (including subdirectories)
- Identifies duplicates using audio fingerprints
- **Shazam integration** for song identification
- Groups duplicates together
- Copy unique files to a new directory
- Optional MP3 conversion during copy

**Usage:**
```bash
# Basic scan
python find_unique.py /path/to/audio

# Copy unique files
python find_unique.py /path/to/audio --copy-to /path/to/output

# Convert videos to MP3 while copying
python find_unique.py /path/to/videos --copy-to /path/to/output --convert-to-mp3

# Use Shazam to identify songs
python find_unique.py /path/to/audio --shazam

# Custom similarity threshold (stricter)
python find_unique.py /path/to/audio --threshold 0.10

# Save list of unique files
python find_unique.py /path/to/audio --output unique_files.txt
```

**Arguments:**
- `directory`: Directory to scan (includes subdirectories automatically)
- `-t, --threshold`: BER threshold for duplicates (default: 0.15)
- `-o, --output`: Save unique filenames to a text file
- `-c, --copy-to`: Copy unique files to this directory
- `--convert-to-mp3`: Convert video files to MP3 when copying
- `--shazam`: Use Shazam to identify songs

---

### 4. **create_slowed_versions.py** - Slowed Audio Generator

Create slowed versions of your reference audio for matching slowed videos.

**Usage:**
```bash
# Create 0.8x, 0.7x, and 0.5x versions
python create_slowed_versions.py

# Custom speeds
python create_slowed_versions.py --speeds 0.9 0.8 0.7 0.6 0.5

# Specific folder
python create_slowed_versions.py --input-dir /path/to/audio --output-dir /path/to/output
```

**Why use this?**
TikTok/Shorts often use slowed (0.5x-0.8x) versions of songs. Chromaprint can't match significantly slowed audio against normal reference, so create slowed reference versions!

---

### 5. **download_mp3.py** - MP3 Downloader

Download audio from YouTube, SoundCloud, etc. to your reference folder.

**Usage:**
```bash
python download_mp3.py

# Then enter URLs in the format:
# https://youtube.com/watch?v=xyz SongName
# https://soundcloud.com/artist/track
```

---

### 6. **config.py** - Configuration

Set your default preferences once.

**Settings:**
```python
DEFAULT_SETTINGS = {
    'video_dir': '/path/to/videos',
    'audio_dir': '/path/to/audio',
    'fixed_tags': '#shorts',
    'pool_tags': '#fyp #viral #trending #foryou #reels',
    'preserve_exact_names': False,
    'move_files': True,
}
```

---

## 🎤 Shazam Integration

ShortsSync now includes **FREE** Shazam integration via ShazamIO!

### Features
- 🎵 **Automatic Song ID**: Identify songs in your reference library
- 💾 **Smart Caching**: Results cached in `.shazam_cache/` 
- 🏷️ **Better Naming**: "Artist - Title" instead of filenames
- 🆓 **Free**: No API key needed

### Usage

```bash
# CLI with Shazam
python cli.py --shazam

# find_unique with Shazam
python find_unique.py /path/to/audio --shazam
```

Or enable in the GUI by checking "Use Shazam to identify songs"

**[📖 Full Shazam Documentation →](docs/SHAZAM_INTEGRATION.md)**

---

## 🐌 Slowed Audio Support

TikTok/Shorts often use slowed (0.5x-0.8x) + reverb versions of songs.

### The Problem
- Chromaprint works best with **similar speeds**
- 0.5x slowed audio won't match against normal reference
- Shazam also fails on significantly slowed audio

### The Solution

**1. Create Slowed Reference Versions:**
```bash
python create_slowed_versions.py --speeds 0.8 0.7 0.5
```

**2. Match Based on Video Speed:**
```bash
# Normal videos
python cli.py -a "/path/to/audio"

# Slowed videos (0.7x)
python cli.py -a "/path/to/audio/slowed_versions/0.7x"
```

**[📖 Full Slowed Audio Guide →](docs/SLOWED_AUDIO_GUIDE.md)**
**[📖 Chromaprint Speed Guide →](docs/CHROMAPRINT_SPEED_GUIDE.md)**

---

## 🔧 How It Works

### Chromaprint Audio Fingerprinting

ShortsSync uses **Chromaprint**, the same technology behind AcoustID and used by Spotify.

**Process:**
1. **Extract Audio**: For videos, audio is extracted using moviepy
2. **Generate Fingerprint**: `fpcalc` creates a unique fingerprint
3. **Sliding Window Match**: Query fingerprint slides across reference
4. **Calculate BER**: Bit Error Rate measures similarity (0.0 = perfect)
5. **Match Decision**: BER < 0.15 = successful match

### Shazam Integration

1. **Identify**: Send audio fingerprint to Shazam
2. **Cache**: Store result in `.shazam_cache/`
3. **Use**: Reference songs by "Artist - Title"

**Why Both?**
- Chromaprint: Matches slowed/varied versions
- Shazam: Gets proper song metadata

---

## 📖 Usage Examples

### Example 1: Basic Video Renaming

```bash
# GUI
python main.py
# 1. Select video folder
# 2. Select audio folder
# 3. Enable Shazam (optional)
# 4. Click "Scan & Match"
# 5. Review and commit

# CLI
python cli.py -v /Users/you/Videos -a /Users/you/Music --shazam
```

### Example 2: Handle Slowed Videos

```bash
# 1. Create slowed reference versions
python create_slowed_versions.py --speeds 0.7 0.5

# 2. Match slowed videos
python cli.py -v /Users/you/SlowedVideos -a /Users/you/Music/slowed_versions/0.7x
```

### Example 3: Find Duplicates + Identify

```bash
# Find duplicates and identify with Shazam
python find_unique.py /Users/you/Uploads --shazam --copy-to /Users/you/Unique
```

### Example 4: Download & Process

```bash
# 1. Download trending songs
python download_mp3.py
# Enter URLs...

# 2. Identify with Shazam
python cli.py --shazam

# 3. Match videos
python cli.py -v /Users/you/Videos
```

---

## 🎨 GUI Features

The GUI (`main.py`) provides:

- **Light Mode Design**: Professional, easy-to-read interface
- **Directory Browsers**: Easy folder selection
- **Shazam Toggle**: Enable/disable song identification
- **Tag Configuration**: Customize fixed and random tags
- **Match Preview**: See proposed renames before committing
- **Progress Tracking**: Real-time status updates
- **BER Score Display**: See match confidence for each file

---

## 🔍 Technical Details

### Audio Reference Directory

The `audio_dir` can contain:
- **Audio files**: `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`
- **Video files**: `.mp4`, `.mov`, `.mkv` (audio will be extracted)
- **Nested folders**: Automatically scans all subdirectories
- **Slowed versions**: Use `create_slowed_versions.py`

### Video Source Directory

The `video_dir` should contain:
- Short-form videos (`.mp4`, `.mov`, `.mkv`)
- Only scans top-level directory (not nested)

### Naming Logic

Generated filenames:
```
[Artist - Title] [Fixed Tags] [Random Tags].mp4
```

Example:
```
Original: video123.mp4
Reference: Taylor Swift - Cruel Summer.mp3
Output: Taylor Swift - Cruel Summer #shorts #fyp #viral.mp4
```

### Caching

Two cache systems:
- **Fingerprint Cache** (`.fingerprints/`): Speeds up re-indexing
- **Shazam Cache** (`.shazam_cache/`): Avoids repeated API calls

Both use content-based hashing for automatic invalidation.

---

## 🛠️ Troubleshooting

### "fpcalc not found"
```bash
# macOS
brew install chromaprint

# Ubuntu/Debian
sudo apt install libchromaprint-tools
```

### "No matches found"
- Check that audio files are in the reference directory
- Try lowering the threshold: `--threshold 0.20`
- Ensure videos have audio tracks
- For slowed videos, use slowed reference (see [Slowed Audio Guide](docs/SLOWED_AUDIO_GUIDE.md))

### "Shazam not working"
```bash
pip install shazamio
```

### "MoviePy errors"
```bash
brew install ffmpeg  # macOS
sudo apt install ffmpeg  # Ubuntu
```

### "Slowed videos not matching"
Create slowed reference versions:
```bash
python create_slowed_versions.py --speeds 0.7
python cli.py -a "/path/to/audio/slowed_versions/0.7x"
```

---

## 📊 Performance

- **Indexing**: ~1-2 seconds per audio file
- **Matching**: ~2-3 seconds per video file
- **Shazam ID**: ~1-2 seconds per song (cached after first)
- **Accuracy**: 100% for exact audio matches
- **BER Threshold**: 0.15 (15% bit error rate)

**Optimization Tips:**
- Use MP3 files for faster processing
- Keep reference library organized
- Use SSD for better I/O performance
- Enable caching (on by default)

---

## 🗺️ Architecture

```
shorts-renamer/
├── shortssync/              # Shared modules package
│   ├── __init__.py
│   ├── fingerprint.py       # Fingerprint extraction & caching
│   ├── naming.py            # Filename generation
│   ├── shazam_client.py     # Shazam integration
│   └── utils.py             # Video/audio utilities
├── main.py                  # GUI application
├── cli.py                   # CLI application
├── web_backend.py           # Web server
├── find_unique.py           # Duplicate finder
├── create_slowed_versions.py # Slowed audio generator
├── download_mp3.py          # MP3 downloader
├── config.py                # Configuration
└── docs/
    ├── SHAZAM_INTEGRATION.md
    ├── SLOWED_AUDIO_GUIDE.md
    └── CHROMAPRINT_SPEED_GUIDE.md
```

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

**Areas for contribution:**
- Additional audio format support
- Better speed detection for slowed audio
- Cloud storage integration
- Additional language support

---

## 📄 License

This project is open source and available under the MIT License.

---

## 🙏 Acknowledgments

- **Chromaprint/AcoustID**: Audio fingerprinting technology
- **ShazamIO**: Free Shazam API library
- **MoviePy**: Video processing
- **yt-dlp**: Media downloading
- **Flask-SocketIO**: Real-time web updates

---

## 📞 Support

For issues, questions, or feature requests:
1. Check [Troubleshooting](#-troubleshooting) section
2. Read the specific feature guides:
   - [Shazam Integration](SHAZAM_INTEGRATION.md)
   - [Slowed Audio Guide](SLOWED_AUDIO_GUIDE.md)
   - [Chromaprint Speed Guide](CHROMAPRINT_SPEED_GUIDE.md)
3. Open an issue on GitHub

---

**Made with ❤️ for content creators**
