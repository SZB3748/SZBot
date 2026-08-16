import datafile
import json
import mimetypes
import os

MEDIA_DIR = datafile.makepath("media")
MEDIA_FILE = datafile.makepath("media.json")

class MediaEntry:
    def __init__(self, name:str, filename:str, tags:list[str], mimetype:str|None=None):
        self.name = name
        self.filename = filename
        self.tags = tags
        self.mimetype = mimetype
        self._mimetype = mimetype
        self._old_name = name

    def resolve_type(self):
        if self.mimetype is None:
            if self._mimetype is None:
                self._mimetype = mimetypes.guess_type(self.filename, strict=False)[0]
        elif self._mimetype != self.mimetype:
            self._mimetype = self.mimetype
        return self._mimetype
        

    def __getstate__(self):
        return {
            "name": self.name,
            "filename": self.filename,
            "tags": self.tags,
            "mimetype": self.mimetype
        }
    
    def __setstate__(self, d:dict[str]):
        self.name = self._old_name = str(d["name"])
        self.filename = str(d["filename"])
        self.tags = [str(tag) for tag in d["tags"]]
        self.mimetype = self._mimetype = None if (mt:=d["mimetype"]) is None else str(mt)

    def get_path(self):
        return get_media_path(self._old_name)

def get_media_path(name:str):
    return os.path.join(MEDIA_DIR, name)

def load_media_entries(path:str=None)->dict[str, MediaEntry]:
    if path is None:
        path = MEDIA_FILE
    if not os.path.isfile(path):
        return {}
    with open(path) as f:
        d = json.load(f)

    if not isinstance(d, dict):
        return {}
    
    rtv = {}
    for de in d.values():
        entry = MediaEntry.__new__(MediaEntry)
        entry.__setstate__(de)
        rtv[entry.name] = entry
    
    return rtv

def save_media_entries(entries:dict[str, MediaEntry], path:str=None):
    d = {}
    renames:list[tuple[str, str, MediaEntry]] = []
    for entry in entries.values():
        if entry.name in d:
            ... #TODO error not unique
        d[entry.name] = entry.__getstate__()
        renames.append((
            os.path.join(MEDIA_DIR, entry._old_name),
            os.path.join(MEDIA_DIR, entry.name),
            entry
        ))
    c = json.dumps({entry.name:entry.__getstate__() for entry in entries.values()}, ensure_ascii=False)
    with open(MEDIA_FILE if path is None else path, "w") as f:
        f.write(c)
    for old_path, new_path, entry in renames:
        if os.path.isfile(old_path):
            os.rename(old_path, new_path)
            entry._old_name = entry.name


def search_media_entries(entries:dict[str, MediaEntry], tags:list[str]):
    found = []
    tagset = {tag for tag in tags if isinstance(tag, str)}
    if tagset:
        for entry in entries.values():
            if all(tag in entry.tags for tag in tagset):
                found.append(entry)
    return found