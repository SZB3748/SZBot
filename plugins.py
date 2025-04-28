import config
import importlib.util
import math
import os
import re
import sys
from types import ModuleType
from typing import Any, Callable, Self

from twitchbot import Bot
from flask import Blueprint, Flask
from flask_sock import Sock

MetaTypeOptions = dict[str]
MetaTypeAllowed = bool
MetaTypeCommand = str
MetaTypeExpression = MetaTypeOptions | MetaTypeAllowed | MetaTypeCommand

DataTarget = tuple[str, Any]
EventCallbackContext = tuple
EventCallback = Callable[[EventCallbackContext], None]

TYPE_COMMAND_EXCLUDE = "exclude"
TYPE_NAME_OBJECT = "object"
TYPE_NAME_LIST = "list"
TYPE_NAME_STRING = "string"
TYPE_NAME_INTEGER = "integer"
TYPE_NAME_FLOAT = "float"
TYPE_NAME_BOOLEAN = "boolean"
TYPE_NAME_NULL = "null"

ExcludedType = type("excluded", (), {"__repr__": lambda _: "excluded"})
excluded = ExcludedType()

PLUGINS_DIR = "plugins"

class PluginException(Exception):
    """Base class for Plugin Exceptions."""

class PluginLoadException(Exception):
    """Failed to load the plugin."""


class ConfigMetaException(Exception):
    """Base class for Plugin Config Metadata Exceptions."""

class MetaTypeInvalidException(ConfigMetaException):
    """Type not allowed."""

class ConfigMissingMetaFieldException(ConfigMetaException):
    """Config is missing field specified by meta data."""

class ConfigRequirementNotMetException(ConfigMetaException):
    """Config value does not meet all the requirements for its data type specified by the metadata."""


class ConfigMetaError(ConfigMetaException):
    """Base class for errors caused by developers when creating a Plugin's Config Metadata."""

class MetaTypeAssertionError(ConfigMetaError):
    """Type assertion failed."""

class MetaInvalidTypeCommandError(ConfigMetaError):
    """Meta data type option command is invalid."""

class MetaTypeInvalidValueError(ConfigMetaError):
    """Meta data incorrectly specifies type."""

class MetaTypeBadOptionError(ConfigMetaError):
    """Meta type option is invalid."""

def _type_assert(value, name:str, *types:type, can_be_none:bool=True):
    if not ((can_be_none and value is None) or isinstance(value, types)):
        if can_be_none:
            if len(types) < 2:
                tnames = ", ".join(t.__name__ for t in types) + " or None"
            else:
                tnames += ", ".join([*(t.__name__ for t in types), "or None"])
        else:
            tnames = ", ".join(t.__name__ for t in types)
        raise MetaTypeAssertionError(f"Expected {name} to be {tnames}, got {type(value).__name__}: {repr(value)}")
    
    return excluded if value is None else value


def _handle_types(types_data:dict[str]):
    types:dict[str, MetaTypeExpression] = {}
    for type_name, type_info in types_data.items():
        _type_assert(type_info, "type expression", str, bool, dict, can_be_none=False)
        if type_name == TYPE_NAME_OBJECT:
            if isinstance(type_info, dict):
                hasfields = "fields" in type_info
                if not (hasfields ^ ("anyfield" in type_info)):
                    ... #TODO error either/or
                    raise Exception("TODO")
                elif hasfields:
                    fields = _type_assert(type_info.get("fields", None), f"{type_name} fields", dict, can_be_none=False)
                    new_fields = {}
                    for field_name, field_info in fields.items():
                        _type_assert(field_info, f"{type_name} field info", dict)
                        if field_info is not None:
                            new_fields[field_name] = MetaField.construct(field_name, field_info)
                    type_info["fields"] = new_fields
                else: #has anyfield
                    anyfield = _type_assert(type_info.get("anyfield", None), f"{type_name} anyfield", dict, can_be_none=False)
                    type_info["anyfield"] = _handle_types(anyfield)
        elif type_name == "list":
            if isinstance(type_info, dict):
                list_types = type_info.get("types", None)
                _type_assert(list_types, f"{type_name} types", dict, can_be_none=False)
                type_info["types"] = _handle_types(list_types)
        types[type_name] = type_info
    return types


