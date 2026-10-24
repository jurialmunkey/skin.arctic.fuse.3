# -*- coding: utf-8 -*-
"""Where scenes live and how they are read and written.

A movie is described by a "ref" dict: {'path', 'tmdb', 'imdb', 'title', 'year'}.

1. Next to the video file (when Kodi plays a real file over SMB/NFS/local disk):

       Movie (2001)/Movie (2001).mkv
       Movie (2001)/Movie (2001).scenes/scenes.json
       Movie (2001)/Movie (2001).scenes/0000512300.png   <- thumbnails

2. In the shared scenes folder, keyed by the movie's TMDb/IMDb ID. This is what's used
   when there is no real file to sit beside, e.g. PlexKodiConnect in add-on paths mode
   (plugin:// paths, streamed over http). The folder is set in the add-on's settings;
   point every device at the same network folder and they all share scenes:

       <scenes folder>/tmdb-949/scenes.json

   If it isn't set, this device's own add-on data folder is used.

scenes.json:
    {"version": 1, "title": "Heat", "year": 1995, "tmdb": "949", "imdb": "tt0113277",
     "scenes": [{"title": "Opening", "start": 512.3, "thumb": "0000512300.png"}]}

`start` is seconds from the start of the movie. `thumb` is a file name inside the same
folder and may be empty.
"""
import hashlib
import json

import xbmc
import xbmcaddon
import xbmcvfs

ADDON_ID = 'plugin.video.moviescenes'
LOCAL_ROOT = 'special://profile/addon_data/%s/scenes/' % ADDON_ID
JSON_NAME = 'scenes.json'


def log(msg, level=xbmc.LOGINFO):
    xbmc.log('[%s] %s' % (ADDON_ID, msg), level)


def _split(path):
    """Split a Kodi path (smb://, nfs://, C:\\...) into (folder, filename, separator)."""
    sep = '\\' if ('\\' in path and '://' not in path) else '/'
    folder, _, name = path.rpartition(sep)
    return folder + sep, name, sep


def _stem(name):
    return name.rsplit('.', 1)[0] if '.' in name else name


def is_file(path):
    """True for a real file Kodi can write beside (not plugin://, http://, stack://...)."""
    return bool(path) and not path.startswith(
        ('stack://', 'plugin://', 'http://', 'https://', 'pvr://', 'upnp://', 'plex://'))


def shared_root():
    try:
        root = xbmcaddon.Addon(ADDON_ID).getSetting('scenes_folder').strip()
    except RuntimeError:
        root = ''
    if not root:
        return LOCAL_ROOT
    return root if root.endswith(('/', '\\')) else root + '/'


def is_device_only(folder):
    return bool(folder) and folder.startswith(LOCAL_ROOT)


def id_key(ref):
    tmdb = str(ref.get('tmdb') or '').strip()
    imdb = str(ref.get('imdb') or '').strip()
    if tmdb.isdigit():
        return 'tmdb-' + tmdb
    if imdb.startswith('tt'):
        return 'imdb-' + imdb
    return None


def usable(ref):
    return is_file(ref.get('path', '')) or bool(id_key(ref))


def sidecar_dir(video_path):
    folder, name, sep = _split(video_path)
    return '%s%s.scenes%s' % (folder, _stem(name), sep)


def _hash_dir(video_path):
    # Device-only fallback for files without IDs, keyed by file name.
    _, name, _ = _split(video_path)
    return '%s%s/' % (LOCAL_ROOT, hashlib.md5(name.lower().encode('utf-8')).hexdigest())


def candidates(ref):
    """Folders to look in, best first."""
    out = []
    path, key = ref.get('path', ''), id_key(ref)
    if is_file(path):
        out.append(sidecar_dir(path))
    if key:
        out.append(shared_root() + key + '/')
        if shared_root() != LOCAL_ROOT:
            out.append(LOCAL_ROOT + key + '/')
    if is_file(path):
        out.append(_hash_dir(path))
    seen = []
    return [f for f in out if not (f in seen or seen.append(f))]


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


def load(ref):
    """Return (data, folder). folder is where the data was found (or None)."""
    for folder in candidates(ref):
        data = _read_json(folder)
        if data is not None:
            return data, folder
    return {'version': 1, 'scenes': []}, None


def _write(folder, data):
    if not xbmcvfs.exists(folder) and not xbmcvfs.mkdirs(folder):
        return False
    f = xbmcvfs.File(folder + JSON_NAME, 'w')
    try:
        ok = f.write(json.dumps(data, indent=2, ensure_ascii=False))
    finally:
        f.close()
    return bool(ok) and xbmcvfs.exists(folder + JSON_NAME)


def save(ref, data, folder=None):
    """Save scenes to the best folder that can be written (sidecar, then shared, then
    this device). `folder` is where they were loaded from; if they end up somewhere
    better, thumbnails are copied across so nothing is lost. Returns the folder written."""
    data['version'] = 1
    for k in ('title', 'year', 'tmdb', 'imdb'):
        if ref.get(k) and not data.get(k):
            data[k] = ref[k]
    data['scenes'] = sorted(data.get('scenes') or [], key=lambda s: s['start'])
    for f in candidates(ref):
        if f != folder and folder:
            # Moving up (e.g. the shared folder was just set): bring thumbnails along first.
            if not xbmcvfs.exists(f) and not xbmcvfs.mkdirs(f):
                log('Could not write scenes to %s' % f, xbmc.LOGWARNING)
                continue
            for s in data['scenes']:
                if s.get('thumb') and xbmcvfs.exists(folder + s['thumb']):
                    xbmcvfs.copy(folder + s['thumb'], f + s['thumb'])
        if _write(f, data):
            if folder and f != folder and xbmcvfs.exists(folder + JSON_NAME):
                xbmcvfs.delete(folder + JSON_NAME)  # leave one copy only
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
