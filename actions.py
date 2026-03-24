import tronix
import tronix.script

class ActionRequestedValue:
    def __init__(self, name:str, t:type, required:bool=True):
        self.name = name
        self.type = t
        self.required = required

class ActionValueMapping:
    def fill_values(self, *args, **kwargs)->dict[str]:
        raise NotImplementedError
    
    def __getstate__(self):
        raise NotImplementedError

    def __setstate__(self, d):
        raise NotImplementedError

class CommandActionValueMapping(ActionValueMapping):
    def __init__(self, parameter_to_requested_name:dict[str,str]):
        self.name_map = parameter_to_requested_name
    
    def fill_values(self, args:dict[str]):
        return {self.name_map[k]:v for k,v in args.items()}
    
    def __getstate__(self):
        return {
            "name_map": self.name_map
        }
    
    def __setstate__(self, d:dict[str]):
        self.name_map:dict[str,str] = d["name_map"]

class RewardActionValueMapping(ActionValueMapping):
    def __init__(self, input_name:str):
        self.input_name = input_name
    
    def fill_values(self, input):
        return {self.input_name:input}
    
    def __getstate__(self):
        return {
            "input_name": self.input_name
        }
    
    def __setstate__(self, d:dict[str]):
        self.input_name:str = d["input_name"]

class Action:
    def __init__(self, name:str, script:str, requested_values:dict[str, ActionRequestedValue]|None=None):
        self.name = name
        self.script = script
        self.requested_values = {} if requested_values is None else requested_values

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

action_table:dict[str, Action] = {}

script_runner = tronix.utils.ScriptRunner()