class MetaField:
    @classmethod
    def construct(cls, key:str, data:dict[str]):
        name = data.get("name", excluded)
        description = data.get("description", excluded)
        types_data = data.get("types", excluded)
        optional = data.get("optional", excluded)
        default = data.get("default", excluded)

        name = _type_assert(name, "field name", str, ExcludedType)
        description = _type_assert(description, "field description", str, ExcludedType)
        types_data = _type_assert(types_data, "field types", dict, ExcludedType)
        optional = _type_assert(optional, "field optional status", bool, ExcludedType)

        if types_data is excluded:
            types = excluded
        else:
            types = _handle_types(types_data)

        return cls(key=key, name=name, description=description, types=types, optional=optional, default=default)
        

    def __init__(self, key:str, name:str|ExcludedType=excluded, description:str|ExcludedType=excluded,
                 types:dict[str, MetaTypeExpression]|ExcludedType=excluded,
                 optional:bool|ExcludedType=excluded, default:Any|ExcludedType=excluded):
        self.key = key
        self.name = name
        self.description = description
        self.types = types
        self.optional = optional
        self.default = default

    @property
    def is_optional(self)->bool:
        if self.default is not excluded:
            return bool(self.optional is excluded or self.optional)
        return bool(self.optional is not excluded and self.optional)
    

MetaFieldCollection = dict[str, MetaField]

class Meta:
    def __init__(self, name:str|ExcludedType=excluded, description:str|ExcludedType=excluded, configs:MetaFieldCollection|ExcludedType=excluded):
        self.name = name
        self.description = description
        self.configs = configs

class Plugin:
    def __init__(self, name:str, run_target:DataTarget, meta_target:DataTarget, meta:Meta|None=None, module:ModuleType|None=None,
                 run_next:list[str]|None=None, depends_on:list[str]|None=None, on_load:EventCallback|None=None, on_unload:EventCallback|None=None,
                 on_twitch_bot_load:EventCallback|None=None, on_twitch_bot_unload:EventCallback|None=None):
        self.name = name
        self.run_target = run_target
        self.meta_target = meta_target
        if meta is None:
            mtype, mvalue = meta_target
            if mtype == "path":
                self.meta = read_plugin_meta(mvalue)
            elif mtype == "inline":
                self.meta = parse_plugin_meta(mvalue)
            else:
                self.meta = Meta()
        else:
            self.meta = meta
        self.module = module
        self.run_next = [] if run_next is None else run_next #run this plugin before these plugins
        self.depends_on = [] if depends_on is None else depends_on #run this plugin after these plugins
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


LoadEvent = tuple[dict[str, Plugin], Plugin, bool, Flask, Blueprint, Sock]
UnloadEvent = tuple[dict[str, Plugin], Plugin, bool, Exception|None]
TwitchBotLoadEvent = tuple[dict[str, Plugin], Plugin, bool, Bot]
TwitchBotUnloadEvent = tuple[dict[str, Plugin], Plugin, bool, Exception|None]


shared_plugins_list:dict[str, Plugin] = None

def import_plugin_file(name:str, path:str)->ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def parse_plugin_meta(data:dict[str])->Meta:
    name = data.get("name", excluded)
    description = data.get("description", excluded)

    configs_data = data.get("configs", None)
    if isinstance(configs_data, dict):
        configs:MetaFieldCollection = {}
        for name, config_info in configs_data.items():
            _type_assert(config_info, "config info", dict)
            if config_info is not None:
                configs[name] = MetaField.construct(name, config_info)
    else:
        configs = excluded

    return Meta(name=name, description=description, configs=configs)

def _config_apply_meta_list(v:list, field:MetaField):
    field_t = field.types.get(TYPE_NAME_LIST)
    if field_t is None:
        raise MetaTypeInvalidException(f"Type \"{TYPE_NAME_LIST}\" not allowed for field {field.key}.")
    elif isinstance(field_t, bool):
        if field_t:
            return v
        else:
            raise MetaTypeInvalidException(f"Type \"{TYPE_NAME_LIST}\" not allowed for field {field.key}.")
    elif isinstance(field_t, str):
        if field_t == TYPE_COMMAND_EXCLUDE:
            if field.default is not excluded:
                return excluded if isinstance(field.default, list) else _config_apply_type(field.default, field)
            elif field.optional is excluded or not field.optional:
                raise ConfigMissingMetaFieldException(f"Missing field {field.key}.")
        else:
            raise MetaInvalidTypeCommandError(f"Invalid field type command: {field_t}")
    elif isinstance(field_t, dict):
        for option_name in field_t.keys():
            if option_name != "types":
                raise MetaTypeBadOptionError(f"Type {TYPE_NAME_LIST} does not have option: {option_name}")
        fixed_list = []
        vfield = MetaField("", types=field_t["types"])
        for item in v:
            applied = _config_apply_type(item, vfield)
            if applied is not excluded:
                fixed_list.append(applied)
        return fixed_list
    else:
        raise MetaTypeInvalidValueError(f"Type {TYPE_NAME_LIST} must be specified by {bool.__name__}, {str.__name__}, or {dict.__name__}, got {type(field_t).__name__}: {repr(field_t)}.")

