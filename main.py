import os
import sys
import threading
import random
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import shutil
import subprocess

# Third-party dependencies
try:
    import numpy as np
except ImportError:
    messagebox.showerror("Missing Dependency", "Numpy is required.\npip install numpy")
    sys.exit(1)

try:
    from moviepy.editor import VideoFileClip
except ImportError:
    try:
        from moviepy import VideoFileClip
    except ImportError:
        messagebox.showerror("Missing Dependency", "MoviePy is required.\npip install moviepy")
        sys.exit(1)

try:
    import yt_dlp
except ImportError:
    messagebox.showerror("Missing Dependency", "yt-dlp is required.\npip install yt-dlp")
    sys.exit(1)

# Import config
try:
    import config
except ImportError:
    config = None

# --- ELEGANT LIGHT THEME ---
THEME = {
    "bg": "#ffffff",
    "card_bg": "#f8f9fa",
    "fg": "#1a1a1a",
    "fg_sub": "#6c757d",
    "accent": "#0066cc",
    "accent_hover": "#0052a3",
    "success": "#28a745",
    "success_hover": "#218838",
    "border": "#dee2e6",
    "input_bg": "#ffffff",
    "input_border": "#ced4da",
}

class ShortsSyncApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ShortsSync")
        self.root.geometry("1000x750")
        self.root.configure(bg=THEME["bg"])
        
        self.video_dir = tk.StringVar()
        self.audio_dir = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")
        self.move_files_var = tk.BooleanVar(value=False)
        self.preserve_exact_names = tk.BooleanVar(value=False)
        self.matches = []

        self._setup_ui()
        self._apply_defaults()
        self._check_dependencies()

    def _check_dependencies(self):
        fpcalc = shutil.which("fpcalc")
        if not fpcalc and os.path.exists("/opt/homebrew/bin/fpcalc"):
            fpcalc = "/opt/homebrew/bin/fpcalc"
        if not fpcalc:
            messagebox.showwarning("Dependency Missing", "Chromaprint 'fpcalc' is missing.\nRun: brew install chromaprint")

    def _apply_defaults(self):
        """Load defaults from config.py if available."""
        if config is None:
            return
        
        defaults = config.get_defaults()
        
        if defaults.get('video_dir'):
            self.video_dir.set(defaults['video_dir'])
        if defaults.get('audio_dir'):
            self.audio_dir.set(defaults['audio_dir'])
        if defaults.get('fixed_tags'):
            self.fixed_tags_entry.delete(0, tk.END)
            self.fixed_tags_entry.insert(0, defaults['fixed_tags'])
        if defaults.get('pool_tags'):
            self.pool_tags_entry.delete(0, tk.END)
            self.pool_tags_entry.insert(0, defaults['pool_tags'])
        if 'move_files' in defaults:
            self.move_files_var.set(defaults['move_files'])
        if 'preserve_exact_names' in defaults:
            self.preserve_exact_names.set(defaults['preserve_exact_names'])

    def _setup_ui(self):
        # Main container with padding
        main = tk.Frame(self.root, bg=THEME["bg"], padx=40, pady=30)
        main.pack(fill="both", expand=True)

        # Header
        header = tk.Frame(main, bg=THEME["bg"])
        header.pack(fill="x", pady=(0, 30))
        tk.Label(header, text="ShortsSync", font=("Helvetica", 24, "bold"), 
                bg=THEME["bg"], fg=THEME["fg"]).pack(side="left")
        tk.Label(header, text="Audio Fingerprint Matcher", font=("Helvetica", 11), 
                bg=THEME["bg"], fg=THEME["fg_sub"]).pack(side="left", padx=(15, 0), pady=(8, 0))

        # Workspace Section
        self._create_section(main, "Workspace", self._build_workspace)

        # Configuration Section
        self._create_section(main, "Configuration", self._build_config)

        # Results Section
        results_card = tk.Frame(main, bg=THEME["card_bg"], relief="flat", bd=1)
        results_card.pack(fill="both", expand=True, pady=(0, 20))
        
        results_inner = tk.Frame(results_card, bg=THEME["card_bg"], padx=20, pady=20)
        results_inner.pack(fill="both", expand=True)
        
        tk.Label(results_inner, text="Results", font=("Helvetica", 12, "bold"), 
                bg=THEME["card_bg"], fg=THEME["fg"]).pack(anchor="w", pady=(0, 15))

        # Treeview
        style = ttk.Style()
        style.theme_use("clam")
        
        style.configure("Treeview",
                       background="white",
                       foreground=THEME["fg"],
                       fieldbackground="white",
                       borderwidth=1,
                       relief="solid",
                       rowheight=32,
                       font=("Helvetica", 11))
        
        style.configure("Treeview.Heading",
                       background=THEME["card_bg"],
                       foreground=THEME["fg"],
                       borderwidth=0,
                       font=("Helvetica", 10, "bold"))
        
        style.map("Treeview", background=[("selected", "#e3f2fd")])
        style.map("Treeview.Heading", background=[("active", THEME["card_bg"])])

        tree_container = tk.Frame(results_inner, bg="white", relief="solid", bd=1)
        tree_container.pack(fill="both", expand=True)

        columns = ("original", "arrow", "new", "score")
        self.tree = ttk.Treeview(tree_container, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("original", text="Video File", anchor="w")
        self.tree.heading("arrow", text="")
        self.tree.heading("new", text="Proposed Name", anchor="w")
        self.tree.heading("score", text="Score", anchor="center")
        
        self.tree.column("original", width=350, anchor="w")
        self.tree.column("arrow", width=40, anchor="center")
        self.tree.column("new", width=350, anchor="w")
        self.tree.column("score", width=100, anchor="center")
        
        sb = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # Footer with actions
        footer = tk.Frame(self.root, bg=THEME["bg"], padx=40, pady=20)
        footer.pack(fill="x", side="bottom")

        tk.Label(footer, textvariable=self.status_var, bg=THEME["bg"], 
                fg=THEME["fg_sub"], font=("Helvetica", 10)).pack(side="left")

        # Buttons
        self.rename_btn = tk.Button(footer, text="Commit Rename", command=self.commit_renames,
                                    bg=THEME["success"], fg="white", font=("Helvetica", 11, "bold"),
                                    relief="flat", padx=20, pady=8, cursor="hand2",
                                    activebackground=THEME["success_hover"])
        self.rename_btn.pack(side="right")
        self.rename_btn.config(state="disabled")

        self.scan_btn = tk.Button(footer, text="Scan & Match", command=self.start_scan,
                                 bg=THEME["accent"], fg="white", font=("Helvetica", 11, "bold"),
                                 relief="flat", padx=20, pady=8, cursor="hand2",
                                 activebackground=THEME["accent_hover"])
        self.scan_btn.pack(side="right", padx=(0, 10))

    def _create_section(self, parent, title, builder):
        card = tk.Frame(parent, bg=THEME["card_bg"], relief="flat", bd=1)
        card.pack(fill="x", pady=(0, 20))
        
        inner = tk.Frame(card, bg=THEME["card_bg"], padx=20, pady=20)
        inner.pack(fill="x")
        
        tk.Label(inner, text=title, font=("Helvetica", 12, "bold"), 
                bg=THEME["card_bg"], fg=THEME["fg"]).pack(anchor="w", pady=(0, 15))
        
        builder(inner)

    def _build_workspace(self, parent):
        self._create_path_input(parent, "Video Folder", self.video_dir, 0)
        self._create_path_input(parent, "Audio Folder", self.audio_dir, 1)

    def _create_path_input(self, parent, label, var, row):
        container = tk.Frame(parent, bg=THEME["card_bg"])
        container.pack(fill="x", pady=5)
        
        tk.Label(container, text=label, bg=THEME["card_bg"], fg=THEME["fg"], 
                font=("Helvetica", 11)).pack(side="left", padx=(0, 15))
        
        entry = tk.Entry(container, textvariable=var, bg=THEME["input_bg"], fg=THEME["fg"],
                        relief="solid", bd=1, font=("Helvetica", 11))
        entry.pack(side="left", fill="x", expand=True, ipady=6)
        
        btn = tk.Button(container, text="Browse", command=lambda: self._browse(var),
                       bg=THEME["card_bg"], fg=THEME["fg"], font=("Helvetica", 10),
                       relief="solid", bd=1, padx=15, pady=6, cursor="hand2")
        btn.pack(side="left", padx=(10, 0))

    def _build_config(self, parent):
        # Tags row
        tags_row = tk.Frame(parent, bg=THEME["card_bg"])
        tags_row.pack(fill="x", pady=(0, 15))
        
        # Fixed tags
        fixed_container = tk.Frame(tags_row, bg=THEME["card_bg"])
        fixed_container.pack(side="left", fill="x", expand=True)
        tk.Label(fixed_container, text="Fixed Tags", bg=THEME["card_bg"], 
                fg=THEME["fg_sub"], font=("Helvetica", 9)).pack(anchor="w")
        self.fixed_tags_entry = tk.Entry(fixed_container, bg=THEME["input_bg"], 
                                         fg=THEME["fg"], relief="solid", bd=1, 
                                         font=("Helvetica", 11))
        self.fixed_tags_entry.insert(0, "#shorts")
        self.fixed_tags_entry.pack(fill="x", ipady=6, pady=(4, 0))
        
        tk.Frame(tags_row, bg=THEME["card_bg"], width=20).pack(side="left")
        
        # Random tags
        pool_container = tk.Frame(tags_row, bg=THEME["card_bg"])
        pool_container.pack(side="left", fill="x", expand=True)
        tk.Label(pool_container, text="Random Tags Pool", bg=THEME["card_bg"], 
                fg=THEME["fg_sub"], font=("Helvetica", 9)).pack(anchor="w")
        self.pool_tags_entry = tk.Entry(pool_container, bg=THEME["input_bg"], 
                                        fg=THEME["fg"], relief="solid", bd=1, 
                                        font=("Helvetica", 11))
        self.pool_tags_entry.insert(0, "#fyp #viral #trending")
        self.pool_tags_entry.pack(fill="x", ipady=6, pady=(4, 0))

        # Checkboxes
        checks = tk.Frame(parent, bg=THEME["card_bg"])
        checks.pack(fill="x")
        
        tk.Checkbutton(checks, text="Move renamed files to '_Ready' folder", 
                      variable=self.move_files_var, bg=THEME["card_bg"], fg=THEME["fg"],
                      selectcolor="white", font=("Helvetica", 10)).pack(side="left", padx=(0, 20))
        
        tk.Checkbutton(checks, text="Use exact reference names (no tags)", 
                      variable=self.preserve_exact_names, bg=THEME["card_bg"], fg=THEME["fg"],
                      selectcolor="white", font=("Helvetica", 10)).pack(side="left")

    def _browse(self, var):
        d = filedialog.askdirectory()
        if d: var.set(d)

    # --- LOGIC ---
    def start_scan(self):
        if not self.video_dir.get() or not self.audio_dir.get():
            messagebox.showwarning("Missing Input", "Please select both directories.")
            return
        
        self.scan_btn.config(state="disabled")
        self.matches = []
        self.tree.delete(*self.tree.get_children())
        self.status_var.set("Scanning...")
        
        threading.Thread(target=self._run_matching, daemon=True).start()

    def _run_matching(self):
        fpcalc = shutil.which("fpcalc")
        if not fpcalc and os.path.exists("/opt/homebrew/bin/fpcalc"):
            fpcalc = "/opt/homebrew/bin/fpcalc"
        
        if not fpcalc:
            self.root.after(0, lambda: messagebox.showerror("Error", "fpcalc not found."))
            self.root.after(0, lambda: self.scan_btn.config(state="normal"))
            return

        audio_path = self.audio_dir.get()
        video_path = self.video_dir.get()

        self.status_var.set("Indexing reference audio...")
        ref_fps = {}
        
        try:
            audio_exts = ('.mp3', '.wav', '.m4a', '.flac', '.ogg')
            video_exts = ('.mp4', '.mov', '.mkv')
            
            # Recursively find all audio and video files
            all_files = []
            for root, dirs, files in os.walk(audio_path):
                for f in files:
                    if f.lower().endswith(audio_exts) or f.lower().endswith(video_exts):
                        rel_path = os.path.relpath(os.path.join(root, f), audio_path)
                        all_files.append(rel_path)
            
            for i, rel_path in enumerate(all_files):
                self.status_var.set(f"Indexing ({i+1}/{len(all_files)}): {rel_path}")
                file_path = os.path.join(audio_path, rel_path)
                
                # If it's a video file, extract audio first
                if rel_path.lower().endswith(video_exts):
                    temp_audio = os.path.join(audio_path, ".temp_ref_audio.wav")
                    try:
                        video = VideoFileClip(file_path)
                        if not video.audio:
                            video.close()
                            continue
                        video.audio.write_audiofile(temp_audio, logger=None, codec='pcm_s16le')
                        video.close()
                        fp = self._get_fingerprint(temp_audio, fpcalc)
                        if os.path.exists(temp_audio):
                            try: os.remove(temp_audio)
                            except: pass
                    except Exception as e:
                        print(f"Error extracting audio from {rel_path}: {e}")
                        continue
                else:
                    fp = self._get_fingerprint(file_path, fpcalc)
                
                if fp is not None and len(fp) > 0:
                    # Use just the filename (without path) as the key
                    filename = os.path.basename(rel_path)
                    ref_fps[filename] = np.unpackbits(fp.view(np.uint8))
        except Exception as e:
            print(f"Index error: {e}")

        if not ref_fps:
            self.status_var.set("No reference audio found.")
            self.root.after(0, lambda: self.scan_btn.config(state="normal"))
            return

        try:
            vid_files = [f for f in os.listdir(video_path) if f.lower().endswith(('.mp4', '.mov', '.mkv'))]
        except Exception:
            vid_files = []

        results = []
        proposed_names = set()

        for i, f in enumerate(vid_files):
            self.status_var.set(f"Matching ({i+1}/{len(vid_files)}): {f}")
            full_path = os.path.join(video_path, f)
            temp_wav = os.path.join(video_path, ".temp_extract.wav")
            
            try:
                video = VideoFileClip(full_path)
                if not video.audio:
                    video.close()
                    results.append((f, "---", "No Audio"))
                    continue
                
                video.audio.write_audiofile(temp_wav, logger=None, codec='pcm_s16le')
                video.close()
                
                q_fp = self._get_fingerprint(temp_wav, fpcalc)
                if q_fp is None or len(q_fp) == 0:
                    results.append((f, "---", "FP Error"))
                    continue
                
                q_bits = np.unpackbits(q_fp.view(np.uint8))
                n_q = len(q_bits)
                
                best_ber = 1.0
                best_ref = None
                
                for ref_name, r_bits in ref_fps.items():
                    n_r = len(r_bits)
                    if n_q > n_r: continue
                    
                    n_windows = (n_r // 32) - (len(q_fp)) + 1
                    if n_windows < 1: continue
                    
                    min_dist = float('inf')
                    for w in range(n_windows):
                        start = w * 32
                        end = start + n_q
                        sub_r = r_bits[start:end]
                        dist = np.count_nonzero(np.bitwise_xor(q_bits, sub_r))
                        if dist < min_dist:
                            min_dist = dist
                            if min_dist == 0: break
                    
                    ber = min_dist / n_q
                    if ber < best_ber:
                        best_ber = ber
                        best_ref = ref_name
                        if best_ber == 0: break
                
                if best_ref and best_ber < 0.15:
                    new_name = self._generate_name(best_ref, f, video_path, proposed_names)
                    proposed_names.add(new_name.lower())
                    results.append((f, new_name, f"{best_ber:.3f}"))
                else:
                    results.append((f, "---", f"No Match ({best_ber:.3f})"))

            except Exception as e:
                print(f"Match error {f}: {e}")
                results.append((f, "---", "Error"))
            finally:
                if os.path.exists(temp_wav):
                    try: os.remove(temp_wav)
                    except: pass

        self.root.after(0, lambda: self._on_scan_complete(results))

    def _get_fingerprint(self, path, fpcalc_path):
        try:
            cmd = [fpcalc_path, "-raw", path]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            for line in res.stdout.splitlines():
                if line.startswith("FINGERPRINT="):
                    raw = line[12:]
                    if not raw: return None
                    return np.array([int(x) for x in raw.split(',')], dtype=np.uint32)
        except Exception:
            return None
        return None

    def _generate_name(self, ref_name, vid_name, vid_dir, used_names):
        base = os.path.splitext(ref_name)[0]
        ext = os.path.splitext(vid_name)[1]
        
        if self.preserve_exact_names.get():
            candidate = f"{base}{ext}"
            if not os.path.exists(os.path.join(vid_dir, candidate)) and candidate.lower() not in used_names:
                return candidate
            for i in range(1, 100):
                c = f"{base}_{i}{ext}"
                if not os.path.exists(os.path.join(vid_dir, c)) and c.lower() not in used_names:
                    return c
        
        fixed = self.fixed_tags_entry.get().strip()
        pool = self.pool_tags_entry.get().split()
        
        for _ in range(20):
            tags = random.sample(pool, k=min(2, len(pool))) if pool else []
            tag_str = " ".join(tags)
            full = f"{base} {fixed} {tag_str}".strip()
            candidate = f"{full}{ext}"
            if not os.path.exists(os.path.join(vid_dir, candidate)) and candidate.lower() not in used_names:
                return candidate
        
        return f"{base}_{random.randint(1000,9999)}{ext}"

    def _on_scan_complete(self, results):
        self.matches = results
        self.tree.delete(*self.tree.get_children())
        count = 0
        for orig, new, score in results:
            self.tree.insert("", "end", values=(orig, "→", new, score))
            if new != "---": count += 1
            
        self.status_var.set(f"Complete. Found {count} matches.")
        self.scan_btn.config(state="normal")
        if count > 0:
            self.rename_btn.config(state="normal")
        else:
            self.rename_btn.config(state="disabled")

    def commit_renames(self):
        valid = [m for m in self.matches if m[1] != "---"]
        if not valid: return
        
        if not messagebox.askyesno("Confirm", f"Rename {len(valid)} files?"):
            return
            
        vid_dir = self.video_dir.get()
        move = self.move_files_var.get()
        target_dir = os.path.join(vid_dir, "_Ready") if move else vid_dir
        
        if move and not os.path.exists(target_dir):
            os.makedirs(target_dir)
            
        count = 0
        for orig, new, _ in valid:
            src = os.path.join(vid_dir, orig)
            dst = os.path.join(target_dir, new)
            try:
                os.rename(src, dst)
                count += 1
            except Exception as e:
                print(f"Rename error: {e}")
        
        messagebox.showinfo("Success", f"Renamed {count} files.")
        self.matches = []
        self.tree.delete(*self.tree.get_children())
        self.rename_btn.config(state="disabled")
        self.status_var.set("Ready")

if __name__ == "__main__":
    root = tk.Tk()
    app = ShortsSyncApp(root)
    root.mainloop()
