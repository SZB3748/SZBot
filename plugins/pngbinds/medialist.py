import datafile
import json
import os

MEDIA_DIR = datafile.makepath("pngbinds-media")
MEDIA_LIST_PATH = datafile.makepath("pngbinds_media.json")

MediaList = dict[str, dict[str]]

def load_media_list(path=MEDIA_LIST_PATH)->MediaList:
    if os.path.isfile(path):
        with open(path) as f:
            return json.load(f)
    return {}
    
def save_media_list(mlist:MediaList, path=MEDIA_LIST_PATH):
    with open(path, "w") as f:
        json.dump(mlist, f, indent="    ")
    