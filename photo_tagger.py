#!/usr/bin/env python3
"""
FHU Photo Tagger
----------------
Step 1: view each photo and type the player name(s) into its Keywords metadata.
Step 2: reads those keywords, then writes:
  - Headline  -> first initial + last name, lowercase (multiple players separated by a space)
  - Caption   -> "NAME in FHU's SPORT game/match against OPPONENT on DATE"
and saves a renamed copy as HEADLINE-vs-opponent.jpg (hyphens instead of spaces).

Step 1 writes keywords directly into the photos in the folder you pick.
Step 2 never changes those photos; tagged copies go into a "Tagged" folder
inside that folder.

Requires: Python 3 (tkinter is included), Pillow (pip install pillow) for the
photo preview, and ExifTool (https://exiftool.org).
Works on Mac and Windows.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from PIL import Image, ImageOps, ImageTk
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

MATCH_SPORTS = {"volleyball", "tennis", "soccer"}
SPORTS = [
    "Baseball", "Men's Basketball", "Women's Basketball", "Bowling",
    "Cross Country", "Football", "Golf", "Men's Soccer", "Women's Soccer",
    "Softball", "Swimming", "Tennis", "Track and Field", "Volleyball",
]


def is_match_sport(sport):
    """True for volleyball, tennis, soccer (men's/women's prefix ignored)."""
    s = sport.lower().strip()
    for prefix in ("men's ", "women's ", "mens ", "womens "):
        if s.startswith(prefix):
            s = s[len(prefix):]
    return s in MATCH_SPORTS
EXTS = {".jpg", ".jpeg"}


# ---------------------------------------------------------------- exiftool
def find_exiftool():
    here = os.path.dirname(os.path.abspath(__file__))
    names = ["exiftool.exe", "exiftool"] if os.name == "nt" else ["exiftool"]
    # Packaged .app: exiftool is bundled in "exiftool_bundle"
    bases = [getattr(sys, "_MEIPASS", None), here]
    for base in bases:
        if not base:
            continue
        p = os.path.join(base, "exiftool_bundle", "exiftool")
        if os.path.isfile(p):
            try:
                os.chmod(p, 0o755)
            except OSError:
                pass
            return p
    for n in names:
        p = os.path.join(here, n)
        if os.path.isfile(p):
            return p
    found = shutil.which("exiftool")
    if found:
        return found
    for p in ("/opt/homebrew/bin/exiftool", "/usr/local/bin/exiftool"):
        if os.path.isfile(p):
            return p
    return None


def run(cmd):
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000  # no console window
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kwargs)


def read_keywords(exiftool, path):
    r = run([exiftool, "-json", "-charset", "iptc=utf8", "-IPTC:Keywords",
             "-XMP-dc:Subject", path])
    if r.returncode != 0 or not r.stdout.strip():
        return []
    data = json.loads(r.stdout)[0]
    raw = data.get("Keywords") or data.get("Subject") or []
    if not isinstance(raw, list):
        raw = [raw]
    names = []
    for item in raw:
        for part in re.split(r"[;,]", str(item)):
            part = part.strip()
            if part and part not in names:
                names.append(part)
    return names


# ------------------------------------------------------------ text builders
def clean_word(w):
    return re.sub(r"[^A-Za-z0-9]", "", w)


def handle(name):
    """'Becca Heineman' -> 'bheineman'"""
    words = [w for w in name.split() if clean_word(w)]
    if not words:
        return ""
    if len(words) == 1:
        return clean_word(words[0]).lower()
    return (clean_word(words[0])[0] + clean_word(words[-1])).lower()


def join_names(names):
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def slug(text):
    text = re.sub(r"['’]", "", text)
    text = re.sub(r"[^A-Za-z0-9]+", "-", text.strip().lower())
    return text.strip("-")


def process(exiftool, folder, sport, opponent, date, log, done):
    try:
        out = os.path.join(folder, "Tagged")
        os.makedirs(out, exist_ok=True)
        noun = "match" if is_match_sport(sport) else "game"
        opp_slug = slug(opponent)
        files = sorted(f for f in os.listdir(folder)
                       if os.path.splitext(f)[1].lower() in EXTS
                       and not f.startswith("."))
        if not files:
            log("No .jpg files found in that folder.")
            return
        used = {}
        ok = skipped = 0
        for f in files:
            src = os.path.join(folder, f)
            names = read_keywords(exiftool, src)
            handles = [handle(n) for n in names if handle(n)]
            if handles:
                headline = " ".join(handles)
                caption = (f"{join_names(names)} in FHU's {sport.lower()} "
                           f"{noun} against {opponent} on {date}")
                base = f"{'-'.join(handles)}-vs-{opp_slug}"
            else:
                # No keyword: generic caption, no headline, generic filename
                headline = ""
                caption = (f"FHU {sport.lower()} in action against "
                           f"{opponent} on {date}")
                base = f"fhu-{slug(sport)}-vs-{opp_slug}"
                log(f"No keyword on {f} (used generic caption)")
                skipped += 1
            count = used.get(base, 0) + 1
            used[base] = count
            fname = f"{base}.jpg" if count == 1 else f"{base}-{count}.jpg"
            dest = os.path.join(out, fname)
            shutil.copy2(src, dest)

            args = [
                "-charset", "utf8",
                "-codedcharacterset=utf8",
                "-overwrite_original", "-m",
                f"-IPTC:Headline={headline}",
                f"-XMP-photoshop:Headline={headline}",
                f"-IPTC:Caption-Abstract={caption}",
                f"-XMP-dc:Description={caption}",
                f"-EXIF:ImageDescription={caption}",
                dest,
            ]
            with tempfile.NamedTemporaryFile("w", suffix=".args", delete=False,
                                             encoding="utf-8") as tf:
                tf.write("\n".join(args))
                argfile = tf.name
            r = run([exiftool, "-@", argfile])
            os.unlink(argfile)
            if r.returncode != 0:
                log(f"ERROR on {f}: {r.stderr.strip()}")
                continue
            log(f"{f}  ->  {fname}")
            ok += 1
        log(f"\nDone. {ok} tagged ({skipped} had no keyword and got the "
            f"generic caption).\nSaved in: {out}")
    except Exception as e:  # noqa
        log(f"Unexpected error: {e}")
    finally:
        done()


# --------------------------------------------------------------------- GUI
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".fhu_photo_tagger.json")


def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa
        return {}


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except OSError:
        pass


def write_keywords(exiftool, path, names):
    """Replace the photo's keywords with exactly these names."""
    args = ["-charset", "utf8", "-codedcharacterset=utf8",
            "-overwrite_original", "-m",
            "-IPTC:Keywords=", "-XMP-dc:Subject="]
    for n in names:
        args += [f"-IPTC:Keywords+={n}", f"-XMP-dc:Subject+={n}"]
    args.append(path)
    with tempfile.NamedTemporaryFile("w", suffix=".args", delete=False,
                                     encoding="utf-8") as tf:
        tf.write("\n".join(args))
        argfile = tf.name
    r = run([exiftool, "-@", argfile])
    os.unlink(argfile)
    return r.returncode == 0, r.stderr.strip()


