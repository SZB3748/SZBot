import actions
import inspect
import twitchio
import tronix_twitch_integrations as tti
from tronix import script, utils
from twitchio.ext import commands
from typing import Any, Callable, Self

CommandParameter = tuple[str, type|Any]
EmptyValue = inspect.Parameter.empty
CommandCallback = Callable[...]

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
    def __init__(self, name:str, description:str, signature:CommandSignature, permissions:CommandPermissions):
        self.name = name
        self.description = description
        self.signature = signature
        self.permissions = permissions
    
    def handle(self, *args):
        raise NotImplementedError
    
    def to_twitch_command(self):
        raise NotImplementedError


class ActionCommand(Command):
    def __init__(self, name:str, description:str, signature:CommandSignature, permissions:CommandPermissions, action_name:str, action_mapping:actions.CommandActionValueMapping):
        super().__init__(name, description, signature, permissions)
        self.action_name = action_name
        self.action_mapping = action_mapping

    def handle(self, *args):
        action = actions.action_table.get(self.action_name, None)
        if action is None:
            ... #TODO exception unknown action
        if not self.signature.is_valid():
            ... #TODO exception invalid signature

        script_scope = {}
        if args and isinstance(args[0], commands.Context):
            ctx = args[0]
            script_scope["twitch_context"] = script.ScriptVariable(utils.wrap_python_value(tti.BotScriptContext(ctx.bot, command_ctx=ctx)))
            args = args[1:]

        if len(args) == len(self.signature.params):
            filled_args = [t(arg) if isinstance(t, type) else arg for (_, t), arg in zip(self.signature.params, args)]
        elif len(args) < len(self.signature.params):
            filled_args = [t(arg) if isinstance(t, type) else arg for (_, t), arg in zip(self.signature.params, args)]
            for name in (self.signature.params[i][0] for i in range(len(args), len(self.signature.params))):
                if name in self.signature.defaults:
                    filled_args.append(self.signature.defaults[name])
                else:
                    ... #TODO exception missing required arguments
        else:
            #TODO exception too many arguments
            ...

        filled = self.action_mapping.fill_values({n:v for (n,_), v in zip(self.signature.params, filled_args)})
        script_scope.update(action.collect_script_values(filled))
        s = script.Script(action.script, script_scope)
        return actions.script_runner.run_async(s)
    
    def to_twitch_command(self):
        check = {}
        _sig_p:list[str] = []
        for (n, t) in self.signature.params:
            _sig_p.append(f"{n}:{t.__name__ if isinstance(t, type) else (tt:=type(t)).__new__(tt)}")
        _sig_s:str = ",".join(_sig_p)
        exec(f"def _callback({_sig_s}): pass", check)

        cmd = commands.Command(name=self.name, callback=check["_callback"], aliases=[], bypass_global_guards=False)
        cmd._callback = self.handle
        return cmd

class CallbackCommand(Command):
    @staticmethod
    def create(name:str|None=None, description:str|None=None, signature:CommandSignature|None=None, permissions:CommandPermissions|None=None):
        def decor(callback:CommandCallback):
            nonlocal signature
            if signature is None:
                signature = getattr(callback, COMMAND_SIGNATURE_STORE_ATTR, None)
            return CallbackCommand(
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
        return CallbackCommand(
            callback.__name__ if name is None else name,
            callback.__doc__ if description is None else description,
            CommandSignature.from_function(callback) if signature is None else signature,
            CommandPermissions() if permissions is None else permissions,
            callback
        )

    def __init__(self, name:str, description:str, signature:CommandSignature, permissions:CommandPermissions, callback:CommandCallback, bind=None):
        super().__init__(name, description, signature, permissions)
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
    
    def __call__(self, *args, **kwargs):
        return self.handle(*args, **kwargs)