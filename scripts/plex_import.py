#!/usr/bin/env python3
"""Create Movie Scenes for your whole Plex library from each movie's chapters.

Every chapter becomes a scene with its start and end time, named after the chapter, with
Plex's chapter picture as its thumbnail (when Plex has made one). Movies that already have
scenes are left alone, so your own scenes are never touched.

Scenes are written to the Movie Scenes shared scenes folder, one tmdb-<id> folder per movie,
exactly where Kodi looks for them with PlexKodiConnect.

    python plex_import.py --dry-run          # see what it would do
    python plex_import.py --movie "Heat"     # try one movie first
    python plex_import.py                    # whole library

On a Windows PC with Kodi and PlexKodiConnect set up, the Plex address and token are read
from PlexKodiConnect's settings. Otherwise pass --server and --token.
"""
import argparse
import json
import os
import re
import ssl
import sys
import urllib.parse
import urllib.request

PKC_SETTINGS = os.path.join(os.environ.get('APPDATA', ''), 'Kodi', 'userdata', 'addon_data',
                            'plugin.video.plexkodiconnect', 'settings.xml')
DEFAULT_FOLDER = r'\\192.168.0.206\kodi\moviescenes'
GENERIC = re.compile(r'^\s*(chapter|chap\.?|ch\.?)?\s*0*(\d+)\s*$', re.I)


def pkc_defaults():
    """Read the Plex server address and token PlexKodiConnect uses, if it's installed."""
    if not os.path.exists(PKC_SETTINGS):
        return None, None
    text = open(PKC_SETTINGS, encoding='utf-8', errors='ignore').read()
    get = lambda k: (re.search(r'<setting id="%s"[^>]*>([^<]*)<' % k, text) or [None, ''])[1].strip()
    host, port = get('ipaddress'), get('port') or '32400'
    scheme = 'https' if get('https') == 'true' else 'http'
    token = get('accessToken') or get('plexToken')
    return ('%s://%s:%s' % (scheme, host, port) if host else None), (token or None)


class Plex:
    def __init__(self, server, token):
        self.server, self.token = server.rstrip('/'), token
        self.ctx = ssl.create_default_context()

    def get(self, path, **params):
        params['X-Plex-Token'] = self.token
        url = '%s%s%s%s' % (self.server, path, '&' if '?' in path else '?', urllib.parse.urlencode(params))
        req = urllib.request.Request(url, headers={'Accept': 'application/json'})
        with urllib.request.urlopen(req, context=self.ctx, timeout=30) as r:
            return json.load(r).get('MediaContainer', {})

    def download(self, path, dest, width=640):
        # Ask Plex to resize the chapter picture so thumbnails stay small.
        url = '%s/photo/:/transcode?%s' % (self.server, urllib.parse.urlencode({
            'url': path, 'width': width, 'height': width * 9 // 16, 'minSize': 1,
            'format': 'jpeg', 'X-Plex-Token': self.token}))
        try:
            with urllib.request.urlopen(url, context=self.ctx, timeout=30) as r:
                data = r.read()
        except Exception:
            return False
        if len(data) < 500:
            return False
        with open(dest, 'wb') as f:
            f.write(data)
        return True


def ids_of(item):
    ids = {}
    for g in item.get('Guid') or []:
        scheme, _, value = g.get('id', '').partition('://')
        if scheme in ('tmdb', 'imdb') and value:
            ids[scheme] = value
    legacy = item.get('guid', '')  # older Plex agents: com.plexapp.agents.imdb://tt0113277?lang=en
    m = re.search(r'agents\.(imdb|themoviedb)://([^?]+)', legacy)
    if m:
        ids.setdefault('tmdb' if m.group(1) == 'themoviedb' else 'imdb', m.group(2))
    return ids


def folder_name(ids):
    if ids.get('tmdb', '').isdigit():
        return 'tmdb-' + ids['tmdb']
    if ids.get('imdb', '').startswith('tt'):
        return 'imdb-' + ids['imdb']
    return None


def has_scenes(path):
    try:
        with open(path, encoding='utf-8') as f:
            return bool(json.load(f).get('scenes'))
    except (OSError, ValueError):
        return False


