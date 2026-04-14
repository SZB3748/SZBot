import datafile
import json
import os
import tronix
from typing import Any

ACTIONS_PATH = datafile.makepath("actions.json")

class ActionRequestedValue:
    def __init__(self, name:str, t:type, required:bool=True):
        self.name = name
        self.type = t
        self.required = required
    
    def __getstate__(self):
        if self.type in tronix.script.DATA_TYPE_TABLE:
            t = tronix.script.DATA_TYPE_TABLE[self.type]
        else:
            t = tronix.script.wrap_python_type(self.type)
        return {
            "name": self.name,
            "type" : t.name,
            "required": self.required
        }
    
    def __setstate__(self, d:dict[str]):
        self.name = str(d["name"])
        self.type = tronix.script._map_name_to_type(d["type"]).inner
        self.required = bool(d["required"])

class ActionValueMapping:
    def fill_values(self, *args, **kwargs)->dict[str]:
        raise NotImplementedError
    
    def __getstate__(self):
        raise NotImplementedError

    def __setstate__(self, d):
        raise NotImplementedError

class CommandActionValueMapping(ActionValueMapping):
    def __init__(self, parameter_to_requested_name:dict[str,str], extra_data:dict[str]):
        self.name_map = parameter_to_requested_name
        self.extra_data = extra_data
    
    def fill_values(self, args:dict[str]):
        d = {self.name_map[k]:v for k,v in args.items()}
        d.update(self.extra_data)
        return d
    
    def __getstate__(self):
        return {
            "name_map": self.name_map,
            "extra_data": self.extra_data
        }
    
    def __setstate__(self, d:dict[str]):
        self.name_map:dict[str,str] = d["name_map"]
        self.extra_data:dict[str] = d["extra_data"]

class RewardActionValueMapping(ActionValueMapping):
    def __init__(self, input_name:str, extra_data:dict[str]):
        self.input_name = input_name
        self.extra_data = extra_data
    
    def fill_values(self, input):
        rtv = self.extra_data.copy()
        if input:
            rtv[self.input_name] = input
        elif self.input_name:
            rtv.setdefault(self.input_name, "")
        return rtv
    
    def __getstate__(self):
        return {
            "input_name": self.input_name,
            "extra_data": self.extra_data #TODO everything in here needs to be serializable
        }
    
    def __setstate__(self, d:dict[str]):
        self.input_name:str = d["input_name"]
        self.extra_data:dict[str] = d["extra_data"]

class Action:
    def __init__(self, name:str, script:str, requested_values:dict[str, ActionRequestedValue]|None=None):
        self.name = name
        self.script = script
        self.requested_values = {} if requested_values is None else requested_values

    def __getstate__(self):
        return {
            "name": self.name,
            "script": self.script,
            "requested_values": {k:v.__getstate__() for k,v in self.requested_values.items()}
        }
    
    def __setstate__(self, d:dict[str]):
        if "name" in d:
            self.name = str(d["name"])
        if "script" in d:
            self.script = str(d["script"])
        if "requested_values" in d:
            self.requested_values = r = {}
            xr:dict[str,dict[str]] = d["requested_values"]
            for k,v in xr.items():
                r[k] = rv = ActionRequestedValue.__new__(ActionRequestedValue)
                rv.__setstate__(v)

    def collect_script_values(self, mapped_values:dict[str])->tronix.script.Namespace:
        rtv = {}
        for rv in self.requested_values.values():
            if rv.name in mapped_values:
                value = mapped_values[rv.name]
                if isinstance(value, rv.type):
                    rtv[rv.name] = tronix.script.ScriptVariable(tronix.script.wrap_python_value(value))
                else:
                    ... #TODO error type doesnt match
            elif rv.required:
                ... #TODO error missing required value
        return rtv

script_runner = tronix.utils.ScriptRunner()

def load_action_table(path:str=None)->dict[str, Action]:
    if path is None:
        path = ACTIONS_PATH
    if not os.path.isfile(path):
        return {}
    with open(path) as f:
        d:dict[str,dict[str]] = json.load(f)
    rtv = {}
    for k,v in d.items():
        rtv[k] = action = Action.__new__(Action)
        action.__setstate__(v)
    return rtv

def save_action_table(table:dict[str, Action], path:str=None):
    c = json.dumps({action.name:action.__getstate__() for action in table.values()}, indent=4)
    with open(ACTIONS_PATH if path is None else path, "w") as f:
        f.write(c)

class get_action:
    NO_DEFAULT = object()

    def __init__(self, name:str, default:Any=NO_DEFAULT, update:bool=True, path:str=ACTIONS_PATH):
        self.name = name
        self.default = default
        self.update = update
        self.path = path
        self._table = None
        self._action = None

    def __enter__(self):
        self._table = load_action_table(path=self.path)
        if self.default is self.NO_DEFAULT:
            self._action = self._table[self.name]
        else:
            self._action = self._table.get(self.name, self.default)
        return self._action

    def __exit__(self, exc_type, exc, tb):
        if self.update and isinstance(self._action, Action):
            if self._action.name != self.name:
                if self._action is self._table.get(self.name, None):
                    del self._table[self.name]
                self._table[self._action.name] = self._action
            save_action_table(self._table, path=self.path)

def check_script(raw:str):
    try:
        script_runner._prep(raw)
    except tronix.exceptions.TronixException as e:
        return tronix.utils.generate_exception_help(raw, e)
