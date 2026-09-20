# ShortsSync Web Interface

**Browser-based audio fingerprinting and video management**

The web interface provides full ShortsSync functionality through a modern, responsive web application. Access from any device with a browser - no installation required on client devices.

---

## 🌐 Features

### Core Capabilities
- ✅ **Browser-based UI** - Access from desktop, tablet, or mobile
- ✅ **Real-time Updates** - WebSocket-powered live progress tracking
- ✅ **Remote Access** - Run server on one machine, access from anywhere on network
- ✅ **No Client Installation** - Just open browser and go
- ✅ **Responsive Design** - Works on all screen sizes
- ✅ **Fingerprint Caching** - Instant startup with cached fingerprints

### Workflow
1. **Configure** - Set directories and tagging preferences
2. **Index** - Build fingerprint database from reference audio
3. **Match** - Find audio matches for your videos
4. **Review** - See all matches with confidence scores
5. **Rename** - Commit changes with one click

---

## 🚀 Quick Start

### Prerequisites

1. **Python 3.8+**
2. **FFmpeg** (for audio/video processing)
   ```bash
   # macOS
   brew install ffmpeg

   # Ubuntu/Debian
   sudo apt install ffmpeg
   ```

3. **Chromaprint** (for audio fingerprinting)
   ```bash
   # macOS
   brew install chromaprint

   # Ubuntu/Debian
   sudo apt install libchromaprint-tools
   ```

### Installation

1. **Clone repository** (if not already done)
   ```bash
   git clone https://github.com/MandarGogate/shorts_renamer.git
   cd shorts_renamer
   ```

2. **Create a virtual environment and install dependencies**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install -r requirements_web.txt
   ```

3. **Start the server**
   ```bash
   # Using startup script (recommended)
   ./start_web.sh

   # Or manually
   python web_backend.py
   ```

4. **Open browser**

   The server will automatically find an available port (starting from 5001).
   Check the terminal output for the actual URL, e.g.:
   ```
   Starting server on http://localhost:5001
   Web UI: http://localhost:5001
   ```

   **Note:** The server automatically selects an available port to avoid conflicts with AirPlay (port 5000) and other services.

---

## 📖 Usage Guide

### Step 1: Configuration

Set your directories and preferences in the web interface:

- **Video Source Directory**: Folder with videos to rename (e.g., `/Users/you/ToEdit`)
- **Reference Audio Directory**: Folder with reference audio files (e.g., `/Users/you/Music`)
- **Fixed Tags**: Tags always added (e.g., `#shorts #viral`)
- **Random Tag Pool**: Tags randomly selected (e.g., `#fyp #trending #foryou`)
- **Options**:
  - Move renamed files to `_Ready` folder
  - Preserve exact reference names (no tags)

### Step 2: Index Reference Audio

Click **"Start Indexing"** to build fingerprint database.

**What happens:**
- Recursively scans reference audio directory
- Generates Chromaprint fingerprints
- Caches fingerprints to `.fingerprints/` for instant reuse
- Handles both audio files (MP3, WAV, etc.) and video files

**Progress:**
- Real-time status updates
- Live progress bar
- Activity log shows each file processed

### Step 3: Match Videos

Click **"Start Matching"** to find audio matches.

**What happens:**
- Scans video source directory (non-recursive)
- Extracts audio from each video
- Compares against reference fingerprints using sliding window
- Finds best match based on BER (Bit Error Rate)
- Generates unique filenames with tags

**Results:**
- Shows all matches with confidence scores
- Color-coded confidence levels:
  - 🟢 Green (90-100%): High confidence match
  - 🟡 Yellow (70-90%): Medium confidence match
  - 🔴 Red (<70%): Low confidence match

### Step 4: Review & Rename

Review matches in the results panel:
- See original filename → new filename
- Check matched reference audio
- View confidence score and BER

Click **"Commit Rename"** to apply changes.

**Safety:**
- Confirmation dialog before renaming
- Option to move to `_Ready` folder
- Activity log tracks all operations

---

## 🔧 API Reference

The backend exposes a RESTful API for integration.

### Health Check
```
GET /api/health
```
Returns server status and dependency check.

### Configuration
```
GET /api/config
POST /api/config
```
Get/update configuration.

### Reference Audio
```
POST /api/reference/index
```
Start indexing reference audio.
```json
{
  "audio_dir": "/path/to/audio"
}
```

```
GET /api/reference/list
```
Get list of indexed files.

### Video Matching
```
POST /api/videos/match
```
Start matching videos.
```json
{
  "video_dir": "/path/to/videos",
  "fixed_tags": "#shorts",
  "pool_tags": "#fyp #viral",
  "preserve_exact_names": false,
  "threshold": 0.15
}
```

```
GET /api/matches
```
Get match results.

### Renaming
```
POST /api/videos/rename
```
Commit renames.
```json
{
  "video_dir": "/path/to/videos",
  "move_files": false
}
```

### Status
```
GET /api/status
```
Get current processing status.

---

## 🌐 WebSocket Events

Real-time updates via Socket.IO.

### Connect
```javascript
socket.on('connect', () => {
  console.log('Connected to ShortsSync');
});
```

