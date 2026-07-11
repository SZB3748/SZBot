import datafile
from datetime import datetime, timezone
import exiting
import os
import sys
import szlogging
import threading
from tronix import utils
from typing import Callable

logger_backend = szlogging.loggers.Logger()
LOG_DIR = datafile.makepath("logs")
LOG_FILE = os.path.join(LOG_DIR, datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S.log"))

ConsoleMessage = tuple[str|bytes, int]

class MessageBuilder:
    def __init__(self, level:szlogging.levels.Level, interface:szlogging.loggers.LoggerInterface, between_sep="\n"):
        self.level = level
        self.interface = interface
        self.between_sep = between_sep
        self.args = []
        self.kwargs = {}
        self.exception:BaseException = None

    def append(self, *args, **kwargs):
        if args:
            if self.args:
                self.args.append(self.between_sep)
            self.args.extend(args)
        self.kwargs.update(kwargs)

    def set_exception(self, exception:BaseException):
        self.exception = exception

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc is not None:
            return
        if self.exception is None:
            self.interface.log(self.level, *self.args, **self.kwargs)
        else:
            self.interface.log_exception(self.exception, self.level, *self.args, **self.kwargs)

class ConsoleMessageTransformation(szlogging.transforms.Transformation[ConsoleMessage]):
    def __init__(self, inner:Callable[[szlogging.messages.Message], str|bytes], fileno_cb:Callable[[szlogging.messages.Message], int]=lambda msg: int(msg.context.exception is not None) + 1):
        super().__init__(self._makefunc())
        self.inner = inner
        self.fileno_cb = fileno_cb

    def _makefunc(self):
        def func(message:szlogging.messages.Message):
            return self.inner(message), self.fileno_cb(message)
        return func
        

class ConsoleDest(szlogging.destinations.Destination[ConsoleMessage]):
    def __init__(self, name:str, dests:dict[int, Callable[[str|bytes], bool]], threshold_level:szlogging.Level|None=None):
        super().__init__(name, self._makefunc(), threshold_level)
        self.dests = dests

    def _makefunc(self):
        def func(cm:ConsoleMessage):
            b, d = cm
            return self.dests[d](b)
        return func
    
class MainLogger(szlogging.loggers.HumanReadableInterface):
    def _get_callframe(self):
        return 2
    
    def debug(self, *text:str, human_text:str="", **kwargs):
        return self.log(szlogging.levels.DEBUG, *text, human_text=human_text, **kwargs)
    def debug_exception[T:BaseException](self, exception:T, *text:str, human_text:str="", **kwargs):
        if szlogging.loggers.TOP_LEVEL_LOGGER.is_logged_exception_remembered(exception, self):
            return exception
        else:
            return self.log_exception(exception, szlogging.levels.DEBUG, *text, human_text=human_text, **kwargs)
    def info(self, *text:str, human_text:str="", **kwargs):
        return self.log(szlogging.levels.INFO, *text, human_text=human_text, **kwargs)
    def info_exception[T:BaseException](self, exception:T, *text:str, human_text:str="", **kwargs):
        if szlogging.loggers.TOP_LEVEL_LOGGER.is_logged_exception_remembered(exception, self):
            return exception
        else:
            return self.log_exception(exception, szlogging.levels.INFO, *text, human_text=human_text, **kwargs)
    def warn(self, *text:str, human_text:str="", **kwargs):
        return self.log(szlogging.levels.WARN, *text, human_text=human_text, **kwargs)
    def warn_exception[T:BaseException](self, exception:T, *text:str, human_text:str="", **kwargs):
        if szlogging.loggers.TOP_LEVEL_LOGGER.is_logged_exception_remembered(exception, self):
            return exception
        else:
            return self.log_exception(exception, szlogging.levels.WARN, *text, human_text=human_text, **kwargs)
    def error(self, *text:str, human_text:str="", **kwargs):
        return self.log(szlogging.levels.ERROR, *text, human_text=human_text, **kwargs)
    def error_exception[T:BaseException](self, exception:T, *text:str, human_text:str="", **kwargs):
        if szlogging.loggers.TOP_LEVEL_LOGGER.is_logged_exception_remembered(exception, self):
            return exception
        else:
            return self.log_exception(exception, szlogging.levels.ERROR, *text, human_text=human_text, **kwargs)

console = ConsoleDest("console", {
    1: szlogging.destinations.stdout,
    2: szlogging.destinations.stderr
})

def logging_serialize(x):
    return utils.serialize_value(x, type_str=True)

logfile = szlogging.destinations.IODestination("logfile", None)

def init_logfile(mode:str="x", encoding:str|None="utf-8", logf:szlogging.IODestination=logfile):
    logf.f = open(LOG_FILE, mode+"b")
    logf.text_encoding = encoding
    if logf not in main.dests:
        main.dests.append(logf)

PREFIX = "[{time_iso}] <{relfile}:{line_number}>\t{LEVEL}\t"
EXCEPTION_NAME = "{exception_name}"
EXCEPTION_MESSAGE = "{exception_message}"
EXCEPTION_TRACEBACK = "{traceback}"

main = MainLogger(
    logger=logger_backend,
    transformations={
        console.name: ConsoleMessageTransformation(szlogging.transforms.StandardTransformation(prefix=PREFIX, indent=True)),
        logfile.name: szlogging.transforms.JsonTransformation(
            szlogging.transforms.SerializeTransformation(
                message_transform=(_default_transform:=szlogging.transforms.StandardTransformation(prefix=PREFIX, end="")),
                serialize_data=logging_serialize
            )
        )
    },
    default_transform=_default_transform,
    dests=[console],
    top_level_exception_message=f"top level exception:\n{EXCEPTION_TRACEBACK}"
)

logger_running = threading.Event()

def run_logger(hook_sys:bool=True, hook_threading:bool=True, hook_gevent:bool=False):
    @exiting.register_cleanup_listener
    def _cleanup(ctx):
        exiting.unregister_cleanup_listener(_cleanup)
        logger_backend.run = False
        logger_backend.queue._queue_ready.set()

    szlogging.loggers.TOP_LEVEL_LOGGER = logger_backend
    if hook_sys:
        sys.excepthook = szlogging.loggers.global_excepthook
    if hook_threading:
        threading.excepthook = szlogging.loggers.threading_excepthook
    if hook_gevent and szlogging.loggers.gevent is not None:
        szlogging.loggers.gevent.get_hub().handle_error = szlogging.loggers.gevent_excepthook
    
    logger_running.set()
    logger_backend.background_task()

