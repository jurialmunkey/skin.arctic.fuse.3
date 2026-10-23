# -*- coding: utf-8 -*-
"""Where scenes live and how they are read and written.

Each movie gets a folder next to its video file:

    Movie (2001)/Movie (2001).mkv
    Movie (2001)/Movie (2001).scenes/scenes.json
    Movie (2001)/Movie (2001).scenes/0000512300.png   <- thumbnails

scenes.json:
    {"version": 1, "title": "Movie (2001)",
     "scenes": [{"title": "Opening", "start": 512.3, "thumb": "0000512300.png"}]}

`start` is seconds from the start of the file. `thumb` is a file name inside the
.scenes folder and may be empty. Because the folder sits beside the movie,
every Kodi box that plays from the same share sees the same scenes.

If the movie's folder can't be written to (a read-only share, say), scenes are
kept in this add-on's own data folder on the current device instead.
"""
import hashlib
import json

import xbmc
import xbmcvfs

ADDON_ID = 'plugin.video.moviescenes'
LOCAL_ROOT = 'special://profile/addon_data/%s/scenes/' % ADDON_ID
JSON_NAME = 'scenes.json'


def log(msg, level=xbmc.LOGINFO):
    xbmc.log('[%s] %s' % (ADDON_ID, msg), level)


def _split(path):
    """Split a Kodi path (smb://, nfs://, C:\\...) into (folder, filename)."""
    sep = '\\' if ('\\' in path and '://' not in path) else '/'
    folder, _, name = path.rpartition(sep)
    return folder + sep, name, sep


def _stem(name):
    return name.rsplit('.', 1)[0] if '.' in name else name


def supported(path):
    return bool(path) and not path.startswith(('stack://', 'plugin://', 'http://', 'https://', 'pvr://'))


def sidecar_dir(video_path):
    folder, name, sep = _split(video_path)
    return '%s%s.scenes%s' % (folder, _stem(name), sep)


def local_dir(video_path):
    # Keyed by file name only, so it survives the share being mounted under a different path.
    _, name, _ = _split(video_path)
    key = hashlib.md5(name.lower().encode('utf-8')).hexdigest()
    return '%s%s/' % (LOCAL_ROOT, key)


def _read_json(folder):
    path = folder + JSON_NAME
    if not xbmcvfs.exists(path):
        return None
    f = xbmcvfs.File(path)
    try:
        raw = f.read()
    finally:
        f.close()
    try:
        data = json.loads(raw or '{}')
    except ValueError:
        log('Could not parse %s' % path, xbmc.LOGWARNING)
        return None
    scenes = []
    for s in data.get('scenes') or []:
        try:
            scenes.append({'title': str(s.get('title') or ''),
                           'start': max(0.0, float(s.get('start') or 0)),
                           'thumb': str(s.get('thumb') or '')})
        except (TypeError, ValueError):
            continue
    data['scenes'] = sorted(scenes, key=lambda s: s['start'])
    return data


def load(video_path):
    """Return (data, folder). folder is where the data was found (or None)."""
    for folder in (sidecar_dir(video_path), local_dir(video_path)):
        data = _read_json(folder)
        if data is not None:
            return data, folder
    return {'version': 1, 'title': '', 'scenes': []}, None


def _write(folder, data):
    if not xbmcvfs.exists(folder) and not xbmcvfs.mkdirs(folder):
        return False
    f = xbmcvfs.File(folder + JSON_NAME, 'w')
    try:
        ok = f.write(json.dumps(data, indent=2, ensure_ascii=False))
    finally:
        f.close()
    return bool(ok) and xbmcvfs.exists(folder + JSON_NAME)


def save(video_path, data, folder=None):
    """Save scenes. Tries the given/sidecar folder first, then the local fallback.
    Returns the folder written to, or None."""
    data['version'] = 1
    data['scenes'] = sorted(data.get('scenes') or [], key=lambda s: s['start'])
    candidates = [folder] if folder else []
    for f in (sidecar_dir(video_path), local_dir(video_path)):
        if f not in candidates:
            candidates.append(f)
    for f in candidates:
        if _write(f, data):
            return f
        log('Could not write scenes to %s' % f, xbmc.LOGWARNING)
    return None


def thumb_name(start):
    return '%010d.png' % int(round(start * 1000))


def thumb_path(folder, scene):
    if not folder or not scene.get('thumb'):
        return ''
    path = folder + scene['thumb']
    return path if xbmcvfs.exists(path) else ''


def delete_thumb(folder, scene):
    path = thumb_path(folder, scene)
    if path:
        xbmcvfs.delete(path)


def fmt_time(seconds):
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return '%d:%02d:%02d' % (h, m, s) if h else '%d:%02d' % (m, s)


def parse_time(text):
    """'1:02:03', '62:03', '3723' -> seconds, or None."""
    try:
        parts = [float(p) for p in text.strip().split(':')]
    except ValueError:
        return None
    if not parts or len(parts) > 3 or any(p < 0 for p in parts):
        return None
    total = 0.0
    for p in parts:
        total = total * 60 + p
    return total
