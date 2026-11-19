# Photo Tagger

A small desktop app for sports information staff who publish game photos to a
website (built with Sidearm sites in mind). It speeds up two chores:

1. **Tag players.** Look at each photo, click the player's name from the
   roster, and the name is saved into the photo's Keywords metadata.
2. **Caption and rename.** Enter your team, sport, opponent, and date. The app
   reads the keywords and writes a headline and caption into each photo, then
   saves a renamed copy.

## What it produces

For a volleyball match against Cumberlands on October 3, 2026, with team name
"FHU":

| Keyword on photo | Headline | Caption | File name |
|---|---|---|---|
| Becca Heineman | `bheineman` | Becca Heineman in FHU's volleyball match against Cumberlands on October 3, 2026 | `bheineman-vs-cumberlands.jpg` |
| Marija Milic, Marija Cabadaj | `mmilic mcabadaj` | Marija Milic and Marija Cabadaj in FHU's volleyball match against Cumberlands on October 3, 2026 | `mmilic-mcabadaj-vs-cumberlands.jpg` |

- Headline is first initial plus last name, lowercase. Several players are
  separated by a space.
- Volleyball, tennis, and soccer say "match"; every other sport says "game".
  Men's and women's versions are handled (for example "Women's Soccer").
- Team names ending in "s" get a trailing apostrophe only (Lions' ...).
- Duplicate file names are numbered: `bheineman-vs-cumberlands-2.jpg`.
- A photo with no keyword gets a generic caption, for example
  "FHU volleyball in action against Cumberlands on October 3, 2026", and no
  headline.
- Headline and caption are written to both IPTC and XMP fields.

## Using it

**Step 1: Tag players**
1. Choose the folder of photos (Browse).
2. Pick the sport. Click **Edit roster**, paste your roster page address, and
   click **Import**, or type names one per line. Rosters are saved per sport.
3. Click player names under each photo (click again to undo), or type. Press
   Enter to save and go to the next photo. Photos already tagged show their
   existing names.

**Step 2: Caption and rename**
1. Enter your team or school name, sport, opponent, and date.
2. Click **Tag and rename photos**. Finished copies go into a `Tagged` folder
   inside your photo folder.

> Step 1 writes keywords **into the photos in the folder you chose**. Step 2
> leaves those photos alone and writes to `Tagged`. Work from a copy or an
> export folder, not your only set of originals.

Roster import reads the standard roster table found on Sidearm-powered athletics
sites. If a page is laid out differently, paste the names in by hand.

Your settings (last folder, team name, rosters) are saved in `.photo_tagger.json`
in your home folder. Nothing is sent anywhere except the roster page request
you start yourself.

## Setup

You need Python 3, Pillow, and ExifTool.

```
pip install pillow certifi
python3 photo_tagger.py
```

**ExifTool** (by Phil Harvey) is downloaded separately from
https://exiftool.org

- **Mac:** install the `.pkg`, or `brew install exiftool`.
- **Windows:** download the Windows executable, rename `exiftool(-k).exe` to
  `exiftool.exe`, and put it and its `exiftool_files` folder next to
  `photo_tagger.py`.

## Build a Mac app

1. Download the ExifTool `.tar.gz` from exiftool.org, unpack it, and rename the
   folder to `exiftool_bundle` (it should contain `exiftool` and `lib`). Place
   it next to `build_mac_app.sh`.
2. Run `bash build_mac_app.sh`.
3. The app appears in `dist/Photo Tagger.app`. The first time you open it,
   right-click and choose Open, since it isn't signed.

The app matches the chip of the Mac that built it (Apple Silicon or Intel).
Windows builds are not scripted yet.

## Credits

Uses [ExifTool](https://exiftool.org) by Phil Harvey for reading and writing
metadata, and [Pillow](https://python-pillow.org) for photo previews.

## License

MIT. See `LICENSE`.
