import actions
import datafile
import inspect
import json
import os
import twitchio
import tronix_twitch_integrations as tti
from tronix import script, utils
from twitchio.ext import commands
from typing import Any, Callable, Self

CommandParameter = tuple[str, type|Any]
EmptyValue = inspect.Parameter.empty
CommandCallback = Callable[..., Any]

COMMAND_TRIGGERS_PATH = datafile.makepath("command_triggers.json")
COMMANDS_PATH = datafile.makepath("commands.json")

type_names = {
    "str": "text",
    "int": "integer",
    "float": "number",
    "bool": "true|false"
}

value_names = {
    True: "true",
    False: "false"
}

COMMAND_SIGNATURE_STORE_ATTR = "_COMMAND_SIGNATURE_STORE"

class CommandPermissions:
    def __init__(self,
                 requires_admin:bool=False, requires_artist:bool=False, requires_broadcaster:bool=False, requires_founder:bool=False,
                 requires_moderator:bool=False, requires_no_audio:bool=False, requires_no_video:bool=False, requires_prime:bool=False, requires_staff:bool=False,
                 requires_subscriber:bool=False, requires_turbo:bool=False, requires_verified:bool=False, requires_vip:bool=False):
        self.requires_admin = requires_admin
        self.requires_artist = requires_artist
        self.requires_broadcaster = requires_broadcaster
        self.requires_founder = requires_founder
        self.requires_moderator = requires_moderator
        self.requires_no_audio = requires_no_audio
        self.requires_no_video = requires_no_video
        self.requires_prime = requires_prime
        self.requires_staff = requires_staff
        self.requires_subscriber = requires_subscriber
        self.requires_turbo = requires_turbo
        self.requires_verified = requires_verified
        self.requires_vip = requires_vip

    def meets_requirements(self, author:twitchio.Chatter|twitchio.PartialUser):
        return not (
            self.requires_admin and not author.admin or self.requires_artist and not author.artist or
            self.requires_broadcaster and not author.broadcaster or self.requires_founder and not author.founder or
            self.requires_moderator and not author.moderator or self.requires_no_audio and not author.no_audio or
            self.requires_no_video and not author.no_video or self.requires_prime and not author.prime or
            self.requires_staff and not author.staff or self.requires_subscriber and not author.subscriber or
            self.requires_turbo and not author.turbo or self.requires_verified and not author._is_verified or
            self.requires_vip and not author.vip
        )
    
    def __getstate__(self):
        return self.__dict__.copy()
    
    def __setstate__(self, d:dict[str, bool]):
        self.__dict__.update(d)

class CommandSignature:
    
    @staticmethod
    def from_function(callback:CommandCallback)->Self:
        sig = inspect.signature(callback)
        sig_params = list(sig.parameters.values())
        sig_param_types = [param.annotation for param in sig_params]

        try:
            start_index = sig_param_types.index(commands.Context) + 1
        except:
            start_index = 0
        
        params = []
        defaults = {}
        for param in (sig_params[i] for i in range(start_index, len(sig_params))):
            params.append((param.name, param.annotation))
            if param.default is not inspect.Parameter.empty:
                defaults[param.name] = param.default
        
        return CommandSignature(params, defaults)

    @staticmethod
    def store(signature:Self|None=None):
        def decor(callback:CommandCallback):
            setattr(callback, COMMAND_SIGNATURE_STORE_ATTR, CommandSignature.from_function(callback) if signature is None else signature)
            return callback
        return decor

    def __init__(self, params:list[CommandParameter], defaults:dict[str]=None):
        self.params = params
        self.defaults = {} if defaults is None else defaults

    def is_valid(self)->bool:
        got_default = False
        for name, _ in self.params:
            if name in self.defaults:
                if not got_default:
                    got_default = True
            elif got_default:
                return False
        return True

    def generate_str(self, prefix:str, name:str):
        usage_hint = [prefix + name]
        for name, t in self.params:
            try:
                d = self.defaults[name]
            except KeyError:
                surround = "<>"
                default_hint = ""
            else:
                surround = "[]"
                default_hint = "" if d is None else f" = {value_names.get(d, d)}"

            
            if t is EmptyValue:
                type_hint = ""
            else:
                type_name = str(getattr(t, "__name__", t))
                type_hint = f" :{type_names.get(type_name, type_name)}"

            usage_hint.append(f"{surround[0]}{name}{type_hint}{default_hint}{surround[1]}")
        return " ".join(usage_hint)
    
    def __getstate__(self)->dict[str]:
        return {
            "params": [[name, type_names.get(t, str(t))] for name, t in self.params],
            "defaults": {name:value_names.get(value, str(value)) for name,value in self.defaults.items()}
        }
    
    def __setstate__(self, d:dict[str]):
        rtypes = {v:k for k,v in type_names.items()}
        rvalues = {v:k for k,v in value_names.items()}
        self.params = [(name, rtypes.get(tname, tname)) for name, tname in d["params"]]
        self.defaults:dict[str] = {name:rvalues.get(vname, vname) for name, vname in d["defaults"].items()}

