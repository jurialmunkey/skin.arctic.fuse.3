# -*- coding: utf-8 -*-
import sys

from resources.lib import main

if __name__ == '__main__':
    item = sys.listitem  # provided by Kodi for context menu add-ons
    tag = item.getVideoInfoTag()
    main.manage({'dbid': str(tag.getDbId()), 'file': tag.getFilenameAndPath()})
