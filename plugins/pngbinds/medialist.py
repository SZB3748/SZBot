import os

MEDIA_DIR = "pngbinds-media"
MEDIA_LIST_PATH = "pngbinds.media"

def load_media_list(path=MEDIA_LIST_PATH)->dict[str,str]:
    mlist = {}
    if os.path.isfile(path):
        with open(path) as f:
            for line in f:
                parts = line.strip().split("\t",1)
                if len(parts) != 2:
                    continue
                mlist[parts[0]] = parts[1]
    return mlist
    
def save_media_list(mlist:dict[str,str], path=MEDIA_LIST_PATH):
    with open(path, "w") as f:
        for name, path in mlist.items():
            f.write(f"{name}\t{path}\n")
    