class Command:
    def __init__(self, name:str, description:str, signature:CommandSignature, permissions:CommandPermissions, enabled:bool=True):
        self.name = name
        self.description = description
        self.signature = signature
        self.permissions = permissions
        self.enabled = enabled

    def __getstate__(self):
        return {
            "name": self.name,
            "description": self.description,
            "signature": self.signature.__getstate__(),
            "permissions": self.permissions.__getstate__(),
            "enabled": self.enabled
        }
    
    def __setstate__(self, d:dict[str]):
        self.name = str(d["name"])
        self.description = str(d["description"])
        self.enabled = bool(d["enabled"])
        signature = CommandSignature.__new__(CommandSignature)
        permissions = CommandPermissions.__new__(CommandPermissions)
        signature.__setstate__(d["signature"])
        permissions.__setstate__(d["permissions"])
        self.signature = signature
        self.permissions = permissions


class CommandTrigger:
    def __init__(self, name:str):
        self.name = name

    def handle(self, *args):
        raise NotImplementedError
    
    def to_twitch_command(self):
        raise NotImplementedError


class ActionCommandTrigger(CommandTrigger):
    def __init__(self, name:str, action_name:str, action_mapping:actions.CommandActionValueMapping):
        super().__init__(name)
        self.action_name = action_name
        self.action_mapping = action_mapping

    def __getstate__(self)->dict[str]:
        return {
            "name": self.name,
            "action_name": self.action_name,
            "action_mapping": self.action_mapping.__getstate__()
        }
    
    def __setstate__(self, d:dict[str]):
        self.name = str(d["name"])
        self.action_name = str(d["action_name"])
        action_mapping = actions.CommandActionValueMapping.__new__(actions.CommandActionValueMapping)
        action_mapping.__setstate__(d["action_mapping"])
        self.action_mapping = action_mapping

    def update(self, other:"ActionCommandTrigger"):
        self.name = other.name
        self.action_name = other.action_name
        self.action_mapping.__setstate__(other.action_mapping.__getstate__())

    def handle(self, *args):
        action = actions.load_action_table().get(self.action_name, None)
        command = load_commands().get(self.name, None)
        if command is None:
            ... #TODO exception could not find command info
        elif action is None:
            ... #TODO exception unknown action
        elif not command.signature.is_valid():
            ... #TODO exception invalid signature

        script_scope = {}
        if args and isinstance(args[0], commands.Context):
            ctx = args[0]
            args = args[1:]
        else:
            ctx = None

        if len(args) == len(command.signature.params):
            filled_args = [t(arg) if isinstance(t, type) else arg for (_, t), arg in zip(command.signature.params, args)]
        elif len(args) < len(command.signature.params):
            filled_args = [t(arg) if isinstance(t, type) else arg for (_, t), arg in zip(command.signature.params, args)]
            for name in (command.signature.params[i][0] for i in range(len(args), len(command.signature.params))):
                if name in command.signature.defaults:
                    filled_args.append(command.signature.defaults[name])
                else:
                    ... #TODO exception missing required arguments
        else:
            ... #TODO exception too many arguments

        filled = self.action_mapping.fill_values({n:v for (n,_), v in zip(command.signature.params, filled_args)})
        script_scope.update(action.collect_script_values(filled))
        s = script.Script(action.script, script_scope)
        
        if action.script_environment is None or actions.match_environment_name(action.script_environment, actions.current_environment_name):
            if ctx is not None:
                script_scope.setdefault(tti.TWITCH_CONTEXT_VAR_NAME, script.ScriptVariable(utils.wrap_python_value(tti.BotScriptContext(ctx.bot, command_ctx=ctx))))
            return actions.script_runner.run_async(s)
        else:
            uid, *_ = actions.enqueue_script(s, action.script_environment)
            async def _wait():
                await actions.wait_script_finish_async(uid)
            return _wait()
    
    def to_twitch_command(self):
        command = load_commands().get(self.name, None)
        if command is None:
            ... #TODO exception could not find command info
        check = globals()
        _sig_p:list[str] = []
        for (n, t) in command.signature.params:
            _sig_p.append(f"{n}:{t.__name__ if isinstance(t, type) else t if isinstance(t, str) else repr((tt:=type(t)).__new__(tt))}")
        _sig_s:str = ",".join(_sig_p)
        exec(f"def _callback(ctx,{_sig_s}): pass", check)
        cb = check["_callback"]
        cb.__name__ = cb.__qualname__ = f"_callback_{self.name}"
        cmd = commands.Command(name=self.name, callback=cb)
        cmd._callback = self.handle
        return cmd

