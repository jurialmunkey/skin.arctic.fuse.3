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
"""
import argparse
import json
import os
import subprocess
import sys

VIDEO_EXT = {'.mkv', '.mp4', '.m4v', '.avi', '.ts', '.m2ts', '.mov', '.wmv', '.webm'}
HDR_TRANSFERS = {'smpte2084', 'arib-std-b67'}
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


def process(video, args):
    stem = os.path.splitext(os.path.basename(video))[0]
    folder = os.path.join(os.path.dirname(video), stem + '.scenes')
    jpath = os.path.join(folder, 'scenes.json')

    if os.path.exists(jpath):
        with open(jpath, encoding='utf-8') as f:
            data = json.load(f)
    elif args.import_chapters:
        scenes = chapters_to_scenes(video)
        if not scenes:
            return
        data = {'version': 1, 'title': stem, 'scenes': scenes}
        print('%s: imported %d chapters' % (stem, len(scenes)))
    else:
        return

    missing = [s for s in data.get('scenes', [])
               if not s.get('thumb') or not os.path.exists(os.path.join(folder, s['thumb']))]
    if not missing and os.path.exists(jpath):
        return
    os.makedirs(folder, exist_ok=True)
    hdr = is_hdr(video) if missing else False
    made = 0
    for s in missing:
        name = '%010d.jpg' % int(round(float(s['start']) * 1000))
        if grab(video, float(s['start']), os.path.join(folder, name), args.width, hdr):
            s['thumb'] = name
            made += 1
    with open(jpath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    if missing:
        print('%s: %d of %d thumbnails made' % (stem, made, len(missing)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('paths', nargs='+', help='movie folders or files')
    ap.add_argument('--import-chapters', action='store_true',
                    help="create scenes from embedded chapters for movies that don't have any yet")
    ap.add_argument('--width', type=int, default=640, help='thumbnail width in pixels (default 640)')
    args = ap.parse_args()

    for tool in ('ffmpeg', 'ffprobe'):
        try:
            subprocess.run([tool, '-version'], capture_output=True)
        except FileNotFoundError:
            sys.exit('%s not found. Install ffmpeg first (Windows: winget install ffmpeg).' % tool)

    for root in args.paths:
        if os.path.isfile(root):
            process(root, args)
            continue
        for dirpath, dirnames, files in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.endswith('.scenes')]
            for name in sorted(files):
                if os.path.splitext(name)[1].lower() in VIDEO_EXT and not name.lower().endswith('-trailer' + os.path.splitext(name)[1].lower()):
                    process(os.path.join(dirpath, name), args)


if __name__ == '__main__':
    main()
