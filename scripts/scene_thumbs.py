#!/usr/bin/env python3
"""Fill in Movie Scenes thumbnails with ffmpeg, and optionally import embedded chapters.

Kodi saves a screenshot when you add a scene during playback, but some devices
(the Nvidia Shield, for one) capture a black frame, and scenes typed in by time
have no picture at all. Run this on a machine that can see your movie share and
has ffmpeg/ffprobe installed; it writes a 640px JPEG for every scene missing one.

    python scene_thumbs.py "\\\\TOWER\\movies"            # Windows, SMB share
    python scene_thumbs.py /mnt/user/movies              # Unraid / Linux
    python scene_thumbs.py /mnt/user/movies --import-chapters

--import-chapters creates scenes from a movie's built-in chapters, but only for
movies that don't have any scenes yet. Your own scenes are never overwritten.

PlexKodiConnect (add-on paths) keeps scenes in the add-on's shared scenes folder,
named by TMDb/IMDb ID instead of sitting beside the movie. Point --scenes-folder at
it and the script finds each movie's file by its ID (from a "{tmdb-949}" style folder
name or a Kodi/Radarr .nfo) or by "Title (Year)":

    python scene_thumbs.py "\\\\TOWER\\movies" --scenes-folder "\\\\TOWER\\appdata\\moviescenes"
"""
import argparse
import json
import os
import re
import subprocess
import sys

VIDEO_EXT = {'.mkv', '.mp4', '.m4v', '.avi', '.ts', '.m2ts', '.mov', '.wmv', '.webm'}
HDR_TRANSFERS = {'smpte2084', 'arib-std-b67'}
WIDTH = 640
TONEMAP = ('zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,'
           'tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p,')


def ffprobe(path, *args):
    out = subprocess.run(['ffprobe', '-v', 'error', '-of', 'json', *args, path],
                         capture_output=True, text=True)
    return json.loads(out.stdout or '{}')


def is_hdr(path):
    streams = ffprobe(path, '-select_streams', 'v:0', '-show_entries', 'stream=color_transfer').get('streams') or []
    return bool(streams) and streams[0].get('color_transfer') in HDR_TRANSFERS


def grab(path, start, out, width, hdr):
    base = ['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-ss', '%.3f' % start, '-i', path,
            '-frames:v', '1', '-q:v', '3']
    scale = 'scale=%d:-2' % width
    attempts = ([TONEMAP + scale] if hdr else []) + [scale]
    for vf in attempts:  # tone-mapped first for HDR; plain if this ffmpeg lacks zscale
        if subprocess.run(base + ['-vf', vf, out], capture_output=True).returncode == 0 and os.path.exists(out):
            return True
    return False


def chapters_to_scenes(path):
    scenes = []
    for i, ch in enumerate(ffprobe(path, '-show_chapters').get('chapters') or []):
        title = (ch.get('tags') or {}).get('title') or 'Chapter %d' % (i + 1)
        scenes.append({'title': title, 'start': round(float(ch['start_time']), 3), 'thumb': ''})
    return scenes


