#!/usr/bin/env python3
"""
Photo Tagger
------------
Step 1: view each photo and type the player name(s) into its Keywords metadata.
Step 2: reads those keywords, then writes:
  - Headline  -> first initial + last name, lowercase (multiple players separated by a space)
  - Caption   -> "NAME in TEAM's SPORT game/match against OPPONENT on DATE"
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
import ssl
import tempfile
import threading
import tkinter as tk
import urllib.request
from html.parser import HTMLParser
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
    bases = [b for b in (getattr(sys, "_MEIPASS", None), here) if b]
    if os.name != "nt":
        for base in bases:
            p = os.path.join(base, "exiftool_bundle", "exiftool")
            if os.path.isfile(p):
                try:
                    os.chmod(p, 0o755)
                except OSError:
                    pass
                return p
    for base in bases:
        for n in names:
            p = os.path.join(base, n)
            if os.path.isfile(p):
                return p
    found = shutil.which("exiftool")
    if found:
        return found
    for p in ("/opt/homebrew/bin/exiftool", "/usr/local/bin/exiftool"):
        if os.path.isfile(p):
            return p
    return None


def safe(text):
    """Flatten line breaks and control characters in anything we hand to ExifTool."""
    return re.sub(r"[\x00-\x1f\x7f]+", " ", str(text)).strip()


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
        for part in re.split(r"[;,]", safe(item)):
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


def possessive(team):
    """FHU -> FHU's, Lions -> Lions' (AP style for names ending in s)."""
    return team + ("'" if team.lower().endswith("s") else "'s")


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


def process(exiftool, folder, team, sport, opponent, date, log, done):
    try:
        team, sport, opponent, date = (safe(team), safe(sport), safe(opponent),
                                       safe(date))
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
                caption = (f"{join_names(names)} in {possessive(team)} {sport.lower()} "
                           f"{noun} against {opponent} on {date}")
                base = f"{'-'.join(handles)}-vs-{opp_slug}"
            else:
                # No keyword: generic caption, no headline, generic filename
                headline = ""
                caption = (f"{team} {sport.lower()} in action against "
                           f"{opponent} on {date}")
                base = f"{slug(team)}-{slug(sport)}-vs-{opp_slug}"
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


# --------------------------------------------------------------- roster import
class _RosterParser(HTMLParser):
    """Pulls player names out of a Sidearm roster page."""

    def __init__(self):
        super().__init__()
        self.tables, self.links = [], []
        self._table = self._row = self._cell = None
        self._skip = 0
        self._href = None
        self._link_text = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "table":
            self._table = []
            self.tables.append(self._table)
        elif tag == "tr" and self._table is not None:
            self._row = []
            self._table.append(self._row)
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag == "a":
            href = a.get("href") or ""
            if re.search(r"/roster/[^/?#]+/\d+", href):
                self._href, self._link_text = href, []

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag in ("td", "th") and self._cell is not None:
            self._row.append(re.sub(r"\s+", " ", " ".join(self._cell)).strip())
            self._cell = None
        elif tag == "tr":
            self._row = None
        elif tag == "table":
            self._table = None
        elif tag == "a" and self._href:
            text = re.sub(r"\s+", " ", " ".join(self._link_text)).strip()
            if text:
                self.links.append(text)
            self._href = None

    def handle_data(self, data):
        if self._skip:
            return
        d = data.strip()
        if not d:
            return
        if self._cell is not None:
            self._cell.append(d)
        if self._href:
            self._link_text.append(d)


def parse_roster_names(html):
    p = _RosterParser()
    p.feed(html)
    names = []

    def add(n):
        n = re.sub(r"^\d+\s+", "", n).strip()
        if (n and not re.search(r"\d", n) and 1 <= len(n.split()) <= 5
                and n not in names):
            names.append(n)

    for table in p.tables:
        header_i = None
        for r_i, row in enumerate(table):
            low = [c.lower() for c in row]
            if "title" in low:
                break  # coaching staff table
            col = next((k for k, c in enumerate(low)
                        if c in ("name", "full name", "player")), None)
            if col is not None:
                header_i = (r_i, col)
                break
        if not header_i:
            continue
        r_i, col = header_i
        for row in table[r_i + 1:]:
            if len(row) > col:
                add(row[col])
    if not names:  # fallback: player-page links
        for text in p.links:
            if re.fullmatch(r"[A-Za-z.'’\- ]+", text) and "bio" not in text.lower():
                add(text)
    return names


def fetch_html(url):
    url = url.strip()
    if not url.lower().startswith("http"):
        url = "https://" + url
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa
        ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/605.1.15 (KHTML, like Gecko) Safari/605.1.15"})
    with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
        return r.read().decode("utf-8", errors="replace")


# --------------------------------------------------------------------- GUI
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".photo_tagger.json")
OLD_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".fhu_photo_tagger.json")


def load_config():
    for path in (CONFIG_PATH, OLD_CONFIG_PATH):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:  # noqa
            continue
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
    for n in map(safe, names):
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
    W, H = 820, 460

    def __init__(self, parent, exiftool, cfg, sport_var):
        super().__init__(parent)
        self.exiftool = exiftool
        self.cfg = cfg
        self.sport_var = sport_var
        self.roster = []
        self.files, self.i, self.photo = [], 0, None
        self.prev_names = []

        srow = ttk.Frame(self)
        srow.pack(fill="x", padx=10, pady=(8, 2))
        ttk.Label(srow, text="Sport").pack(side="left")
        ttk.Combobox(srow, textvariable=sport_var, values=SPORTS,
                     width=22).pack(side="left", padx=6)
        self.roster_label = ttk.Label(srow, text="")
        self.roster_label.pack(side="left", padx=6)
        ttk.Button(srow, text="Edit roster...",
                   command=self.edit_roster).pack(side="right")
        sport_var.trace_add("write", lambda *a: self.load_roster())

        self.info = ttk.Label(self, text="Choose a photo folder above.")
        self.info.pack(anchor="w", padx=10, pady=(4, 2))

        box = tk.Frame(self, width=self.W, height=self.H, bg="#222")
        box.pack(padx=10)
        box.pack_propagate(False)
        self.img_label = tk.Label(box, bg="#222")
        self.img_label.pack(expand=True)

        ttk.Label(self, text="Click player names below (click again to undo), "
                  "or type. Enter = save and next."
                  ).pack(anchor="w", padx=10, pady=(8, 2))
        self.var = tk.StringVar()
        self.entry = ttk.Entry(self, textvariable=self.var, font=("", 14))
        self.entry.pack(fill="x", padx=10)
        self.var.trace_add("write", lambda *a: self.sync())
        self.entry.bind("<Return>", lambda e: self.save_next())

        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True, padx=10, pady=4)
        self.canvas = tk.Canvas(wrap, height=150, highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.btn_frame = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.btn_frame, anchor="nw")
        self.btn_frame.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all(
            "<MouseWheel>", self.on_wheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))
        self.buttons = {}
        self.syncing = False

        row = ttk.Frame(self)
        row.pack(pady=4)
        ttk.Button(row, text="< Back", command=self.back).pack(side="left", padx=3)
        ttk.Button(row, text="Same as previous",
                   command=self.same_as_prev).pack(side="left", padx=3)
        ttk.Button(row, text="Skip", command=self.skip).pack(side="left", padx=3)
        ttk.Button(row, text="Save and next (Enter)",
                   command=self.save_next).pack(side="left", padx=3)

        self.status = ttk.Label(self, text="")
        self.status.pack(anchor="w", padx=10)
        self.load_roster()

    # ---- roster
    def load_roster(self):
        sport = self.sport_var.get().strip()
        self.roster = list(self.cfg.get("rosters", {}).get(sport, []))
        if not sport:
            msg = "Pick a sport to load its roster"
        elif self.roster:
            msg = f"{len(self.roster)} players on roster"
        else:
            msg = "No roster saved yet. Click Edit roster."
        self.roster_label.config(text=msg)
        self.build_buttons()

    def edit_roster(self):
        sport = self.sport_var.get().strip()
        if not sport:
            messagebox.showinfo("Pick a sport", "Choose a sport first.")
            return
        win = tk.Toplevel(self)
        win.title(f"{sport} roster")
        win.geometry("460x600")
        ttk.Label(win, text="Roster page web address (the roster page for this team on "
                  "your school's athletics site)").pack(anchor="w", padx=10,
                                                     pady=(10, 2))
        url_var = tk.StringVar(value=self.cfg.get("roster_urls", {}).get(sport, ""))
        urow = ttk.Frame(win)
        urow.pack(fill="x", padx=10)
        ttk.Entry(urow, textvariable=url_var).pack(side="left", fill="x",
                                                   expand=True)
        text = tk.Text(win)

        def do_import():
            url = url_var.get().strip()
            if not url:
                messagebox.showinfo("Web address", "Paste the roster page "
                                    "address first.", parent=win)
                return
            win.config(cursor="watch")
            win.update_idletasks()
            try:
                names = parse_roster_names(fetch_html(url))
            except Exception as e:  # noqa
                win.config(cursor="")
                messagebox.showerror("Couldn't load the page", str(e), parent=win)
                return
            win.config(cursor="")
            if not names:
                messagebox.showwarning(
                    "No names found",
                    "That page didn't have a roster table I could read. You "
                    "can still paste the names below, one per line.",
                    parent=win)
                return
            text.delete("1.0", "end")
            text.insert("1.0", "\n".join(names))
            status.config(text=f"Found {len(names)} names. Check them, then "
                               "click Save roster.")

        ttk.Button(urow, text="Import", command=do_import).pack(side="left",
                                                                padx=(6, 0))
        status = ttk.Label(win, text="One player per line. You can edit the "
                           "list by hand.")
        status.pack(anchor="w", padx=10, pady=6)
        text.pack(fill="both", expand=True, padx=10)
        text.insert("1.0", "\n".join(self.roster))

        def save():
            names = [ln.strip() for ln in text.get("1.0", "end").splitlines()
                     if ln.strip()]
            self.cfg.setdefault("rosters", {})[sport] = names
            self.cfg.setdefault("roster_urls", {})[sport] = url_var.get().strip()
            save_config(self.cfg)
            win.destroy()
            self.load_roster()

        ttk.Button(win, text="Save roster", command=save).pack(pady=8)

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

    # ---- name buttons
    COLS = 4

    def on_wheel(self, e):
        step = -e.delta if sys.platform == "darwin" else -e.delta // 120
        self.canvas.yview_scroll(int(step), "units")

    def build_buttons(self):
        for w in self.btn_frame.winfo_children():
            w.destroy()
        self.buttons = {}
        for k in range(self.COLS):
            self.btn_frame.columnconfigure(k, weight=1)
        for name in self.roster:
            v = tk.BooleanVar(value=False)
            b = ttk.Checkbutton(self.btn_frame, text=name, variable=v,
                                style="Toolbutton", width=20,
                                command=lambda n=name: self.toggle(n))
            self.buttons[name] = (b, v)
        self.layout_buttons(list(self.roster))
        self.sync()

    def layout_buttons(self, show):
        for b, _ in self.buttons.values():
            b.grid_forget()
        for idx, name in enumerate(show):
            self.buttons[name][0].grid(row=idx // self.COLS, column=idx % self.COLS,
                                       padx=2, pady=2, sticky="ew")
        self.canvas.yview_moveto(0)

    def sync(self):
        """Keep the buttons in step with what's typed in the box."""
        if self.syncing or not self.buttons:
            return
        typed = {n.lower() for n in self.parse()}
        for name, (_, v) in self.buttons.items():
            v.set(name.lower() in typed)
        # Narrow the buttons while a partial name is being typed
        t = self.token().lower()
        exact = any(t == n.lower() for n in self.roster)
        if t and not exact:
            show = [n for n in self.roster if t in n.lower()]
        else:
            show = list(self.roster)
        shown_now = [n for n, (b, _) in self.buttons.items() if b.winfo_manager()]
        if show != shown_now:
            self.layout_buttons(show)

    def toggle(self, name):
        names = self.parse()
        lower = [n.lower() for n in names]
        if name.lower() in lower:
            names = [n for n in names if n.lower() != name.lower()]
        else:
            names.append(name)
        self.syncing = True
        self.var.set(", ".join(names))
        self.syncing = False
        self.sync()
        self.entry.focus_set()
        self.entry.icursor("end")

    def token(self):
        return self.var.get().rsplit(",", 1)[-1].strip()

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


