# -*- coding: utf-8 -*-
import json
import sys
from urllib.parse import parse_qsl, urlencode

import xbmc
import xbmcgui
import xbmcplugin
import xbmcvfs

from resources.lib import store

BASE = 'plugin://%s/' % store.ADDON_ID
HEADING = 'Movie Scenes'


# ---------- helpers ----------

def url(**params):
    return BASE + '?' + urlencode(params)


def notify(msg, error=False):
    xbmcgui.Dialog().notification(HEADING, msg,
                                  xbmcgui.NOTIFICATION_ERROR if error else xbmcgui.NOTIFICATION_INFO, 4000)


def rpc(method, **params):
    req = {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}
    res = json.loads(xbmc.executeJSONRPC(json.dumps(req)))
    return res.get('result') or {}


def movie_details(dbid):
    try:
        dbid = int(dbid)
    except (TypeError, ValueError):
        return None
    if dbid <= 0:
        return None
    res = rpc('VideoLibrary.GetMovieDetails', movieid=dbid,
              properties=['file', 'title', 'year', 'art', 'uniqueid', 'imdbnumber'])
    return res.get('moviedetails')


def ref_from_details(m):
    ids = m.get('uniqueid') or {}
    art = m.get('art') or {}
    imdb = ids.get('imdb') or (m.get('imdbnumber') if str(m.get('imdbnumber', '')).startswith('tt') else '')
    return {'path': m.get('file', ''), 'title': m.get('title', ''), 'year': m.get('year') or '',
            'tmdb': str(ids.get('tmdb') or ''), 'imdb': imdb or '', 'dbid': m.get('movieid'),
            'fanart': art.get('fanart') or art.get('thumb') or ''}


def resolve(params):
    """Build a movie ref from dbid= (library movie) or file= params."""
    m = movie_details(params.get('dbid'))
    if m:
        m.setdefault('movieid', int(params['dbid']))
        return ref_from_details(m)
    return {'path': params.get('file', ''), 'title': params.get('title', ''),
            'tmdb': params.get('tmdb', ''), 'imdb': params.get('imdb', ''),
            'dbid': None, 'fanart': ''}


def display_title(ref):
    if ref.get('title') and ref.get('year'):
        return '%s (%s)' % (ref['title'], ref['year'])
    return ref.get('title') or ''


def playing_ref(player):
    """Work out which movie is playing. With PlexKodiConnect (add-on paths) the playing
    file is an http stream, so fall back to the library entry and its IDs."""
    path = player.getPlayingFile()
    tag = player.getVideoInfoTag()
    dbid = 0
    for get in (lambda: tag.getDbId(), lambda: int(xbmc.getInfoLabel('VideoPlayer.DBID') or 0)):
        try:
            dbid = int(get() or 0)
        except (RuntimeError, ValueError, TypeError):
            dbid = 0
        if dbid > 0:
            break
    m = movie_details(dbid) if dbid > 0 else None
    if m:
        m.setdefault('movieid', dbid)
        ref = ref_from_details(m)
        if is_real(path):
            ref['path'] = path
        return ref
    ref = {'path': path, 'title': tag.getTitle(), 'year': tag.getYear() or '', 'dbid': None, 'fanart': ''}
    try:
        ref['tmdb'] = tag.getUniqueID('tmdb')
        ref['imdb'] = tag.getUniqueID('imdb') or tag.getIMDBNumber()
    except (RuntimeError, AttributeError):
        ref['tmdb'], ref['imdb'] = '', ''
    return ref


def is_real(path):
    return store.is_file(path)


def ref_params(ref, **extra):
    params = {'dbid': ref['dbid']} if ref.get('dbid') else \
        {'file': ref.get('path', ''), 'tmdb': ref.get('tmdb', ''), 'imdb': ref.get('imdb', '')}
    params.update(extra)
    return params


def wait_for(cond, timeout, step=100):
    mon = xbmc.Monitor()
    waited = 0
    while waited < timeout and not mon.abortRequested():
        if cond():
            return True
        xbmc.sleep(step)
        waited += step
    return cond()


# ---------- list: the Scenes row on the info screen ----------

