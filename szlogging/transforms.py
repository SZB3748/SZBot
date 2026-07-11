from . import messages
import json
import os
import traceback
from typing import Any, Callable

class Transformation[T]:
    def __init__(self, func:Callable[[messages.Message], T]):
        self.func = func

    def __call__(self, message:messages.Message):
        return self.func(message)
    
class StandardTransformation(Transformation[str]):
    def __init__(self, prefix="", sep=" ", end="\n", indent:bool=False):
        super().__init__(self._makefunc())
        self.prefix = prefix
        self.sep = sep
        self.end = end
        self.indent = indent

    def _fill_data(self, message:messages.Message):
        dt = message.context.now
        tz = dt.tzinfo
        if tz is None:
            dt = dt.astimezone()
            tz = dt.tzinfo
        tzo = int(tz.utcoffset(dt).total_seconds()/3600)
        d = dict(
            level=message.level.name.lower(),
            LEVEL=message.level.name.upper(),
            time_iso=dt.isoformat(),
            time_year=str(dt.year),
            time_month=str(dt.month),
            time_day=str(dt.day),
            time_hour=str(dt.hour),
            time_minute=str(dt.minute),
            time_second=str(dt.second),
            timezone=dt.tzname(),
            timezone_offset=f"{tzo:03d}" if tzo < 0 else f"{tzo:02d}",
            file=(filep:=message.context.frame.f_code.co_filename),
            relfile=os.path.relpath(filep),
            filename=os.path.basename(filep),
            line_number=str(message.context.frame.f_lineno)
        )
        e = message.context.exception
        if e is None:
            d.update(
                exception_name="",
                exception_message="",
                exception_file="",
                exception_filename="",
                exception_line_number="",
                traceback=""
            )
        else:
            d.update(
                exception_name=type(e).__name__,
                exception_message=str(e)
            )
            t = e.__traceback__
            if t is None:
                d.update(
                    exception_file="",
                    exception_filename="",
                    exception_line_number="",
                    traceback=""
                )
            else:
                d.update(
                    exception_file=(efilep:=t.tb_frame.f_code.co_filename),
                    exception_relfile=os.path.relpath(efilep),
                    exception_filename=os.path.basename(efilep),
                    exception_line_number=t.tb_lineno,
                    traceback="".join(traceback.format_exception(e))
                )
        d.update(message.context.kwargs)
        return d

    def _makefunc(self):
        def func(message:messages.Message):
            d = self._fill_data(message)
            sep = self.sep.format_map(d)
            end = self.end.format_map(d)
            p = self.prefix.format(**d)
            if self.indent and self.prefix:
                b = f"{sep.join(a.format_map(d) if isinstance(a, str) else str(a) for a in message.context.args)}{end}"
                s = p + b
                if s.find("\n", 0, len(s)-1) >= 0:
                    w = " " * len(p)
                    s = "\n".join(w+x if i and x else x for i, x in enumerate(s.split("\n")))
            else:
                s = f"{p}{sep.join(a.format_map(d) if isinstance(a, str) else str(a) for a in message.context.args)}{end}"
            return s
        return func
    
class SerializeTransformation(Transformation[dict[str]]):
    def __init__(self, message_transform:Callable[[messages.Message], str], serialize_data:Callable[[dict[str]], Any]=lambda d: d):
        super().__init__(self._makefunc())
        self.message_transform = message_transform
        self.serialize_data = serialize_data

    def _fill_data(self, message:messages.Message):
        dt = message.context.now
        if dt.tzinfo is None:
            dt = dt.astimezone()
        
        d = dict(
            time=dt.isoformat(),
            file=message.context.frame.f_code.co_filename,
            line_number=message.context.frame.f_lineno,
        )
        e = message.context.exception
        if e is None:
            d["exception"] = None
        else:
            d["exception"] = exception = dict(
                name=type(e).__name__,
                message=str(e)
            )
            t = e.__traceback__
            if t is None:
                exception.update(
                    file=None,
                    line_number=None,
                    traceback=None
                )
            else:
                exception.update(
                    file=t.tb_frame.f_code.co_filename,
                    line_number=t.tb_lineno,
                    traceback="".join(traceback.format_exception(e))
                )
        d.update(message.context.kwargs)
        return d

    def _makefunc(self):
        def func(message:messages.Message):
            m = dict(text=self.message_transform(message), data=self.serialize_data(self._fill_data(message)))
            return m
        return func

class JsonTransformation(Transformation[str]):
    def __init__(self, serializer:Callable[[messages.Message], Any], end="\n", json_options:dict[str]|None=None):
        super().__init__(self._makefunc())
        self.serializer = serializer
        self.end = end
        self.json_options = {} if json_options is None else json_options
    
    def _makefunc(self):
        def func(message:messages.Message):
            return f"{json.dumps(self.serializer(message), **self.json_options)}{self.end}"
        return func
