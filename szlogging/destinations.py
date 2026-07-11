from . import levels
import sys
from typing import Callable, IO

class Destination[T]:
    def __init__(self, name:str, func:Callable[[T], bool], threshold_level:levels.Level|None=None):
        self.name = name
        self.func = func
        self._func = func
        self.threshold_level = threshold_level

    def __call__(self, x:T):
        return self.func(x)

class IODestination(Destination[str|bytes]):
    def __init__(self, name, f:IO[bytes], text_encoding:str|None=None, threshold_level:levels.Level|None=None):
        super().__init__(name, self._makefunc(), threshold_level)
        self.f = f
        self.text_encoding = text_encoding

    def _makefunc(self):
        def func(b:str|bytes):
            if isinstance(b, str):
                if self.text_encoding is None:
                    return False
                b = b.encode(self.text_encoding)
            self.f.write(b)
            self.f.flush()
        return func
    

stdout = IODestination("stdout", sys.stdout.buffer, sys.stdout.encoding)
stderr = IODestination("stderr", sys.stderr.buffer, sys.stderr.encoding)