def list_scenes(handle, params):
    ref = resolve(params)
    fanart = ref['fanart']
    xbmcplugin.setContent(handle, 'videos')
    items = []
    if store.usable(ref):
        data, folder = store.load(ref)
        scenes = data['scenes']
        for i, s in enumerate(scenes):
            thumb = store.thumb_path(folder, s) or fanart
            label = s['title'] or 'Scene %d' % (i + 1)
            li = xbmcgui.ListItem(label, store.fmt_time(s['start']), offscreen=True)
            li.setArt({'thumb': thumb, 'landscape': thumb, 'fanart': fanart or thumb, 'icon': thumb})
            li.setProperty('override_landscape', thumb)
            li.setProperty('IsPlayable', 'false')
            tag = li.getVideoInfoTag()
            tag.setTitle(label)
            tag.setMediaType('video')
            tag.setPlot('Scene %d of %d · starts at %s' % (i + 1, len(scenes), store.fmt_time(s['start'])))
            items.append((url(**ref_params(ref, action='play', t='%.3f' % s['start'])), li, False))
        if scenes:
            li = xbmcgui.ListItem('Edit scenes', offscreen=True)
            li.setArt({'thumb': fanart, 'landscape': fanart, 'fanart': fanart})
            li.setProperty('override_landscape', fanart)
            li.setProperty('IsPlayable', 'false')
            li.getVideoInfoTag().setMediaType('video')
            li.getVideoInfoTag().setPlot('Rename, retime or delete scenes for this movie.')
            items.append((url(**ref_params(ref, action='manage')), li, False))
    xbmcplugin.addDirectoryItems(handle, items, len(items))
    xbmcplugin.endOfDirectory(handle, succeeded=True, cacheToDisc=False)


# ---------- play from a scene ----------

def play(params):
    ref = resolve(params)
    path, title, fanart, dbid = ref['path'], display_title(ref), ref['fanart'], ref['dbid']
    try:
        start = float(params.get('t', 0))
    except ValueError:
        start = 0.0
    if not path:
        notify('Movie not found in the library', error=True)
        return
    xbmc.executebuiltin('Dialog.Close(all,true)')
    li = xbmcgui.ListItem(path=path, offscreen=True)
    li.setProperty('StartOffset', '%.3f' % start)
    tag = li.getVideoInfoTag()
    tag.setMediaType('movie')
    if title:
        tag.setTitle(title)
    if dbid:
        tag.setDbId(dbid)
    if fanart:
        li.setArt({'fanart': fanart})
    player = xbmc.Player()
    player.play(path, li)

    # StartOffset is honoured for normal files; add-ons that resolve their own stream
    # (PlexKodiConnect) may drop it, so seek once playback is running if needed.
    def started():
        try:
            return player.isPlayingVideo() and player.getTotalTime() > 0
        except RuntimeError:
            return False
    if start > 0 and wait_for(started, 20000):
        xbmc.sleep(500)
        try:
            if abs(player.getTime() - start) > 3:
                player.seekTime(start)
        except RuntimeError:
            pass


# ---------- add a scene while watching ----------

def add_scene():
    player = xbmc.Player()
    if not player.isPlayingVideo():
        notify('Start a movie first, then add scenes while it plays')
        return
    ref = playing_ref(player)
    if not store.usable(ref):
        notify("Can't tell which movie this is. Scenes work for library movies only", error=True)
        return
    start = player.getTime()
    was_paused = xbmc.getCondVisibility('Player.Paused')

    # Grab a clean frame: hide the playback controls and make sure video is moving
    # so the paused seek bar isn't in the picture.
    xbmc.executebuiltin('Dialog.Close(videoosd,true)')
    xbmc.executebuiltin('Dialog.Close(all,true)')
    if was_paused:
        player.pause()
    xbmc.sleep(600)
    capture = xbmcvfs.translatePath('special://temp/moviescenes_capture.png')
    if xbmcvfs.exists(capture):
        xbmcvfs.delete(capture)
    xbmc.executebuiltin('TakeScreenshot("%s",sync)' % capture, True)
    got_frame = wait_for(lambda: xbmcvfs.exists(capture), 3000)

    if not xbmc.getCondVisibility('Player.Paused'):
        player.pause()
    try:
        if abs(player.getTime() - start) > 1:
            player.seekTime(start)
    except RuntimeError:
        pass

    data, folder = store.load(ref)
    count = len(data['scenes'])
    name = xbmcgui.Dialog().input('Name this scene (%s)' % store.fmt_time(start),
                                  defaultt='Scene %d' % (count + 1))
    if name:
        scene = {'title': name.strip(), 'start': round(start, 3), 'thumb': ''}
        data['scenes'] = [s for s in data['scenes'] if abs(s['start'] - start) > 0.5] + [scene]
        folder = store.save(ref, data, folder)
        if folder:
            thumb = store.thumb_name(start)
            if got_frame and xbmcvfs.copy(capture, folder + thumb):
                scene['thumb'] = thumb
                store.save(ref, data, folder)
            where = ' (this device only)' if store.is_device_only(folder) else ''
            notify('Added "%s" at %s%s' % (scene['title'], store.fmt_time(start), where))
        else:
            notify("Couldn't save the scene", error=True)
    if got_frame:
        xbmcvfs.delete(capture)
    if not was_paused and xbmc.getCondVisibility('Player.Paused'):
        player.pause()