def build_rename_tab(parent, exiftool, folder_var, sport_var, team_var):
    """Step 2: caption, headline, and rename."""
    pad = {"padx": 10, "pady": 4}
    opp_var, date_var = tk.StringVar(), tk.StringVar()

    ttk.Label(parent, text="Uses the player names saved in step 1. Tagged "
              "copies go into a 'Tagged' folder.").pack(anchor="w", **pad)
    ttk.Label(parent, text="Your team or school name (e.g. FHU)"
              ).pack(anchor="w", **pad)
    ttk.Entry(parent, textvariable=team_var).pack(fill="x", **pad)
    ttk.Label(parent, text="Sport (pick one or type your own, e.g. "
              "Women's Tennis)").pack(anchor="w", **pad)
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
        team = team_var.get().strip()
        sport, opp, date = (sport_var.get().strip(), opp_var.get().strip(),
                            date_var.get().strip())
        if not (folder and team and sport and opp and date):
            messagebox.showwarning(
                "Missing info",
                "Fill in the folder, team name, sport, opponent, and date.")
            return
        if not os.path.isdir(folder):
            messagebox.showwarning("Folder not found", folder)
            return
        run_btn.config(state="disabled")
        logbox.config(state="normal")
        logbox.delete("1.0", "end")
        logbox.config(state="disabled")
        threading.Thread(target=process,
                         args=(exiftool, folder, team, sport, opp, date, log, finished),
                         daemon=True).start()

    run_btn.config(command=go)
    run_btn.pack(pady=8)
    logbox.pack(fill="both", expand=True, **pad)


def main():
    exiftool = find_exiftool()
    root = tk.Tk()
    root.title("Photo Tagger")
    root.geometry("880x960")

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
    sport_var = tk.StringVar(value=cfg.get("sport", ""))
    team_var = tk.StringVar(value=cfg.get("team", ""))

    def remember_sport(*_):
        cfg["sport"] = sport_var.get().strip()
        save_config(cfg)

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

    tagger = TaggerTab(tab1, exiftool, cfg, sport_var)
    tagger.pack(fill="both", expand=True)
    build_rename_tab(tab2, exiftool, folder_var, sport_var, team_var)
    sport_var.trace_add("write", remember_sport)

    def remember_team(*_):
        cfg["team"] = team_var.get().strip()
        save_config(cfg)

    team_var.trace_add("write", remember_team)

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
