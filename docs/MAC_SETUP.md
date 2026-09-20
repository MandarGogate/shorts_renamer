# macOS setup

These steps assume a new Mac and a fresh checkout. The commands work on both Apple silicon and Intel Macs. Homebrew chooses the correct install paths for the machine.

## 1. Install system tools

Install Apple's command-line tools if macOS asks for them:

```bash
xcode-select --install
```

Install [Homebrew](https://brew.sh/) if it is not already installed, then install Python and the media tools:

```bash
brew install python ffmpeg chromaprint
```

ShortsSync uses:

- `python` for the application and tests
- `ffmpeg` to extract and convert audio
- `fpcalc` from `chromaprint` to create fingerprints

## 2. Clone the repository and create an isolated environment

```bash
git clone https://github.com/MandarGogate/shorts_renamer.git
cd shorts_renamer

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Activate the environment again whenever you open a new terminal:

```bash
cd /path/to/shorts_renamer
source .venv/bin/activate
```

The environment is local to this checkout and is ignored by Git.

## 3. Verify the install

Run these checks from the repository root with `.venv` active:

```bash
python --version
ffmpeg -version | head -1
fpcalc -version
python -m pytest -q
```

The test suite can skip media cases when a fixture or optional tool is unavailable. A missing `fpcalc` command means Chromaprint was not installed correctly. Run `brew install chromaprint` and open a new terminal if needed.

The desktop GUI also needs Tk support:

```bash
python -c "import tkinter; print('Tk is available')"
```

If that import fails, install a Python build with Tk support, such as the installer from [python.org](https://www.python.org/downloads/macos/), then recreate the virtual environment with that Python.

## 4. Set your folders

Use either local config or environment variables. Local config is easier for a permanent setup:

```bash
cp config.example.py config_local.py
nano config_local.py
```

Set `video_dir` to the folder containing videos to rename and `audio_dir` to the reference audio folder. `config_local.py` is ignored by Git, so personal paths stay on the Mac.

For a temporary setup instead:

```bash
export SHORTSSYNC_VIDEO_DIR="$HOME/Movies/Shorts"
export SHORTSSYNC_AUDIO_DIR="$HOME/Music/Shorts"
```

Create the folders first if they do not exist. macOS may ask Terminal or your Python application for permission to access folders under Desktop, Documents, or external drives. Approve that access in System Settings > Privacy & Security.

## 5. Start safely

Preview a batch before allowing renames:

```bash
python cli.py -v "$HOME/Movies/Shorts" \
  -a "$HOME/Music/Shorts" \
  --dry-run
```

Other entry points:

```bash
# Identify directly with Shazam, without indexing the reference library
python cli.py --shazam-only -v "$HOME/Movies/Shorts" --dry-run

# Desktop app
python main.py

# Web app
./start_web.sh
```

The web app listens on `127.0.0.1` and normally uses port `5001`. Open the URL printed in the terminal. Keep the server on localhost unless you configure `SHORTSSYNC_TOKEN`, `SHORTSSYNC_ROOTS`, and the allowed CORS origins. See the web security section in the main README before exposing it to another device.

## Updating later

```bash
cd /path/to/shorts_renamer
source .venv/bin/activate
git pull --ff-only
python -m pip install -r requirements.txt
```

Do not commit `config_local.py`, media files, caches, logs, or `rename_history.jsonl`.