def _config_apply_str(v:str, field:MetaField):
    field_t = field.types.get("string", None)
    if field_t is None:
        raise MetaTypeInvalidException(f"Type \"{TYPE_NAME_STRING}\" not allowed for field {field.key}.")
    elif isinstance(field_t, bool):
        if field_t:
            return v
        else:
            raise MetaTypeInvalidException(f"Type \"{TYPE_NAME_STRING}\" not allowed for field {field.key}.")
    elif isinstance(field_t, str):
        if field_t == TYPE_COMMAND_EXCLUDE:
            if field.default is not excluded:
                return excluded if isinstance(field.default, str) else _config_apply_type(field.default, field)
            elif field.optional is excluded or not field.optional:
                raise ConfigMissingMetaFieldException(f"Missing field {field.key}.")
        else:
            raise MetaInvalidTypeCommandError(f"Invalid field type command: {field_t}")
    elif isinstance(field_t, dict):
        l = len(v)
        for option_name, option_value in field_t.items():
            if option_name == ">":
                if not isinstance(option_value, int):
                    raise MetaTypeBadOptionError(f"Type {TYPE_NAME_STRING} option \"{option_name}\" must speficy {int.__name__} value, got {type(option_value).__name__}: {repr(option_value)}")
                elif l <= option_value:
                    raise ConfigRequirementNotMetException(f"Requirement for {field.key} from option \"{option_name}\" not met: len({repr(v)}) > {option_value}")
            elif option_name == "<":
                if not isinstance(option_value, int):
                    raise MetaTypeBadOptionError(f"Type {TYPE_NAME_STRING} option \"{option_name}\" must speficy {int.__name__} value, got {type(option_value).__name__}: {repr(option_value)}")
                elif l >= option_value:
                    raise ConfigRequirementNotMetException(f"Requirement for {field.key} from option \"{option_name}\" not met: len({repr(v)}) < {option_value}")
            elif option_name == ">=":
                if not isinstance(option_value, int):
                    raise MetaTypeBadOptionError(f"Type {TYPE_NAME_STRING} option \"{option_name}\" must speficy {int.__name__} value, got {type(option_value).__name__}: {repr(option_value)}")
                elif l < option_value:
                    raise ConfigRequirementNotMetException(f"Requirement for {field.key} from option \"{option_name}\" not met: len({repr(v)}) >= {option_value}")
            elif option_name == "<=":
                if not isinstance(option_value, int):
                    raise MetaTypeBadOptionError(f"Type {TYPE_NAME_STRING} option \"{option_name}\" must speficy {int.__name__} value, got {type(option_value).__name__}: {repr(option_value)}")
                elif l > option_value:
                    raise ConfigRequirementNotMetException(f"Requirement for {field.key} from option \"{option_name}\" not met: len({repr(v)}) <= {option_value}")
            elif option_name == "pattern":
                if not isinstance(option_value, str):
                    raise MetaTypeBadOptionError(f"Type {TYPE_NAME_STRING} option \"{option_name}\" must speficy {str.__name__} value, got {type(option_value).__name__}: {repr(option_value)}")
                elif not re.fullmatch(option_value, v):
                    raise ConfigRequirementNotMetException(f"Requirement for {field.key} from option \"{option_name}\" not met: {repr(v)} matches {re.sub(r"[\\]*?/", lambda m: f"{m[0][:-1]}\\/" if m[0].count("\\") % 2 == 0 else m[0], option_value).join("//")}")
            else:
                raise MetaTypeBadOptionError(f"Type {TYPE_NAME_STRING} does not have option: {option_name}")
        return v
    else:
        raise MetaTypeInvalidValueError(f"Type {TYPE_NAME_STRING} must be specified by {bool.__name__}, {str.__name__}, or {dict.__name__}, got {type(field_t).__name__}: {repr(field_t)}.")

def _config_apply_number(v:int|float, T:type[int|float], tname:str, field:MetaField):
    field_t = field.types.get(tname, None)
    if field_t is None:
        raise MetaTypeInvalidException(f"Type \"{tname}\" not allowed for field {field.key}.")
    elif isinstance(field_t, bool):
        if field_t:
            return v
        else:
            raise MetaTypeInvalidException(f"Type \"{tname}\" not allowed for field {field.key}.")
    elif isinstance(field_t, str):
        if field_t == TYPE_COMMAND_EXCLUDE:
            if field.default is not excluded:
                return excluded if isinstance(v, T) else _config_apply_type(field.default, field)
            elif field.optional is excluded or not field.optional:
                raise ConfigMissingMetaFieldException(f"Missing field {field.key}.")
        else:
            raise MetaInvalidTypeCommandError(f"Invalid field type command: {field_t}")
    elif isinstance(field_t, dict):
        type_set_available = [float, int]
        type_set = tuple(type_set_available[type_set_available.index(T):])
        for option_name, option_value in field_t.items():
            if option_name == ">":
                if not isinstance(option_value, type_set):
                    raise MetaTypeBadOptionError(f"Type {tname} option \"{option_name}\" must speficy {" | ".join(t.__name__ for t in type_set)} value, got {type(option_value).__name__}: {repr(option_value)}")
                elif v <= option_value:
                    raise ConfigRequirementNotMetException(f"Requirement for {field.key} from option \"{option_name}\" not met: {v} > {option_value}")
            elif option_name == "<":
                if not isinstance(option_value, type_set):
                    raise MetaTypeBadOptionError(f"Type {tname} option \"{option_name}\" must speficy {" | ".join(t.__name__ for t in type_set)} value, got {type(option_value).__name__}: {repr(option_value)}")
                elif v >= option_value:
                    raise ConfigRequirementNotMetException(f"Requirement for {field.key} from option \"{option_name}\" not met: {v} < {option_value}")
            elif option_name == ">=":
                if not isinstance(option_value, type_set):
                    raise MetaTypeBadOptionError(f"Type {tname} option \"{option_name}\" must speficy {" | ".join(t.__name__ for t in type_set)} value, got {type(option_value).__name__}: {repr(option_value)}")
                elif v < option_value:
                    raise ConfigRequirementNotMetException(f"Requirement for {field.key} from option \"{option_name}\" not met: {v} >= {option_value}")
            elif option_name == "<=":
                if not isinstance(option_value, type_set):
                    raise MetaTypeBadOptionError(f"Type {tname} option \"{option_name}\" must speficy {" | ".join(t.__name__ for t in type_set)} value, got {type(option_value).__name__}: {repr(option_value)}")
                elif v > option_value:
                    raise ConfigRequirementNotMetException(f"Requirement for {field.key} from option \"{option_name}\" not met: {v} <= {option_value}")
            else:
                raise MetaTypeBadOptionError(f"Type {tname} does not have option: {option_name}")
        return v
    else:
        raise MetaTypeInvalidValueError(f"Type {tname} must be specified by {bool.__name__}, {str.__name__}, or {dict.__name__}, got {type(field_t).__name__}: {repr(field_t)}.")

def _config_apply_type(v, field:MetaField):
    if field.types is excluded:
        return v
    else:
        if v is None:
            field_t = field.types.get(TYPE_NAME_NULL, None)
            if field_t is None:
                raise MetaTypeInvalidException(f"Type \"{TYPE_NAME_NULL}\" not allowed for field {field.key}.")
            elif isinstance(field_t, bool):
                if field_t:
                    return v
                else:
                    raise MetaTypeInvalidException(f"Type \"{TYPE_NAME_NULL}\" not allowed for field {field.key}.")
            elif isinstance(field_t, str):
                if field_t == TYPE_COMMAND_EXCLUDE:
                    if field.default is not excluded:
                        return excluded if field.default is None else _config_apply_type(field.default, field)
                    elif field.optional is excluded or not field.optional:
                        raise ConfigMissingMetaFieldException(f"Missing field {field.key}.")
                else:
                    raise MetaInvalidTypeCommandError(f"Invalid field type command: {field_t}")
            elif isinstance(field_t, dict):
                raise MetaTypeBadOptionError(f"Type {TYPE_NAME_NULL} does not have options.")
            else:
                raise MetaTypeInvalidValueError(f"Type {TYPE_NAME_NULL} must be specified by {bool.__name__}, {str.__name__}, or {dict.__name__}, got {type(field_t).__name__}: {repr(field_t)}.")
        elif isinstance(v, str):
            return _config_apply_str(v, field)
        elif isinstance(v, bool):
            field_t = field.types.get(TYPE_NAME_BOOLEAN, None)
            if field_t is None:
                raise MetaTypeInvalidException(f"Type \"{TYPE_NAME_BOOLEAN}\" not allowed for field {field.key}.")
            elif isinstance(field_t, bool):
                if field_t:
                    return v
                else:
                    raise MetaTypeInvalidException(f"Type \"{TYPE_NAME_BOOLEAN}\" not allowed for field {field.key}.")
            elif isinstance(field_t, str):
                if field_t == TYPE_COMMAND_EXCLUDE:
                    if field.default is not excluded:
                        return excluded if isinstance(field.default, bool) else _config_apply_type(field.default, field)
                    elif field.optional is excluded or not field.optional:
                        raise ConfigMissingMetaFieldException(f"Missing field {field.key}.")
                else:
                    raise MetaInvalidTypeCommandError(f"Invalid field type command: {field_t}")
            elif isinstance(field_t, dict):
                raise MetaTypeBadOptionError(f"Type {TYPE_NAME_BOOLEAN} does not have options.")
            else:
                raise MetaTypeInvalidValueError(f"Type {TYPE_NAME_BOOLEAN} must be specified by {bool.__name__}, {str.__name__}, or {dict.__name__}, got {type(field_t).__name__}: {repr(field_t)}.")
        elif isinstance(v, int):
            return _config_apply_number(v, int, TYPE_NAME_INTEGER, field)
        elif isinstance(v, float):
            return _config_apply_number(v, float, TYPE_NAME_FLOAT, field)
        elif isinstance(v, dict):
            field_t = field.types.get(TYPE_NAME_OBJECT, None)
            if field_t is None:
                raise MetaTypeInvalidException(f"Type \"{TYPE_NAME_BOOLEAN}\" not allowed for field {field.key}.")
            elif isinstance(field_t, bool):
                if field_t:
                    return v
                else:
                    raise MetaTypeInvalidException(f"Type \"{TYPE_NAME_BOOLEAN}\" not allowed for field {field.key}.")
            elif isinstance(field_t, str):
                if field_t == TYPE_COMMAND_EXCLUDE:
                    if field.default is not excluded:
                        return excluded if isinstance(field.default, dict) else _config_apply_type(field.default, field)
                    elif field.optional is excluded or not field.optional:
                        raise ConfigMissingMetaFieldException(f"Missing field {field.key}.")
                else:
                    raise MetaInvalidTypeCommandError(f"Invalid field type command: {field_t}")
            elif isinstance(field_t, dict):
                has = 0
                for option_name in field_t.keys():
                    if option_name != "fields" and option_name != "anyfield":
                        raise MetaTypeBadOptionError(f"Type {TYPE_NAME_OBJECT} does not have option: {option_name}")
                    else:
                        has += 1
                if has > 1:
                    raise MetaTypeBadOptionError(f"Type {TYPE_NAME_OBJECT} cannot specify both options: fields and anyfield")
                elif "fields" in field_t:
                    return config_apply_meta(v, field_t["fields"])
                else: #"anyfield" in field_t
                    fixed_object= {}
                    vfield = MetaField("", types=field_t["anyfield"])
                    for k,item in v.items():
                        applied = _config_apply_type(item, vfield)
                        if applied is not excluded:
                            fixed_object[k] = applied
                    return fixed_object
            else:
                raise MetaTypeInvalidValueError(f"Type {TYPE_NAME_OBJECT} must be specified by {bool.__name__}, {str.__name__}, or {dict.__name__}, got {type(field_t).__name__}: {repr(field_t)}.")
        elif isinstance(v, list):
            return _config_apply_meta_list(v, field)
        else:
            raise ConfigMetaException(f"Value of unsupported type {type(v).__name__}: {v}")


def config_apply_meta(c:dict[str], fields:MetaFieldCollection)->dict[str]:
    fixed_c = {}
    for name, field in fields.items():
        if name in c:
            v = c[name]
            applied = _config_apply_type(v, field)
            if applied is not excluded:
                fixed_c[name] = applied
        elif field.default is not excluded:
            fixed_c[name] = field.default
        elif field.optional is excluded or not field.optional:
            raise ConfigMissingMetaFieldException(f"Missing field {field.key}.")

    #add names from config file that aren't in meta
    for name in (set(c.keys()) - set(fields.keys())):
        fixed_c[name] = c[name]

    return fixed_c

def read_configs(path:str, meta:Meta):
    c = config.read(path)
    if meta.configs is not excluded:
        return config_apply_meta(c, meta.configs)
    return c

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
            plugin = plugins[name] = Plugin(name, ("path", run_file), ("path", meta_file))
            if info:
                plugin.enable()
        elif info and isinstance(info, dict):
            runinfo = info.get("run", None)
            metainfo = info.get("meta", None)
            runnext = info.get("run_next", None)
            dependson = info.get("depends_on", None)

            if runinfo and isinstance(runinfo, dict):
                run_target = runinfo["type"], runinfo["value"]
            else:
                run_target = "path", os.path.join(PLUGINS_DIR, name, "plugin.py")
            
            if metainfo and isinstance(metainfo, dict):
                meta_target = metainfo["type"], metainfo["value"]
            else:
                meta_file = os.path.join(PLUGINS_DIR, name, "plugin.json")
                meta_target = "path", meta_file

            if isinstance(runnext, list):
                run_next = [name for name in runnext if isinstance(name, str)]
            else:
                run_next = None
            
            if isinstance(dependson, list):
                depends_on = [name for name in dependson if isinstance(name, str)]
            else:
                depends_on = None

            plugin = plugins[name] = Plugin(name, run_target, meta_target, run_next=run_next, depends_on=depends_on)

            enabled = info.get("enabled", True)
            if enabled:
                plugin.enable()
            
    return plugins

# def _generate_order_rec(plugin:Plugin|None, plugin_list:dict[str, Plugin], order:list[str], visited:set[str]):
#     if plugin is None:
#         for n, p in plugin_list.items():
#             if n not in order:
#                 _generate_order_rec(p, plugin_list, order, visited)
#     elif plugin.module is not None: #must be enabled
#         for n in plugin.depends_on:
#             if n not in visited:
#                 visited.add(n)
#                 _generate_order_rec(plugin_list[n], plugin_list, order, visited)
#         if plugin.name not in order:
#             order.append(plugin.name)
#             visited.add(plugin.name)
#         for n in plugin.run_next:
#             if n not in visited:
#                 _generate_order_rec(plugin_list[n], plugin_list, order, visited, is_next=True)


def _generate_order_queuesim(plugin_list:dict[str, Plugin]):
    queue = list(plugin_list.values())
    loaded:set[str] = set()
    disabled:set[str] = set()
    order = []
    #make sure all disabled plugins are marked as such first
    for plugin in list(queue):
        if plugin.module is None:
            queue.remove(plugin)
            disabled.add(plugin.name)
    while queue:
        for plugin in list(queue):
            all_loaded = True
            for dn in plugin.depends_on:
                if dn in disabled: #if any are disabled
                    queue = [p for p in queue if p != plugin]
                    all_loaded = False
                    break
                elif all_loaded and dn not in loaded:
                    all_loaded = False
            if all_loaded:
                loaded.add(plugin.name)
                order.append(plugin.name)
                index = queue.index(plugin)
                queue.pop(index)
                if plugin.run_next:
                    i = 0
                    for nn in plugin.run_next:
                        if nn in disabled:
                            continue
                        pn = plugin_list[nn]
                        ii = index + i
                        if queue.index(pn) > ii:
                            queue = [p for i,p in enumerate(list(queue)) if i <= ii or p != pn]
                        queue.insert(ii, pn)
    return order
    

def generate_load_order(plugin_list:dict[str, Plugin])->list[str]:
    # if not plugin_list:
    #     return []
    # order = []
    # _generate_order_rec(None, plugin_list, order, set())
    # return order
    return _generate_order_queuesim(plugin_list)