def list_photos(folder):
    return [os.path.join(folder, f) for f in sorted(os.listdir(folder))
            if os.path.splitext(f)[1].lower() in EXTS and not f.startswith(".")]


class TaggerTab(ttk.Frame):
    """Step 1: look at each photo and type the player name(s)."""
    W, H = 820, 500

    def __init__(self, parent, exiftool, cfg):
        super().__init__(parent)
        self.exiftool = exiftool
        self.cfg = cfg
        self.roster = list(cfg.get("roster", []))
        self.files, self.i, self.photo = [], 0, None
        self.prev_names, self.matches = [], []

        self.info = ttk.Label(self, text="Choose a photo folder above.")
        self.info.pack(anchor="w", padx=10, pady=(8, 2))

        box = tk.Frame(self, width=self.W, height=self.H, bg="#222")
        box.pack(padx=10)
        box.pack_propagate(False)
        self.img_label = tk.Label(box, bg="#222")
        self.img_label.pack(expand=True)

        ttk.Label(self, text="Player name(s). Separate multiple players with "
                  "commas. Tab = autocomplete, Enter = save and next."
                  ).pack(anchor="w", padx=10, pady=(8, 2))
        self.var = tk.StringVar()
        self.entry = ttk.Entry(self, textvariable=self.var, font=("", 14))
        self.entry.pack(fill="x", padx=10)
        self.var.trace_add("write", lambda *a: self.filter())
        self.entry.bind("<Return>", lambda e: self.save_next())
        self.entry.bind("<Tab>", self.on_tab)

        self.listbox = tk.Listbox(self, height=4, exportselection=False)
        self.listbox.pack(fill="x", padx=10, pady=4)
        self.listbox.bind("<<ListboxSelect>>", self.pick_match)

        row = ttk.Frame(self)
        row.pack(pady=4)
        ttk.Button(row, text="< Back", command=self.back).pack(side="left", padx=3)
        ttk.Button(row, text="Same as previous",
                   command=self.same_as_prev).pack(side="left", padx=3)
        ttk.Button(row, text="Skip", command=self.skip).pack(side="left", padx=3)
        ttk.Button(row, text="Save and next (Enter)",
                   command=self.save_next).pack(side="left", padx=3)
        ttk.Button(row, text="Edit roster...",
                   command=self.edit_roster).pack(side="left", padx=(20, 3))

        self.status = ttk.Label(self, text="")
        self.status.pack(anchor="w", padx=10)

    # ---- loading / showing
    def load(self, folder):
        try:
            self.files = list_photos(folder)
        except OSError:
            self.files = []
        self.i = 0
        if not self.files:
            self.info.config(text="No .jpg files found in that folder.")
            self.img_label.config(image="")
            return
        self.show()

    def show(self):
        path = self.files[self.i]
        self.info.config(
            text=f"Photo {self.i + 1} of {len(self.files)}: "
                 f"{os.path.basename(path)}")
        if HAVE_PIL:
            try:
                img = Image.open(path)
                img.draft("RGB", (self.W * 2, self.H * 2))
                img = ImageOps.exif_transpose(img)
                img.thumbnail((self.W, self.H))
                self.photo = ImageTk.PhotoImage(img)
                self.img_label.config(image=self.photo, text="")
            except Exception as e:  # noqa
                self.img_label.config(image="", text=f"Can't show photo: {e}",
                                      fg="white")
        else:
            self.img_label.config(
                image="", fg="white",
                text="Photo preview needs Pillow (pip install pillow)")
        existing = read_keywords(self.exiftool, path)
        self.var.set(", ".join(existing))
        self.entry.focus_set()
        self.entry.icursor("end")
        self.status.config(text="Already tagged. Edit or press Enter to keep."
                           if existing else "")

    # ---- autocomplete
    def token(self):
        return self.var.get().rsplit(",", 1)[-1].strip()

    def filter(self):
        t = self.token().lower()
        self.matches = ([n for n in self.roster if t in n.lower()][:20]
                        if t else [])
        self.listbox.delete(0, "end")
        for n in self.matches:
            self.listbox.insert("end", n)

    def complete(self, name):
        text = self.var.get()
        head = text.rsplit(",", 1)[0] + ", " if "," in text else ""
        self.var.set(head + name)
        self.entry.focus_set()
        self.entry.icursor("end")

    def on_tab(self, _event):
        if self.matches:
            self.complete(self.matches[0])
        return "break"

    def pick_match(self, _event):
        sel = self.listbox.curselection()
        if sel and sel[0] < len(self.matches):
            self.complete(self.matches[sel[0]])

    # ---- actions
    def parse(self):
        lookup = {n.lower(): n for n in self.roster}
        names = []
        for part in re.split(r"[;,]", self.var.get()):
            part = part.strip()
            if part:
                part = lookup.get(part.lower(), part)
                if part not in names:
                    names.append(part)
        return names

    def save_next(self):
        if not self.files:
            return
        names = self.parse()
        if not names:
            self.status.config(text="Type a name first, or press Skip.")
            return
        ok, err = write_keywords(self.exiftool, self.files[self.i], names)
        if not ok:
            self.status.config(text=f"Couldn't save: {err}")
            return
        self.prev_names = names
        lower = {n.lower() for n in self.roster}
        unknown = [n for n in names if self.roster and n.lower() not in lower]
        self.advance("Saved." + (f" (not on roster: {', '.join(unknown)})"
                                 if unknown else ""))

    def advance(self, msg=""):
        if self.i < len(self.files) - 1:
            self.i += 1
            self.show()
            if msg:
                self.status.config(text=msg)
        else:
            self.status.config(text=(msg + " " if msg else "") +
                               "That was the last photo. Go to step 2.")

    def skip(self):
        if self.files:
            self.advance()

    def back(self):
        if self.files and self.i > 0:
            self.i -= 1
            self.show()

    def same_as_prev(self):
        if self.prev_names:
            self.var.set(", ".join(self.prev_names))
            self.entry.focus_set()
            self.entry.icursor("end")

    def edit_roster(self):
        win = tk.Toplevel(self)
        win.title("Roster")
        win.geometry("360x480")
        ttk.Label(win, text="One player per line (paste from the roster page)."
                  ).pack(anchor="w", padx=10, pady=6)
        text = tk.Text(win)
        text.pack(fill="both", expand=True, padx=10)
        text.insert("1.0", "\n".join(self.roster))

        def save():
            self.roster = [ln.strip() for ln in
                           text.get("1.0", "end").splitlines() if ln.strip()]
            self.cfg["roster"] = self.roster
            save_config(self.cfg)
            win.destroy()
            self.filter()

        ttk.Button(win, text="Save roster", command=save).pack(pady=8)