# ---------- manage ----------

def _scene_items(data, folder, fanart):
    items = []
    for i, s in enumerate(data['scenes']):
        li = xbmcgui.ListItem(s['title'] or 'Scene %d' % (i + 1), store.fmt_time(s['start']))
        thumb = store.thumb_path(folder, s) or fanart
        li.setArt({'thumb': thumb, 'icon': thumb})
        items.append(li)
    return items


def manage(params):
    ref = resolve(params)
    title, fanart = display_title(ref), ref['fanart']
    if not store.usable(ref):
        notify("Can't tell which movie this is. Scenes work for library movies only", error=True)
        return
    dlg = xbmcgui.Dialog()
    changed = False
    while True:
        data, folder = store.load(ref)
        add = xbmcgui.ListItem('Add a scene by time…',
                               'Or press the bookmark-star button while watching')
        choice = dlg.select('%s scenes' % (title or 'Movie'),
                            [add] + _scene_items(data, folder, fanart), useDetails=True)
        if choice < 0:
            break
        if choice == 0:
            text = dlg.input('Start time (h:mm:ss)', defaultt='0:00:00')
            start = store.parse_time(text) if text else None
            if start is None:
                continue
            name = dlg.input('Scene name', defaultt='Scene %d' % (len(data['scenes']) + 1))
            if not name:
                continue
            data['scenes'].append({'title': name.strip(), 'start': start, 'thumb': ''})
            changed = bool(store.save(ref, data, folder)) or changed
            continue

        scene = data['scenes'][choice - 1]
        action = dlg.contextmenu(['Play from here', 'Rename', 'Change start time', 'Delete'])
        if action == 0:
            play(ref_params(ref, t=scene['start']))
            return
        if action == 1:
            name = dlg.input('Scene name', defaultt=scene['title'])
            if name:
                scene['title'] = name.strip()
                changed = bool(store.save(ref, data, folder)) or changed
        elif action == 2:
            text = dlg.input('Start time (h:mm:ss)', defaultt=store.fmt_time(scene['start']))
            start = store.parse_time(text) if text else None
            if start is not None and abs(start - scene['start']) > 0.01:
                store.delete_thumb(folder, scene)  # thumbnail no longer matches
                scene['start'], scene['thumb'] = start, ''
                changed = bool(store.save(ref, data, folder)) or changed
        elif action == 3:
            if dlg.yesno(HEADING, 'Delete "%s"?' % scene['title']):
                store.delete_thumb(folder, scene)
                data['scenes'].remove(scene)
                changed = bool(store.save(ref, data, folder)) or changed
    if changed:
        # Reload the info screen's Scenes row.
        xbmc.executebuiltin('Container.Refresh')


# ---------- entry point ----------

def run(argv):
    # RunScript(plugin.video.moviescenes,add) -> argv = [script, 'add']
    if len(argv) > 1 and argv[1] == 'add':
        add_scene()
        return
    handle = int(argv[1]) if len(argv) > 1 and argv[1].lstrip('-').isdigit() else -1
    params = dict(parse_qsl(argv[2].lstrip('?'))) if len(argv) > 2 else {}
    action = params.get('action', 'list')
    if action == 'list' and handle >= 0:
        list_scenes(handle, params)
    elif action == 'play':
        play(params)
    elif action == 'manage':
        manage(params)
    elif action == 'add':
        add_scene()
    elif handle >= 0:
        xbmcplugin.endOfDirectory(handle, succeeded=False)