def fill(video, folder, data, label, import_chapters):
    """Make missing thumbnails (and optionally import chapters) for one movie."""
    jpath = os.path.join(folder, 'scenes.json')
    if data is None:
        if not import_chapters:
            return
        scenes = chapters_to_scenes(video)
        if not scenes:
            return
        data = {'version': 1, 'title': label, 'scenes': scenes}
        print('%s: imported %d chapters' % (label, len(scenes)))
        new = True
    else:
        new = False
    missing = [s for s in data.get('scenes', [])
               if not s.get('thumb') or not os.path.exists(os.path.join(folder, s['thumb']))]
    if not missing and not new:
        return
    os.makedirs(folder, exist_ok=True)
    hdr = is_hdr(video) if missing else False
    made = 0
    for s in missing:
        name = '%010d.jpg' % int(round(float(s['start']) * 1000))
        if grab(video, float(s['start']), os.path.join(folder, name), WIDTH, hdr):
            s['thumb'] = name
            made += 1
    with open(jpath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    if missing:
        print('%s: %d of %d thumbnails made' % (label, made, len(missing)))


def read_json(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def process(video, args):
    stem = os.path.splitext(os.path.basename(video))[0]
    folder = os.path.join(os.path.dirname(video), stem + '.scenes')
    fill(video, folder, read_json(os.path.join(folder, 'scenes.json')), stem, args.import_chapters)


def norm(text):
    return re.sub(r'[^a-z0-9]+', '', text.lower())


def movie_ids(video):
    """IDs for a movie file, from its folder/file name or an .nfo beside it."""
    ids = {}
    names = os.path.basename(os.path.dirname(video)) + ' ' + os.path.basename(video)
    m = re.search(r'tmdb(?:id)?[-=](\d+)', names, re.I)
    if m:
        ids['tmdb'] = m.group(1)
    m = re.search(r'(tt\d{6,})', names)
    if m:
        ids['imdb'] = m.group(1)
    stem = os.path.splitext(video)[0]
    for nfo in (stem + '.nfo', os.path.join(os.path.dirname(video), 'movie.nfo')):
        if os.path.exists(nfo):
            text = open(nfo, encoding='utf-8', errors='ignore').read()
            m = re.search(r'<uniqueid[^>]*type="tmdb"[^>]*>(\d+)<', text) or re.search(r'<tmdbid>(\d+)<', text)
            if m:
                ids.setdefault('tmdb', m.group(1))
            m = re.search(r'(tt\d{6,})', text)
            if m:
                ids.setdefault('imdb', m.group(1))
            break
    m = re.match(r'(.+?)\s*\((\d{4})\)', os.path.basename(os.path.dirname(video)))
    if m:
        ids['titleyear'] = norm(m.group(1)) + m.group(2)
    return ids


def process_shared(videos, args):
    index = {}
    for v in videos:
        for k, val in movie_ids(v).items():
            index.setdefault((k, val), v)
    seen = set()
    for entry in sorted(os.listdir(args.scenes_folder)):
        folder = os.path.join(args.scenes_folder, entry)
        data = read_json(os.path.join(folder, 'scenes.json'))
        if data is None:
            continue
        key = ('tmdb', entry[5:]) if entry.startswith('tmdb-') else ('imdb', entry[5:])
        video = index.get(key) or index.get(('tmdb', str(data.get('tmdb', '')))) or \
            index.get(('imdb', str(data.get('imdb', '')))) or \
            index.get(('titleyear', norm(str(data.get('title', ''))) + str(data.get('year', ''))))
        if not video:
            print('%s: no matching movie file found' % (data.get('title') or entry))
            continue
        seen.add(video)
        fill(video, folder, data, data.get('title') or entry, False)
    if args.import_chapters:
        for v in videos:
            if v in seen:
                continue
            ids = movie_ids(v)
            key = 'tmdb-' + ids['tmdb'] if 'tmdb' in ids else ('imdb-' + ids['imdb'] if 'imdb' in ids else None)
            if key and not os.path.exists(os.path.join(args.scenes_folder, key, 'scenes.json')):
                fill(v, os.path.join(args.scenes_folder, key), None,
                     os.path.splitext(os.path.basename(v))[0], True)


def find_videos(paths):
    for root in paths:
        if os.path.isfile(root):
            yield root
            continue
        for dirpath, dirnames, files in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.endswith('.scenes')]
            for name in sorted(files):
                ext = os.path.splitext(name)[1].lower()
                if ext in VIDEO_EXT and not name.lower().endswith('-trailer' + ext):
                    yield os.path.join(dirpath, name)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('paths', nargs='+', help='movie folders or files')
    ap.add_argument('--import-chapters', action='store_true',
                    help="create scenes from embedded chapters for movies that don't have any yet")
    ap.add_argument('--scenes-folder', help="the Movie Scenes add-on's shared scenes folder (PlexKodiConnect add-on paths)")
    ap.add_argument('--width', type=int, default=640, help='thumbnail width in pixels (default 640)')
    args = ap.parse_args()

    for tool in ('ffmpeg', 'ffprobe'):
        try:
            subprocess.run([tool, '-version'], capture_output=True)
        except FileNotFoundError:
            sys.exit('%s not found. Install ffmpeg first (Windows: winget install ffmpeg).' % tool)

    global WIDTH
    WIDTH = args.width
    videos = list(find_videos(args.paths))
    if args.scenes_folder:
        if not os.path.isdir(args.scenes_folder):
            sys.exit('Scenes folder not found: %s' % args.scenes_folder)
        process_shared(videos, args)
    else:
        for v in videos:
            process(v, args)

if __name__ == '__main__':
    main()
