import config
import importlib.util
import os
import sys
from types import ModuleType
from typing import Any, Callable

type MetaFields = dict[str, MetaField]

type MetaTypeInfo = dict[str]
type MetaTypeAllowed = bool
type MetaTypeCommand = str
type MetaTypeExpression = MetaTypeInfo | MetaTypeAllowed | MetaTypeCommand

type RunTarget = tuple[str, Any]
type EventCallbackContext = tuple
type EventCallback = Callable[[EventCallbackContext], None]


ExcludedType = type("excluded", (), {})
excluded = ExcludedType()

PLUGINS_DIR = "plugins"

class MetaField:
    def __init__(self, name:str|ExcludedType=excluded, description:str|ExcludedType=excluded,
                 types:dict[str, MetaTypeExpression]|ExcludedType=excluded,
                 optional:bool|ExcludedType=excluded, default:Any|ExcludedType=excluded):
        self.name = name
        self.description = description
        self.types = types
        self.optional = optional
        self.default = default

class Meta:
    def __init__(self, name:str|ExcludedType=excluded, description:str|ExcludedType=excluded, configs:MetaFields|ExcludedType=excluded):
        self.name = name
        self.description = description
        self.configs = configs

class Plugin:
    def __init__(self, name:str, run_target:RunTarget, meta:Meta, module:ModuleType|None=None, on_load:EventCallback|None=None, on_unload:EventCallback|None=None, on_twitch_bot_load:EventCallback|None=None, on_twitch_bot_unload:EventCallback|None=None):
        self.name = name
        self.run_target = run_target
        self.meta = meta
        self.module = module
        self.on_load = on_load
        self.on_unload = on_unload
        self.on_twitch_bot_load = on_twitch_bot_load
        self.on_twitch_bot_unload = on_twitch_bot_unload
        self.is_loaded = False

    def enable(self):
        if self.module is None:
            runtype, runvalue = self.run_target
            if runtype == "path":
                dirname = os.path.dirname(os.path.abspath(runvalue))
                if dirname not in sys.path:
                    sys.path.append(dirname)
                self.module = import_plugin_file(self.name, runvalue)
            self.on_load = getattr(self.module, "on_load", None)
            self.on_unload = getattr(self.module, "on_unload", None)
            self.on_twitch_bot_load = getattr(self.module, "on_twitch_bot_load", None)
            self.on_twitch_bot_unload = getattr(self.module, "on_twitch_bot_unload", None)

    def disable(self, ctx:EventCallbackContext):
        if self.module is not None:
            self.unload(ctx)
            del sys.modules[self.module.__name__]
            self.module = None

    def load(self, ctx:EventCallbackContext):
        if not self.is_loaded and self.on_load is not None:
            self.on_load(ctx)
    
    def unload(self, ctx:EventCallbackContext):
        if self.is_loaded and self.on_unload is not None:
            self.on_unload(ctx)
    
    def twitch_bot_load(self, ctx:EventCallbackContext):
        if not self.is_loaded and self.on_twitch_bot_load is not None:
            self.on_twitch_bot_load(ctx)
    
    def twitch_bot_unload(self, ctx:EventCallbackContext):
        if self.is_loaded and self.on_twitch_bot_unload is not None:
            self.on_twitch_bot_unload(ctx)


def import_plugin_file(name:str, path:str)->ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def parse_plugin_meta(data:dict[str])->Meta:
    name = data.get("name", excluded)
    description = data.get("description", excluded)
    return Meta(name=name, description=description) #TODO configs

def read_plugin_meta(path:str)->Meta:
    data = config.read(path)
    if not (data and isinstance(data, dict)):
        return Meta()
    return parse_plugin_meta(data)

def read_plugin_data(path=config.PLUGIN_FILE)->dict[str, Plugin]:
    data = config.read(path)
    plugins = {}
    if not isinstance(data, dict):
        return plugins

    for name, info in data.items():
        if isinstance(info, bool):
            run_file = os.path.join(PLUGINS_DIR, name, "plugin.py")
            meta_file = os.path.join(PLUGINS_DIR, name, "plugin.json")
            meta = read_plugin_meta(meta_file)
            plugin = plugins[name] = Plugin(name, ("path", run_file), meta)
            if info:
                plugin.enable()
        elif info and isinstance(info, dict):
            runinfo = info.get("run", None)
            metainfo = info.get("meta", None)

            if runinfo and isinstance(runinfo, dict):
                run_target = runinfo["type"], runinfo["value"]
            else:
                run_target = "path", os.path.join(PLUGINS_DIR, name, "plugin.py")
            
            if metainfo and isinstance(metainfo, dict):
                metainfo_type = metainfo["type"]
                if metainfo_type == "path":
                    meta = read_plugin_meta(metainfo["value"])
                elif metainfo_type == "inline":
                    meta = parse_plugin_meta(metainfo["value"])
                else:
                    meta = Meta()
            else:
                meta_file = os.path.join(PLUGINS_DIR, name, "plugin.json")
                meta = read_plugin_meta(meta_file)

            plugin = plugins[name] = Plugin(name, run_target, meta)

            enabled = info.get("enabled", True)
            if enabled:
                plugin.enable()
            
    return plugins
