import copy
from datetime import datetime
import json
import os
from typing import Any

CONFIG_FILE = "config.json"
OAUTH_FILE = "oauth.json"

_cached_contents:dict[str, tuple[datetime, Any]] = {}

def read(path:str=CONFIG_FILE, use_cache:bool=True)->dict[str]:
    if os.path.isfile(path):
        mtime = datetime.fromtimestamp(os.path.getmtime(path))

        if use_cache and path in _cached_contents:
            cachetime, contents = _cached_contents[path]
            if mtime == cachetime:
                return copy.deepcopy(contents)

        with open(path) as f:
            contents = json.load(f)
        
        if use_cache:
            _cached_contents[path] = mtime, copy.deepcopy(contents)

        return contents
    else:
        return {}

def write(new_configs:dict[str]|None=None, config_updates:dict[str]|None=None, path:str=CONFIG_FILE, use_cache:bool=True):
    if os.path.isfile(path):
        with open(path, "r+") as f:
            contents = f.read()
            configs:dict[str] = new_configs if new_configs is not None else json.loads(contents)
            if config_updates is not None:
                configs = {**configs, **config_updates}
            f.seek(0)
            f.truncate()
            try:
                json.dump(configs, f, indent=4)
            except:
                f.write(contents)
                raise
    elif new_configs:
        if config_updates:
            d = {**new_configs, **config_updates}
        else:
            d = new_configs
        with open(path, "w") as f:
            json.dump(d, f, indent=4)
    elif config_updates:
        with open(path, "w") as f:
            json.dump(config_updates, f, indent=4)
    else:
        with open(path, "w") as f:
            f.write("{}")

    if use_cache and path in _cached_contents:
        _cached_contents.pop(path)