def build_rename_tab(parent, exiftool, folder_var):
    """Step 2: caption, headline, and rename."""
    pad = {"padx": 10, "pady": 4}
    sport_var, opp_var, date_var = tk.StringVar(), tk.StringVar(), tk.StringVar()

    ttk.Label(parent, text="Uses the player names saved in step 1. Tagged "
              "copies go into a 'Tagged' folder.").pack(anchor="w", **pad)
    ttk.Label(parent, text="Sport").pack(anchor="w", **pad)
    ttk.Combobox(parent, textvariable=sport_var, values=SPORTS).pack(fill="x", **pad)
    ttk.Label(parent, text="Opponent (e.g. Cumberlands)").pack(anchor="w", **pad)
    ttk.Entry(parent, textvariable=opp_var).pack(fill="x", **pad)
    ttk.Label(parent, text="Date (e.g. October 3, 2026)").pack(anchor="w", **pad)
    ttk.Entry(parent, textvariable=date_var).pack(fill="x", **pad)

    logbox = tk.Text(parent, height=14, state="disabled")
    run_btn = ttk.Button(parent, text="Tag and rename photos")

    def log(msg):
        def _w():
            logbox.config(state="normal")
            logbox.insert("end", msg + "\n")
            logbox.see("end")
            logbox.config(state="disabled")
        parent.after(0, _w)

    def finished():
        parent.after(0, lambda: run_btn.config(state="normal"))

    def go():
        folder = folder_var.get().strip()
        sport, opp, date = (sport_var.get().strip(), opp_var.get().strip(),
                            date_var.get().strip())
        if not (folder and sport and opp and date):
            messagebox.showwarning("Missing info",
                                   "Fill in the folder, sport, opponent, and date.")
            return
        if not os.path.isdir(folder):
            messagebox.showwarning("Folder not found", folder)
            return
        run_btn.config(state="disabled")
        logbox.config(state="normal")
        logbox.delete("1.0", "end")
        logbox.config(state="disabled")
        threading.Thread(target=process,
                         args=(exiftool, folder, sport, opp, date, log, finished),
                         daemon=True).start()

    run_btn.config(command=go)
    run_btn.pack(pady=8)
    logbox.pack(fill="both", expand=True, **pad)