### Status Updates
```javascript
socket.on('status_update', (data) => {
  // data = { is_processing, current_task, progress, total, message }
});
```

---

## 🔐 Remote access

The server binds to `127.0.0.1` by default. Local use does not require a token. Do not expose it on a network without configuring authentication and filesystem limits.

To access it from another device on your LAN:

```bash
SHORTSSYNC_HOST=0.0.0.0 \
SHORTSSYNC_TOKEN=$(openssl rand -hex 16) \
SHORTSSYNC_ROOTS="/Users/me/Movies/Shorts:/Users/me/Music/Shorts" \
SHORTSSYNC_CORS_ORIGINS="http://192.168.1.50:5001" \
./start_web.sh
```

Use the Mac's LAN address in the browser. The token can be supplied in the UI with `?token=<secret>` or through the documented auth headers. `SHORTSSYNC_ROOTS` is an `os.pathsep`-separated allow-list, so use `:` on macOS and Linux. A non-loopback host without `SHORTSSYNC_TOKEN` is refused.

---

## 🚀 Deployment

### Docker Deployment

Create `Dockerfile`:
```dockerfile
FROM python:3.10-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    libchromaprint-tools \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements_web.txt .
RUN pip install --no-cache-dir -r requirements_web.txt

COPY . .

EXPOSE 5001
CMD ["python", "web_backend.py"]
```

Build and run:
```bash
docker build -t shortssync-web .
docker run -p 5001:5001 -v /path/to/data:/data shortssync-web
```

### Cloud Deployment (AWS, GCP, Azure)

The web backend can run on:
- AWS EC2, ECS, Lambda (with API Gateway)
- Google Cloud Run, App Engine, Compute Engine
- Azure App Service, Container Instances

**Environment Variables:**
```bash
export FLASK_ENV=production
export FLASK_SECRET_KEY=your-secret-key
export MAX_UPLOAD_SIZE=500000000  # 500MB
```

---

## 🛠️ Development

### Project Structure

```
shorts_renamer/
├── web_backend.py          # Flask API server
├── web_frontend/
│   ├── index.html          # Main UI
│   ├── styles.css          # Styling
│   └── app.js              # Frontend logic
├── requirements_web.txt    # Python dependencies
├── start_web.sh            # Startup script
├── .fingerprints/          # Cached fingerprints
└── uploads/                # Temporary uploads
```

### Customization

**Change starting port:**
```python
# web_backend.py, in main block
port = find_available_port(start_port=8080)  # Change start_port value
```

The server automatically finds an available port, starting from the specified port.

**Max upload size:**
```python
# web_backend.py, line ~40
app.config['MAX_CONTENT_LENGTH'] = 1000 * 1024 * 1024  # 1GB
```

**Theme colors:**
```css
/* web_frontend/styles.css */
:root {
    --primary: #0066cc;
    --success: #28a745;
    /* ... */
}
```

---

## 📊 Performance

### Benchmarks

**Indexing:**
- ~1-2 seconds per audio file (first time)
- ~0.01 seconds per file (with cache)

**Matching:**
- ~2-3 seconds per video file
- Scales linearly with video count

**Caching:**
- 100x faster startup with fingerprint cache
- Cache invalidation on file modification

### Optimization Tips

1. **Use SSD** for better I/O performance
2. **Cache fingerprints** (automatic in web version)
3. **Use MP3 files** for faster processing
4. **Close other apps** during heavy processing
5. **Upgrade to SSD/NVMe** if using HDD

---

## 🐛 Troubleshooting

### "fpcalc not found"

Install Chromaprint:
```bash
# macOS
brew install chromaprint

# Ubuntu/Debian
sudo apt install libchromaprint-tools
```

### "Connection error" in browser

1. Check if server is running (use the port shown in terminal output):
   ```bash
   curl http://localhost:5001/api/health
   ```

2. Check firewall settings

3. Verify the port in the terminal output where you started the server

### "No matches found"

1. Verify reference audio directory is correct
2. Check that videos have audio tracks
3. Try lowering threshold (default: 0.15)
4. Ensure audio quality is reasonable

### "Processing stuck"

1. Check server logs in terminal
2. Restart server
3. Clear browser cache
4. Check file permissions

---

## 🔮 Roadmap

### Near-term (v1.1)
- [ ] User authentication
- [ ] Multi-user support
- [ ] File upload via browser
- [ ] Download results as ZIP
- [ ] Dark mode

### Medium-term (v1.2)
- [ ] Docker Compose setup
- [ ] Cloud storage integration
- [ ] Batch job scheduling
- [ ] Email notifications

### Long-term (v2.0)
- [ ] Mobile apps (iOS/Android)
- [ ] GPU acceleration
- [ ] Multi-language support
- [ ] Advanced analytics

---

## 📝 License

MIT License - See LICENSE file for details

---

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing`)
5. Open Pull Request

---

## 📞 Support

- **Issues**: https://github.com/MandarGogate/shorts_renamer/issues
- **Discussions**: https://github.com/MandarGogate/shorts_renamer/discussions
- **Email**: support@shortssync.com (if available)

---

**Happy matching! 🎵🎬**
