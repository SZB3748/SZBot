from datetime import datetime
from types import FrameType
from typing import Self

class SafeFrame:
    @classmethod
    def make(cls, frame:FrameType|Self|None, backframes:int=0):
        if frame is None:
            return None
        elif isinstance(frame, cls):
            return frame
        else:
            return cls(frame, backframes=backframes)
        
    def __init__(self, frame:FrameType, backframes:int=0):
        if backframes:
            self.f_back = SafeFrame.make(frame.f_back, backframes=backframes-1)
        else:
            self.f_back = None
        self.f_code = frame.f_code
        self.f_locals = frame.f_locals.copy()
        self.f_globals = frame.f_globals.copy()
        self.f_builtins = frame.f_builtins.copy()
        self.f_lasti = frame.f_lasti
        self.f_lineno = frame.f_lineno


class Context:
    def __init__(self, now:datetime, frame:FrameType|SafeFrame, args:tuple|None=None, kwargs:dict[str]|None=None, exception:BaseException|None=None):
        self.now = now
        self.frame = frame if isinstance(frame, SafeFrame) else SafeFrame(frame)
        self.args = () if args is None else args
        self.kwargs = {} if kwargs is None else kwargs
        self.exception = exception
    