def main():
    exiftool = find_exiftool()
    root = tk.Tk()
    root.title("FHU Photo Tagger")
    root.geometry("880x940")

    if not exiftool:
        messagebox.showerror(
            "ExifTool not found",
            "Install ExifTool from exiftool.org.\n\n"
            "Mac: install the .pkg (or 'brew install exiftool').\n"
            "Windows: rename exiftool(-k).exe to exiftool.exe and put it "
            "(with its exiftool_files folder) next to this script.")
        root.destroy()
        return

    cfg = load_config()
    folder_var = tk.StringVar(value=cfg.get("folder", ""))

    top = ttk.Frame(root)
    top.pack(fill="x", padx=10, pady=(10, 4))
    ttk.Label(top, text="Photo folder").pack(side="left")
    ttk.Entry(top, textvariable=folder_var).pack(side="left", fill="x",
                                                 expand=True, padx=6)

    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True, padx=6, pady=6)
    tab1, tab2 = ttk.Frame(nb), ttk.Frame(nb)
    nb.add(tab1, text="1. Tag players")
    nb.add(tab2, text="2. Caption and rename")

    tagger = TaggerTab(tab1, exiftool, cfg)
    tagger.pack(fill="both", expand=True)
    build_rename_tab(tab2, exiftool, folder_var)

    def pick():
        d = filedialog.askdirectory(title="Folder of photos")
        if d:
            folder_var.set(d)
            cfg["folder"] = d
            save_config(cfg)
            tagger.load(d)

    ttk.Button(top, text="Browse...", command=pick).pack(side="left")

    start = folder_var.get()
    if start and os.path.isdir(start):
        root.after(200, lambda: tagger.load(start))
    root.mainloop()


if __name__ == "__main__":
    main()