class CallbackCommandTrigger(CommandTrigger):
    @staticmethod
    def create(name:str|None=None, description:str|None=None, signature:CommandSignature|None=None, permissions:CommandPermissions|None=None):
        def decor(callback:CommandCallback):
            nonlocal signature
            if signature is None:
                signature = getattr(callback, COMMAND_SIGNATURE_STORE_ATTR, None)
            return CallbackCommandTrigger(
                callback.__name__ if name is None else name,
                callback.__doc__ if description is None else description,
                CommandSignature.from_function(callback) if signature is None else signature,
                CommandPermissions() if permissions is None else permissions,
                callback
            )
        return decor
        
    @staticmethod
    def new(callback:CommandCallback, name:str|None=None, description:str|None=None, signature:CommandSignature|None=None, permissions:CommandPermissions|None=None):
        if signature is None:
            signature = getattr(callback, COMMAND_SIGNATURE_STORE_ATTR, None)
        return CallbackCommandTrigger(
            callback.__name__ if name is None else name,
            callback.__doc__ if description is None else description,
            CommandSignature.from_function(callback) if signature is None else signature,
            CommandPermissions() if permissions is None else permissions,
            callback
        )

    def __init__(self, name:str, description:str, signature:CommandSignature, permissions:CommandPermissions, callback:CommandCallback, bind=None):
        super().__init__(name)
        self.description = description
        self.signature = signature
        self.permissions = permissions
        self.callback = callback
        self.bind = bind
    
    def handle(self, *args, **kwargs):
        if not self.signature.is_valid():
            ... #TODO exception invalid signature
        if self.bind is None:
            cb = self.callback
        else:
            cb = self.callback.__get__(self.bind, type(self.bind))
        return cb(*args, **kwargs)
    
    def to_twitch_command(self):
        cmd = commands.Command(name=self.name, callback=twitchio.utils.unwrap_function(self.callback), aliases=[], bypass_global_guards=False)
        cmd._callback = self.handle
        return cmd
    
    def generate_command(self):
        return Command(self.name, self.description, self.signature, self.permissions)
    
    def __call__(self, *args, **kwargs):
        return self.handle(*args, **kwargs)
    

def load_command_triggers(path:str=None)->dict[str, ActionCommandTrigger]:
    if path is None:
        path = COMMAND_TRIGGERS_PATH
    if not os.path.isfile(path):
        return {}
    with open(path) as f:
        d:dict[str,dict[str]] = json.load(f)
    rtv = {}
    for k,v in d.items():
        rtv[k] = cmd = ActionCommandTrigger.__new__(ActionCommandTrigger)
        cmd.__setstate__(v)
    return rtv

def save_command_triggers(commands:dict[str, ActionCommandTrigger], path:str=None):
    c = json.dumps({c.name:c.__getstate__() for c in commands.values() if isinstance(c, ActionCommandTrigger)}, indent=4)
    with open(COMMAND_TRIGGERS_PATH if path is None else path, "w") as f:
        f.write(c)

def load_commands(path:str=None)->dict[str, Command]:
    if path is None:
        path = COMMANDS_PATH
    if not os.path.isfile(path):
        return {}
    with open(path) as f:
        d:dict[str,dict[str]] = json.load(f)
    rtv = {}
    for k,v in d.items():
        rtv[k] = cmd = Command.__new__(Command)
        cmd.__setstate__(v)
    return rtv

def save_commands(commands:dict[str, Command], path:str=None):
    c = json.dumps({c.name:c.__getstate__() for c in commands.values() if isinstance(c, Command)}, indent=4)
    with open(COMMANDS_PATH if path is None else path, "w") as f:
        f.write(c)