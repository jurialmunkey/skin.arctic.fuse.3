# Pavan's Arctic Fuse 3 mods

This is a fork of [jurialmunkey/skin.arctic.fuse.3](https://github.com/jurialmunkey/skin.arctic.fuse.3).
All changes live on the `scene-selection` branch; `omega` tracks upstream untouched.

## Scene Selection

Adds a **Scenes** button next to **Play** on a movie's info screen. Pressing it starts the
movie and, about 3 seconds after playback begins, opens Kodi's chapter picker. Choosing a
chapter jumps straight to it.

Files changed:
- `1080i/Includes_DialogInfo.xml` — the Scenes button (movies with a file only)
- `1080i/VideoFullScreen.xml` — opens the chapter picker when the movie starts after Scenes was pressed

Requirements:
- The movie file needs embedded chapters (MakeMKV Blu-ray rips almost always have them).
- For thumbnails: Settings → Player → Videos → **Extract chapter thumbnails** (Advanced/Expert settings level).
- If Kodi asks Resume / Start from beginning, answer that first; the picker opens once playback starts.

## Installing

1. On GitHub, switch to the `scene-selection` branch → **Code → Download ZIP**.
2. Rename the folder inside the zip to `skin.arctic.fuse.3` and re-zip it.
3. In Kodi: Settings → Add-ons → Install from zip file → pick the zip.
4. Open Add-ons → My add-ons → Look and feel → Skin → Arctic Fuse 3 and turn **Auto-update off**,
   so the official repo doesn't overwrite these changes.

The add-on ID is unchanged, so all existing skin settings and home-screen layout carry over.

## Pulling in upstream updates

```
git remote add upstream https://github.com/jurialmunkey/skin.arctic.fuse.3.git   # once
git fetch upstream
git checkout omega && git merge --ff-only upstream/omega && git push
git checkout scene-selection && git rebase omega && git push --force-with-lease
```
