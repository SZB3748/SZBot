from . import contexts, destinations, levels, messages, queues, transforms
from datetime import datetime
import sys
import threading
from types import TracebackType
from typing import Iterable
import weakref

        
class Logger:
    def __init__(self):
        self.queue = queues.Queue()
        self.run = True
        self.started = False
        self.exceptions:dict[BaseException,set[LoggerInterface]] = {}
        self.registered_exception_handlers:weakref.WeakSet[LoggerInterface] = weakref.WeakSet()

    def remember_logged_exception(self, exception:BaseException, *interfaces:"LoggerInterface"):
        s = self.exceptions.get(exception, None)
        if s is None:
            self.exceptions[exception] = set(interfaces)
        else:
            for inter in interfaces:
                s.add(inter)

    def is_logged_exception_remembered(self, exception:BaseException, interface:"LoggerInterface|None"=None):
        s = self.exceptions.get(exception, None)
        return s is not None and (interface is None or interface in s)
        
    def background_task(self):
        self.started = True
        while self.run:
            self._clean_exceptions()
            self.queue.send_all(block=True)


    def _log_exception(self, value:BaseException, traceback:TracebackType|None):
        memory = self.exceptions.get(value, None)
        if memory is None:
            for interface in self.registered_exception_handlers:
                interface.log_exception(value, TOP_EXCEPTION_LOGGING_LEVEL, interface.top_level_exception_message)
        else:
            for interface in self.registered_exception_handlers:
                if interface not in memory:
                    interface.log_exception(value, TOP_EXCEPTION_LOGGING_LEVEL, interface.top_level_exception_message)

    def _clean_exceptions(self):
        to_remove = []
        for ex in self.exceptions.keys():
            if sys.getrefcount(ex) <= 5:
                to_remove.append(ex)
        for ex in to_remove:
            self.exceptions.pop(ex, None)

class LoggerInterface:
    def __init__(self, logger:Logger, transformations:dict[str, transforms.Transformation], default_transform:transforms.Transformation, dests:Iterable[destinations.Destination], register_error_handling:bool=True, top_level_exception_message:str=""):
        self.logger = logger
        self.transformations = transformations
        self.default_transform = default_transform
        self.dests = list(dests)
        if register_error_handling:
            logger.registered_exception_handlers.add(self)
        self.top_level_exception_message = top_level_exception_message

    
    def _get_callframe(self):
        return 1

    def _generate_outputs(self)->queues.QueueOutputs:
        return [(d, self.transformations.get(d.name, self.default_transform)) for d in self.dests]

    def log(self, level:levels.Level, *args, **kwargs):
        raise NotImplementedError

    def log_exception[T:BaseException](self, exception:T, level:levels.Level, *args, **kwargs)->T:
        raise NotImplementedError


class StandardInterface(LoggerInterface):
    def log(self, level, *args, **kwargs):
        now = datetime.now()
        frame = sys._getframe(self._get_callframe())
        ctx = contexts.Context(now, frame, args, kwargs)
        self.logger.queue.push(messages.Message(level, ctx), self._generate_outputs())

    def log_exception[T:BaseException](self, exception:T, level, *args, **kwargs)->T:
        now = datetime.now()
        if exception.__traceback__ is None:
            frame = sys._getframe(self._get_callframe())
        else:
            frame = exception.__traceback__.tb_frame
        ctx = contexts.Context(now, frame, args, kwargs, exception=exception)
        self.logger.queue.push(messages.Message(level, ctx), self._generate_outputs())
        self.logger.remember_logged_exception(exception, self)
        return exception

class HumanReadableInterface(LoggerInterface):
    def log(self, level:levels.Level, *text:str, human_text:str="", **kwargs):
        now = datetime.now()
        frame = sys._getframe(self._get_callframe())
        kwargs["human_text"] = human_text
        ctx = contexts.Context(now, frame, text, kwargs)
        self.logger.queue.push(messages.Message(level, ctx), self._generate_outputs())
    
    def log_exception[T:BaseException](self, exception:T, level:levels.Level, *text:str, human_text:str="", **kwargs)->T:
        now = datetime.now()
        if exception.__traceback__ is None:
            frame = sys._getframe(self._get_callframe())
        else:
            frame = exception.__traceback__.tb_frame
        kwargs["human_text"] = human_text
        ctx = contexts.Context(now, frame, text, kwargs, exception=exception)
        self.logger.remember_logged_exception(exception, self)
        self.logger.queue.push(messages.Message(level, ctx), self._generate_outputs())
        return exception

TOP_EXCEPTION_LOGGING_LEVEL = levels.ERROR
TOP_LEVEL_LOGGER:Logger = None

#sys.excepthook
def global_excepthook(etype:type[BaseException], value:BaseException, traceback:TracebackType|None):
    try:
        TOP_LEVEL_LOGGER._log_exception(value, traceback)
    except BaseException:
        exc_type, exc_value, exc_tb = sys.exc_info()
        exc_value.__cause__ = value
        print("!!!failed to log exception with szlogging")
        sys.__excepthook__(exc_type, exc_value, exc_tb)

#threading.excepthook   
def threading_excepthook(args:threading.ExceptHookArgs):
    try:
        TOP_LEVEL_LOGGER._log_exception(args.exc_value, args.exc_traceback)
    except BaseException:
        exc_type, exc_value, exc_tb = sys.exc_info()
        exc_value.__cause__ = args.exc_value
        print(f"!!!thread {args.thread} # failed to log exception with szlogging")
        threading.__excepthook__(threading.ExceptHookArgs([exc_type, exc_value, exc_tb, args.thread]))

try:
    import gevent
except ImportError:
    gevent = None
else:
    #gevent.get_hub().handle_error
    def gevent_excepthook(context:object|None, etype:type[BaseException], value:BaseException, tb:TracebackType|None):
        try:
            TOP_LEVEL_LOGGER._log_exception(value, tb)
        except BaseException:
            exc_type, exc_value, exc_tb = sys.exc_info()
            exc_value.__cause__ = value
            print(f"!!!gevent {context} # failed to log exception with szlogging")
            hub = gevent.get_hub()
            type(hub).handle_error(hub, context, exc_type, exc_value, exc_tb)
        
