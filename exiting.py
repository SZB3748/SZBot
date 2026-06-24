import traceback
from typing import Any, Callable
import websocket

class ExitContext:
    def __init__(self, sig:int|None=None, frame=None):
        self.sig = sig
        self.frame = frame

CleanupListener = Callable[[ExitContext], Any]

_cleanup_listener_lookup:set[CleanupListener] = set()
_cleanup_listener_order:list[CleanupListener] = []

def register_cleanup_listener(f:CleanupListener):
    if f not in _cleanup_listener_lookup:
        _cleanup_listener_lookup.add(f)
        _cleanup_listener_order.append(f)
    return f

def unregister_cleanup_listener(f:CleanupListener):
    if f in _cleanup_listener_order:
        _cleanup_listener_lookup.remove(f)
        _cleanup_listener_order.remove(f)

def cleanup(ctx:ExitContext):
    i = 0
    listeners = list(reversed(_cleanup_listener_order))
    for l in listeners:
        try:
            l(ctx)
        except Exception as e:
            traceback.print_exception(e)
        i += 1
    print(f"ran {i} cleanup listener{"s"*bool(i-1)}")

def clear():
    _cleanup_listener_lookup.clear()
    _cleanup_listener_order.clear()

def make_websocket_cleanup(wsa:websocket.WebSocketApp, log_pre:str|None=None, log_post:str|None=None):
    @register_cleanup_listener
    def _cleanup(ctx):
        unregister_cleanup_listener(_cleanup)
        if log_pre is not None:
            print(log_pre)
        wsa.close()
        if log_post is not None:
            print(log_post)
    return _cleanup