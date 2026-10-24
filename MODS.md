# Pavan's Arctic Fuse 3 mods

This is a fork of [jurialmunkey/skin.arctic.fuse.3](https://github.com/jurialmunkey/skin.arctic.fuse.3).
All changes live on the `scene-selection` branch; `omega` tracks upstream untouched.

## Scene Selection

Your own scene list for each movie, chosen from the info screen **before** the movie starts.

- **Scenes row** on a movie's info screen: a row of thumbnails, one per scene. Pick one and the
  movie starts right at that moment. A **Scenes** button next to Play opens a scene picker.
  The row and button only appear on movies that have scenes.
- **Add scenes while watching:** in the playback controls there's a bookmark-star button.
  Press it at the moment you want, type a name, and the scene is saved with a screenshot as its thumbnail.
- **Edit scenes:** the last tile in the Scenes row (or **Movie scenes…** in any movie's context menu)
  lets you rename, retime or delete scenes, or add one by typing a time.

It's made of three parts in this repo:

| Part | What it does |
|---|---|
| `addons/plugin.video.moviescenes` | Kodi add-on that stores scenes, lists them and plays from a timestamp |
| Skin changes in `1080i/` | Scenes row + button on the info screen (`Includes_DialogInfo.xml`), Add Scene button in the playback controls (`VideoOSD.xml`) |
| `scripts/scene_thumbs.py` | Optional: makes missing thumbnails with ffmpeg and can import a movie's built-in chapters |

### Where scenes are stored

Next to each movie, so every Kodi device playing from the same share sees the same scenes:

```
Heat (1995)/Heat (1995).mkv
Heat (1995)/Heat (1995).scenes/scenes.json
Heat (1995)/Heat (1995).scenes/0000512300.png
```

```json
{"version": 1, "title": "Heat",
 "scenes": [{"title": "Opening heist", "start": 512.3, "thumb": "0000512300.png"}]}
```

`start` is seconds from the start of the file. The file is plain JSON, so other tools
(Silo, scripts) can read and write the same scenes.

Kodi needs **write access** to the movie share for this. If it can't write there, scenes are
saved on that device only (the notification says "this device only"). To fix that, edit the
share's source in Kodi and use an account that can write to it.

### Movies from Plex (PlexKodiConnect)

PlexKodiConnect puts your Plex movies into Kodi's library in one of two ways, and scenes work with both:

- **Direct Paths:** Kodi plays the real file over SMB, so scenes are saved beside the movie as above.
- **Add-on paths** (PKC's default): Kodi only sees a `plugin://` link and a stream from Plex, so
  there's no file to save beside. Scenes are saved by the movie's TMDb/IMDb ID in the add-on's
  **shared scenes folder** instead.

For add-on paths, open Add-ons → Video add-ons → Movie Scenes → **Configure** and set **Shared scenes
folder** to a writable network folder, for example `smb://TOWER/appdata/moviescenes/`. Set the same
folder on every device. Without it, scenes stay on the device where you added them. Scenes saved
before you set the folder move into it automatically the next time you add or edit one for that movie.

```
moviescenes/tmdb-949/scenes.json
moviescenes/tmdb-949/0000512300.png
```

Playing a scene goes through PlexKodiConnect as normal, so Plex still tracks watched status and
resume points.

### Thumbnails

When you add a scene during playback, Kodi saves a screenshot. Some devices capture a black frame
instead of the picture (the Nvidia Shield usually does), and scenes added by typing a time have no
picture. `scripts/scene_thumbs.py` fills those in from the video file:

```
# Windows (needs Python and ffmpeg: winget install Python.Python.3.12 Gyan.FFmpeg)
python scripts\scene_thumbs.py "\\TOWER\movies"

# Create scenes from built-in chapters for movies that don't have any yet
python scripts\scene_thumbs.py "\\TOWER\movies" --import-chapters
```

For PlexKodiConnect add-on paths, also point it at the shared scenes folder. It matches each
movie to its file by a `{tmdb-949}`-style folder name, a `.nfo` file, or "Title (Year)":

```
python scripts\scene_thumbs.py "\\TOWER\movies" --scenes-folder "\\TOWER\appdata\moviescenes"
```

It only fills gaps; it never changes scenes you made. HDR movies are tone-mapped so thumbnails
don't look washed out.

## Installing

Install both zips in Kodi (Settings → Add-ons → Install from zip file), on each device:

1. **Movie Scenes add-on:** `dist/plugin.video.moviescenes-1.2.0.zip` from this branch.
2. **Skin:** on GitHub, switch to the `scene-selection` branch → **Code → Download ZIP**. Rename the
   folder inside the zip to `skin.arctic.fuse.3`, re-zip it, and install that.
3. Add-ons → My add-ons → Look and feel → Skin → Arctic Fuse 3 → turn **Auto-update off**, so the
   official repo doesn't overwrite these changes.

The skin's add-on ID is unchanged, so existing skin settings and home-screen layout carry over.

## Pulling in upstream updates

```
git remote add upstream https://github.com/jurialmunkey/skin.arctic.fuse.3.git   # once
git fetch upstream
git checkout omega && git merge --ff-only upstream/omega && git push
git checkout scene-selection && git rebase omega && git push --force-with-lease
```
