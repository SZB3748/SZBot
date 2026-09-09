import hashlib
import json
from typing import Callable

INPUT_TYPES = {"text", "number", "date", "time", "datetime", "color"}

class Field:
    def __init__(self, name:str, input_type:str="text", default:str|None=None, options:dict[str]|None=None):
        self.name = name
        self.default = default
        self.input_type = input_type
        self.options = {} if options is None else options

    def __getstate__(self):
        return dict(
            name=self.name,
            input_type=self.input_type,
            default=self.default,
            options=self.options
        )

    def __setstate__(self, d:dict[str]):
        self.name = str(d["name"])
        self.input_type = str(d["input_type"])
        self.default = None if (dd := d.get("default", None)) is None else str(dd)
        od = d["options"]
        if isinstance(od, dict):
            self.options:dict[str] = od
        else:
            self.options:dict[str] = {}


ResourceList = dict[str, str]
FieldList = dict[str, Field]

#uncontained: no "" or '' or {} or []
FIELD_USE_METHODS = {"plain", "json_value", "json_value_uncontained"}

class _mutible_wrapper:
    __slots__ = "t", "v"
    
    def __init__(self, t:type, v:tuple):
        self.t = t
        self.v = v

    def __hash__(self):
        return hash((self.t, self.v))

    def __eq__(self, value):
        if isinstance(value, _mutible_wrapper):
            return value.t == self.t and value.v == self.v
        elif isinstance(value, tuple):
            return value == self.v
        return super().__eq__(value)


def mutible_wrap(value):
    if isinstance(value, dict):
        return _mutible_wrapper(type(value), tuple(sorted((k, mutible_wrap(v)) for k,v in value.items())))
    elif isinstance(value, (list, tuple)):
        return _mutible_wrapper(type(value), tuple(mutible_wrap(v) for v in value))
    else:
        return value

def mutible_unwrap(value:str|bool|int|float|None|_mutible_wrapper):
    if isinstance(value, _mutible_wrapper):
        if issubclass(value.t, dict):
            return {k:mutible_unwrap(v) for k,v in value.v}
        elif issubclass(value.t, list):
            return [mutible_unwrap(v) for v in value.v]
        elif issubclass(value.t, tuple):
            return tuple(mutible_unwrap(v) for v in value.v)
        else:
            raise TypeError(f"expected dict, list, or tuple, got: {value.t.__name__}")
    else:
        return value

class ReplaceProcess:
    def __init__(self, field_name:str, blank:str, use_method:str="plain", options:dict[str]|None=None):
        self.field_name = field_name
        self.blank = blank
        self.use_method = use_method
        self.options = {} if options is None else options

    def __getstate__(self):
        return dict(
            field_name=self.field_name,
            blank=self.blank,
            use_method=self.use_method,
            options=self.options
        )

    def __setstate__(self, d:dict[str]):
        self.field_name = str(d["field_name"])
        self.blank = str(d["blank"])
        self.use_method = str(d["use_method"])
        options = d["options"]
        if isinstance(options, dict):
            self.options:dict[str] = options

    def generate_key(self):
        return self.field_name, self.blank, self.use_method, tuple(sorted((k, mutible_wrap(v)) for k,v in self.options.items()))

ReplaceProcessList = list[ReplaceProcess]

DESTINATION_MERGE_METHODS = {"new_file", "append_file", "json_insert"}

class Destination:
    def __init__(self, location:str, merge_method:str, unmerge_method:str, merge_options:dict[str]|None=None, unmerge_options:dict[str]|None=None):
        self.location = location
        self.merge_method = merge_method
        self.unmerge_method = unmerge_method
        self.merge_options = {} if merge_options is None else merge_options
        self.unmerge_options = {} if unmerge_options is None else unmerge_options

    def __getstate__(self):
        return dict(
            location=self.location,
            merge_method=self.merge_method,
            unmerge_method=self.unmerge_method,
            merge_options=self.merge_options,
            unmerge_options=self.unmerge_options
        )

    def __setstate__(self, d:dict[str]):
        self.location = str(d["location"])
        self.merge_method = str(d["merge_method"])
        self.unmerge_method = str(d["unmerge_method"])
        mod = d["merge_options"]
        umod = d["unmerge_options"]
        if isinstance(mod, dict):
            self.merge_options:dict[str] = mod
        else:
            self.merge_options:dict[str] = {}
        if isinstance(umod, dict):
            self.unmerge_options:dict[str] = umod
        else:
            self.unmerge_options:dict[str] = {}


class Output:
    def __init__(self, resource_name:str, replace_processes:ReplaceProcessList, destination:Destination, location_replace_processes:ReplaceProcessList):
        self.resource_name = resource_name
        self.replace_processes = replace_processes
        self.destination = destination
        self.location_replace_processes = location_replace_processes

    def __getstate__(self):
        return dict(
            resource_name=self.resource_name,
            replace_processes=[process.__getstate__() for process in self.replace_processes],
            destination=self.destination.__getstate__(),
            location_replace_processes=[process.__getstate__() for process in self.location_replace_processes],
        )

    def __setstate__(self, d:dict[str]):
        rpds = d["replace_processes"]
        rps = []
        if isinstance(rpds, list):
            for rpd in rpds:
                rp = ReplaceProcess.__new__(ReplaceProcess)
                rp.__setstate__(rpd)
                rps.append(rp)
        lrpds = d["location_replace_processes"]
        lrps = []
        if isinstance(lrpds, list):
            for lrpd in lrpds:
                rp = ReplaceProcess.__new__(ReplaceProcess)
                rp.__setstate__(lrpd)
                lrps.append(rp)
        dest = Destination.__new__(Destination)
        dest.__setstate__(d["destination"])
        self.resource_name = str(d["resource_name"])
        self.replace_processes = rps
        self.location_replace_processes = lrps
        self.destination = dest

    def generate_key(self):
        return self.resource_name, tuple(sorted({process.generate_key() for process in self.replace_processes}))

OutputList = list[Output]

def key_to_string(key:tuple, alg:"Callable[[bytes], hashlib._Hash]"=hashlib.sha256):
    return alg(json.dumps(key, sort_keys=True, ensure_ascii=False).encode("utf-8"))
