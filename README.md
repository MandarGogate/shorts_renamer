ShortsSync

1. Executive Summary

ShortsSync is a desktop automation tool designed to streamline the metadata management of short-form video content. It automates the file renaming process by performing audio fingerprinting and matching between a set of short video files (Query) and a set of full-length audio tracks (Reference).

The system utilizes Digital Signal Processing (DSP) techniques—specifically Chroma CENS features and Subsequence Dynamic Time Warping (DTW)—to identify short audio snippets within longer tracks, regardless of slight tempo variations or offset differences.

2. System Architecture

2.1 High-Level Stack

Language: Python 3.x

GUI Framework: tkinter (Standard Python GUI)

DSP Engine: librosa (Audio feature extraction and alignment)

Media Handling: moviepy (Video audio extraction), yt-dlp (Reference audio acquisition)

Math/Array Ops: numpy

2.2 Data Flow

Ingestion: User defines Source (Video) and Reference (Audio) directories.

Extraction: * Reference Audios are loaded and converted to Chroma CENS feature vectors.

Source Videos are processed via moviepy to extract audio streams to temporary WAV files, then converted to Chroma CENS vectors.

Matching (The Core Engine):

The system performs an N x M comparison matrix.

It utilizes Subsequence DTW to find the optimal alignment of the short video vector inside the long reference vector.

Renaming: * Upon a high-confidence match, a new filename is generated using the Reference Name + Viral Tags.

Collision handling ensures file integrity.

3. The Matching Engine (Deep Dive)

The application has evolved from simple Euclidean distance matching to a robust Subsequence DTW approach. This handles the "Needle in a Haystack" problem (finding a 20s clip inside a 3-minute song).

3.1 Feature Extraction: Chroma CENS

Instead of using MFCCs (which represent timbre and are sensitive to EQ/Mic quality), we use Chroma CENS (Chroma Energy Normalized Statistics).

Why CENS? CENS features map the audio to 12 pitch classes (C, C#, D...). They are normalized over a short window. This makes the matching robust to:

Dynamics/Volume: Loudness differences between the TikTok video and the studio MP3 don't break the match.

Timbre: A recording of a song played over speakers will still match the source file.

Implementation: librosa.feature.chroma_cens(y=y, sr=sr, hop_length=512)

3.2 Alignment: Subsequence DTW

We use Dynamic Time Warping (DTW) to calculate the distance cost between the two audio signals.

Standard DTW vs. Subsequence: Standard DTW tries to align the entire sequence X with the entire sequence Y. This fails when X is a short snippet of Y.

Our Implementation: We use librosa.sequence.dtw(subseq=True).

This algorithm allows the query sequence (Video) to start and end at any point within the reference sequence (Audio) without penalty for the skipped start/end sections of the reference.

Cost Calculation: * The algorithm returns a Cost Matrix $D$ and a Warping Path $W$.

We normalize the final cumulative cost by the path length to get a comparable score: normalized_cost = D[-1, -1] / path_len.

4. Modules & Logic

4.1 ShortsNamerApp Class

The main controller class managing UI state and business logic.

process_audio_matching (Threaded):

Iterates through video files.

Calls extract_chroma_cens for feature generation.

Performs the $O(N \times M)$ comparison.

Performance Note: Reference audios are indexed once (ref_data dictionary) to prevent re-computing features for every video.

generate_unique_name:

Inputs: Base audio name, User tags (Fixed & Random Pool).

Logic:

Cleans base name (underscores -> spaces).

Appends "Fixed Tags" (e.g., #shorts).

Selects $k$ random tags from the pool.

Collision Resolution: Checks os.path.exists. If a collision occurs, it retries with a different permutation of random tags. If all else fails, it appends a random integer ID.

4.2 The Downloader Module (_download_worker)

Integrates yt-dlp for acquiring reference material.

Configuration:

noplaylist: True: Prevents accidental bulk downloads of "Sound" pages.

postprocessors: Forces conversion to MP3 using FFmpeg.

Input Parsing: Supports URL | Custom Title syntax for pre-naming files.

5. Threading Model

To prevent the GUI (Tkinter main loop) from freezing during heavy DSP operations, all blocking I/O is offloaded.

Main Thread: UI Rendering, Button events.

Worker Thread 1: process_audio_matching (CPU Bound - numpy/librosa operations).

Worker Thread 2: _download_worker (Network Bound - yt-dlp operations).

Communication: Threads update self.status_var via self.root.after() to ensure thread-safe UI updates.

6. Dependencies & Requirements

System Requirements

FFmpeg: Must be installed and on the system PATH (required by moviepy and yt-dlp).

Python Libraries

numpy       # Matrix operations
librosa     # Audio feature extraction & DTW
moviepy     # Video decoding
yt_dlp      # YouTube/TikTok downloading
shutil      # High-level file operations
tkinter     # GUI (Standard lib)


7. Future Optimization Roadmap

GPU Acceleration: librosa runs on CPU. For batches >500 videos, moving tensor operations to PyTorch/TensorFlow could speed up CENS extraction.

Fingerprint Database: Currently, reference features are recalculated on every app launch. Storing these as serialized .npy files would make startup instant for large reference libraries.

Visual Matching: Implementing CV (OpenCV) to match video watermarks or visual signatures if audio is muted.