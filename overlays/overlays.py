from . import layouts
import actions
import bs4
import datafile
import json
import os
from werkzeug.security import safe_join

OVERLAYS_PATH = datafile.makepath("overlays.json")

class LayoutFetcher:
    def resolve_paths(self)->tuple[str|None, str|None]:
        raise NotImplementedError
    
    def fetch(self)->tuple[bs4.BeautifulSoup, layouts.Layout]:
        html_path, meta_path = self.resolve_paths()
        if meta_path is not None:
            layout = layouts.load_layout_meta(meta_path)
            if layout is not None:
                if html_path is not None:
                    tree = layouts.load_layout_html(html_path)
                else:
                    tree = bs4.BeautifulSoup()
                return tree, layout
        return None, None

    
class LayoutByName(LayoutFetcher):
    def __init__(self, name:str):
        self.name = name

    def resolve_paths(self):
        return safe_join(layouts.LAYOUT_DIR, f"{self.name}.html"), safe_join(layouts.LAYOUT_DIR, f"{self.name}.json")
    
    def __getstate__(self):
        return {
            "type": type(self).__qualname__,
            "name": self.name
        }

    def __setstate__(self, d:dict[str]):
        self.name = str(d["name"])
    
class LayoutPathPair(LayoutFetcher):
    def __init__(self, html_path:str, meta_path:str, html_dir:str|None=None, meta_dir:str|None=None):
        self.html_path = html_path
        self.meta_path = meta_path
        self.html_dir = html_dir
        self.meta_dir = meta_dir
    
    def resolve_paths(self):
        if self.html_dir is None:
            dir = layouts.LAYOUT_DIR
        else:
            dir = self.html_dir
        if dir:
            html_path = safe_join(dir, self.html_path)
        else:
            html_path = self.html_path
        if self.meta_dir is None:
            dir = layouts.LAYOUT_DIR
        else:
            dir = self.meta_dir
        if dir:
            meta_path = safe_join(dir, self.meta_path)
        else:
            meta_path = self.meta_path
        return html_path, meta_path
    
    def __getstate__(self):
        return {
            "type": type(self).__qualname__,
            "html_path": self.html_path,
            "meta_path": self.meta_path,
            "html_dir": self.html_dir,
            "meta_dir": self.meta_dir
        }
    
    def __setstate__(self, d:dict[str]):
        self.html_path = str(d["html_path"])
        self.html_dir = str(d["html_dir"])
        self.meta_path = str(d["meta_path"])
        self.meta_dir = str(d["meta_dir"])

fetcher_types:dict[str,type[LayoutFetcher]] = {
    LayoutByName.__name__:LayoutByName,
    LayoutPathPair.__name__:LayoutPathPair
}

class Overlay:
    def __init__(self, name:str, layout_fetcher:LayoutFetcher|None=None, layout_args:dict[str]|None=None, make_connection:bool=True):
        self.name = name
        self.layout_fetcher = layout_fetcher
        self.layout_args = {} if layout_args is None else layout_args
        self.make_connection = make_connection

    def __getstate__(self):
        return {
            "name": self.name,
            "layout_fetcher": None if self.layout_fetcher is None else self.layout_fetcher.__getstate__(),
            "layout_args": actions.extra_data_serialize(self.layout_args),
            "make_connection": self.make_connection
        }
    
    def __setstate__(self, d:dict[str]):
        self.name = str(d["name"])
        self.layout_args = actions.extra_data_deserialize(d["layout_args"])
        self.make_connection = bool(d["make_connection"])
        lfd = d["layout_fetcher"]
        if isinstance(lfd, dict):
            cls = fetcher_types[lfd["type"]]
            layout_fetcher = cls.__new__(cls)
            layout_fetcher.__setstate__(lfd)
            self.layout_fetcher = layout_fetcher
        else:
            self.layout_fetcher = None

runtime_overlays:dict[str, Overlay] = {}

def load_overlays(path:str=None)->dict[str,Overlay]:
    if path is None:
        path = OVERLAYS_PATH
    if not os.path.isfile(path):
        return {}
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {}
    rtv = {}
    for od in data.values():
        overlay = Overlay.__new__(Overlay)
        overlay.__setstate__(od)
        rtv[overlay.name] = overlay
    return rtv

def save_overlays(overlays:dict[str,Overlay], path:str=None):
    c = json.dumps({o.name:o.__getstate__() for o in overlays.values()}, ensure_ascii=False)
    with open(OVERLAYS_PATH if path is None else path, "w") as f:
        f.write(c)

def merge_overlays(path:str=None):
    d = runtime_overlays.copy()
    d.update(load_overlays(path=path))
    return d