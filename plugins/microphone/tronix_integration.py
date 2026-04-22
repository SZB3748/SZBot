from . import handler, webroutes
import aiohttp
import plugins
from tronix import builtins, exceptions, script, utils
from tronix.utils import ScriptFunction, ScriptFunctionParam
from uuid import UUID

_MicrophoneType_attrs = {"name","enabled","format","channels","rate","frames_per_buffer","is_on"}
_remote_addr = None
_remote_secure = None
#NOTE technically a memory leak is possible here, but that would only really be an issue if the remote instance is making a bunch of microphones 
_mic_cache:dict[UUID,handler.Microphone] = {}

s = aiohttp.ClientSession()

class _MicrophoneType(script.ScriptDataType[handler.Microphone]):

    f_construct = ScriptFunction()
    construct = f_construct

    def setattr(self, obj:script.ScriptValue[handler.Microphone], name:str, value):
        if name in _MicrophoneType_attrs:
            if _remote_addr is None:
                ... #TODO update microphone behavior based on the updated value
            else:
                ... #TODO make api call to update microphone value
        self.parent.setattr(obj, name, value)

Microphone = _MicrophoneType("Microphone", handler.Microphone, builtins.BASE_TYPE)

local_f_microphone_fetch = ScriptFunction()
remote_f_microphone_fetch = ScriptFunction()

def local_microphone_list(ctx:script.ScriptContext):
    return script.ScriptValue(builtins.Map_readonly, builtins._rodict_dummy(webroutes.main_handler.mics))

@utils.async_function
async def remote_microphone_list(ctx:script.ScriptContext):
    async with s.put(f"http{"s"*_remote_secure}://{_remote_addr}/api/microphone/list") as r:
        r.raise_for_status()
        data = await r.json()
    rod = builtins._rodict_dummy()
    if isinstance(data, dict):
        for k,v in data.items():
            mid = UUID(k)
            m = _mic_cache.get(mid, None)
            if m is None:
                rod[mid] = _mic_cache[mid] = m = handler.Microphone.__new__(handler.Microphone)
            else:
                rod[mid] = m
            m.__setstate__(v)
    return script.ScriptValue(builtins.Map_readonly, rod)

@local_f_microphone_fetch.overload(ScriptFunctionParam("id", [builtins.String, builtins.UUID]))
def local_microphone_fetch(id:script.ScriptVariable[str|UUID]):
    mid_s = id.get().inner
    if isinstance(mid_s, str):
        try:
            mid = UUID(mid_s)
        except:
            raise exceptions.TBadValue("microphone id cannot be read", parameter="id")
    else:
        mid = mid_s
    mic = webroutes.main_handler.mics.get(mid, None)
    if mic is None:
        return builtins.null
    return script.ScriptValue(Microphone, mic)

@remote_f_microphone_fetch.overload(ScriptFunctionParam("id", [builtins.String, builtins.UUID]))
async def remote_microphone_fetch(id:script.ScriptVariable[str|UUID]):
    mid_s = id.get().inner
    if isinstance(mid_s, str):
        try:
            mid = UUID(mid_s)
        except:
            raise exceptions.TBadValue("microphone id cannot be read", parameter="id")
    else:
        mid = mid_s
    mid_s = str(mid)

    async with s.put(f"http{"s"*_remote_secure}://{_remote_addr}/api/microphone/list") as r:
        r.raise_for_status()
        data = await r.json()
    if isinstance(data, dict):
        mdata = data.get(mid_s, None)
        if isinstance(mdata, dict):
            cached = _mic_cache.get(mid, None)
            if cached is None:
                _mic_cache[mid] = cached = handler.Microphone.__new__(handler.Microphone)
            cached.__setstate__(mdata)
            return script.ScriptValue(Microphone, cached)
    return builtins.null

def activate(api_mode:str, remote:str|None=None, secure:bool=False):
    global _remote_addr, _remote_secure
    if api_mode == plugins.COMPONENT_MODE_REMOTE:
        _remote_addr = remote
        _remote_secure = secure
        script.SCRIPT_FUNCTION_TABLE["microphone_list"] = remote_microphone_list
        script.SCRIPT_FUNCTION_TABLE["microphone_fetch"] = remote_f_microphone_fetch
    else:
        script.SCRIPT_FUNCTION_TABLE["microphone_list"] = local_microphone_list
        script.SCRIPT_FUNCTION_TABLE["microphone_fetch"] = local_f_microphone_fetch
        utils.add_type(Microphone)

def deactivate():
    script.SCRIPT_FUNCTION_TABLE.pop("microphone_list",None)
    script.SCRIPT_FUNCTION_TABLE.pop("microphone_fetch",None)
    utils.remove_type(Microphone)