def scene_title(tag, index):
    tag = (tag or '').strip()
    if not tag or GENERIC.match(tag):
        return 'Chapter %d' % index
    return tag


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--scenes-folder', default=DEFAULT_FOLDER, help='shared scenes folder (default %(default)s)')
    ap.add_argument('--server', help='Plex address, e.g. http://192.168.0.206:32400')
    ap.add_argument('--token', help='Plex token (X-Plex-Token)')
    ap.add_argument('--movie', help='only movies whose title contains this text')
    ap.add_argument('--no-ends', action='store_true',
                    help="don't give scenes an end time (they keep playing instead of returning to the info screen)")
    ap.add_argument('--min-chapters', type=int, default=3, help='skip movies with fewer chapters (default 3)')
    ap.add_argument('--no-thumbs', action='store_true', help="don't download chapter pictures")
    ap.add_argument('--dry-run', action='store_true', help='show what would happen without writing anything')
    args = ap.parse_args()

    server, token = pkc_defaults()
    server, token = args.server or server, args.token or token
    if not server or not token:
        sys.exit('Need the Plex address and token: pass --server and --token, or run this on the PC '
                 'where PlexKodiConnect is set up.')
    if not args.dry_run and not os.path.isdir(args.scenes_folder):
        sys.exit("Can't open the scenes folder %s. Open it in File Explorer first so Windows signs in, "
                 'or pass --scenes-folder.' % args.scenes_folder)

    plex = Plex(server, token)
    try:
        sections = [d for d in plex.get('/library/sections').get('Directory', []) if d.get('type') == 'movie']
    except Exception as e:
        sys.exit("Couldn't reach Plex at %s: %s" % (server, e))

    stats = dict(created=0, existing=0, few=0, noid=0, thumbs=0)
    for section in sections:
        items = plex.get('/library/sections/%s/all' % section['key'], type=1, includeGuids=1).get('Metadata', [])
        print('%s: %d movies' % (section.get('title', 'Movies'), len(items)))
        for item in items:
            title = item.get('title', '?')
            if args.movie and args.movie.lower() not in title.lower():
                continue
            label = '%s (%s)' % (title, item['year']) if item.get('year') else title
            name = folder_name(ids_of(item))
            if not name:
                stats['noid'] += 1
                print('  %s: no TMDb/IMDb ID in Plex, skipped' % label)
                continue
            folder = os.path.join(args.scenes_folder, name)
            jpath = os.path.join(folder, 'scenes.json')
            if has_scenes(jpath):
                stats['existing'] += 1
                continue
            meta = (plex.get('/library/metadata/%s' % item['ratingKey'], includeChapters=1).get('Metadata') or [{}])[0]
            chapters = sorted(meta.get('Chapter') or [], key=lambda c: c.get('startTimeOffset', 0))
            if len(chapters) < args.min_chapters:
                stats['few'] += 1
                continue
            ids = ids_of(item)
            scenes, got = [], 0
            if not args.dry_run:
                os.makedirs(folder, exist_ok=True)
            for i, ch in enumerate(chapters, 1):
                start = ch.get('startTimeOffset', 0) / 1000.0
                scene = {'title': scene_title(ch.get('tag'), i), 'start': round(start, 3), 'thumb': ''}
                end = ch.get('endTimeOffset')
                if end and not args.no_ends and end / 1000.0 > start:
                    scene['end'] = round(end / 1000.0, 3)
                if ch.get('thumb') and not args.no_thumbs and not args.dry_run:
                    thumb = '%010d.jpg' % int(round(start * 1000))
                    if plex.download(ch['thumb'], os.path.join(folder, thumb)):
                        scene['thumb'] = thumb
                        got += 1
                scenes.append(scene)
            data = {'version': 1, 'title': title, 'year': item.get('year', ''),
                    'tmdb': ids.get('tmdb', ''), 'imdb': ids.get('imdb', ''),
                    'source': 'plex-chapters', 'scenes': scenes}
            if not args.dry_run:
                with open(jpath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            stats['created'] += 1
            stats['thumbs'] += got
            print('  %s: %d scenes%s' % (label, len(scenes),
                                         '' if args.dry_run or args.no_thumbs else ', %d with pictures' % got))

    plural = lambda n, word: '%d %s%s' % (n, word, '' if n == 1 else 's')
    print('\n%s %s, %s. Skipped: %d already had scenes, %d with fewer than %d '
          'chapters, %d without an ID.' % ('Would add scenes to' if args.dry_run else 'Added scenes to',
                                          plural(stats['created'], 'movie'), plural(stats['thumbs'], 'chapter picture'),
                                          stats['existing'], stats['few'], args.min_chapters, stats['noid']))
    if stats['created'] and not stats['thumbs'] and not args.no_thumbs and not args.dry_run:
        print('No chapter pictures came back. In Plex, turn on Settings > Library > "Generate chapter '
              'thumbnails", let it run, then use scene_thumbs.py to fill in pictures.')


if __name__ == '__main__':
    main()
