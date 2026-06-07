import asyncio
import config
import contextlib
import datafile
from datetime import datetime, timezone
import math
import sqlite3
import threading
import traceback
import twitchio
from typing import Any
from uuid import UUID

DEFAULT_ANALYTICS_URI = datafile.makepath("twitch_analytics.sqlite3")

sqlite3.register_adapter(UUID, lambda u: u.bytes)
sqlite3.register_converter("UUID", lambda b: UUID(bytes=b))
sqlite3.register_adapter(datetime, lambda dt: dt.astimezone(timezone.utc).timestamp())
sqlite3.register_converter("DATETIME", lambda f: datetime.fromtimestamp(float(f.decode("utf-8")), timezone.utc))


class sqle_loop_result:
    def __init__(self, _loop:asyncio.AbstractEventLoop=None):
        self.result = None
        self.is_done = False
        self.was_rolled_back = False
        self._loop = _loop
        self.tevent = threading.Event()
        self.aevent = asyncio.Event()

    def wait(self, timeout:float|None=None):
        return self.tevent.wait(timeout=timeout)

    async def wait_async(self, timeout:float|None=None, loop:asyncio.AbstractEventLoop=None):
        if self._loop is None:
            if loop is None:
                loop = asyncio.get_running_loop()
            self._loop = loop
        if timeout is None:
            return await self.aevent.wait()
        else:
            with contextlib.suppress(asyncio.TimeoutError):
                return await asyncio.wait_for(self.aevent.wait(), timeout=timeout)
            return False
            
    def done(self, result, was_rolled_back:bool=False):
        self.result = result
        if self._loop is None:
            self.aevent.set()
        else:
            self._loop.call_soon_threadsafe(self.aevent.set)
        self.tevent.set()
        self.is_done = True
        self.was_rolled_back = was_rolled_back
    
    def wait_for_result(self, timeout:float|None=None):
        x = self.wait(timeout=timeout)
        return self.result, x
    
    async def wait_for_result_async(self, timeout:float|None=None, loop:asyncio.AbstractEventLoop=None):
        x = await self.wait_async(timeout=timeout, loop=loop)
        return self.result, x

SQLEQueueEntry = tuple[int|float, tuple, sqle_loop_result]

_sqle_run = False
_sqle_queue:list[list[SQLEQueueEntry]] = []
_sqle_ready = threading.Event()
_sqle_lock = threading.Lock()

def _get_uri():
    c = config.read()
    v = c.get("Twitch-Analytics-DB-File", None)
    if isinstance(v, str):
        v = v.strip()
        if v:
            return v
    return DEFAULT_ANALYTICS_URI

def sqle_stop():
    global _sqle_run
    _sqle_run = False
    _sqle_ready.set()

def sql_executor_loop_handle():
    global _sqle_run
    _sqle_run = True
    sql_executor_loop()

def sql_executor_loop():
    global _sqle_run
    uri = _get_uri()
    conn = sqlite3.connect(uri, detect_types=sqlite3.PARSE_DECLTYPES, autocommit=True)
    cursor = conn.cursor()

    for _, tablestatement in TABLES.values():
        cursor.execute(tablestatement)

    conn.autocommit = False

    inf = float("inf")

    while _sqle_run:
        _sqle_ready.wait()
        if not _sqle_run:
            break
        new_uri = _get_uri()
        if new_uri != uri:
            conn.close()
            conn = sqlite3.connect(uri, detect_types=sqlite3.PARSE_DECLTYPES, autocommit=False)
        with _sqle_lock:
            q = _sqle_queue.copy()
            _sqle_queue.clear()
            _sqle_ready.clear()
        for transaction in q:
            n_needs_commit = True
            results:list[tuple[sqle_loop_result, Any]] = []
            for query_count, statement, result in transaction:
                try:
                    cursor.execute(statement[0], statement[1:])
                    if query_count == inf or query_count <= 0:
                        results.append((result, cursor.fetchall()))
                    elif query_count > 1:
                        results.append((result, cursor.fetchmany(math.ceil(query_count))))
                    else: #query_count == 1
                        results.append((result, cursor.fetchone()))

                    if n_needs_commit and cursor.rowcount > -1:
                        n_needs_commit = False
                except KeyboardInterrupt:
                    _sqle_run = False
                    conn.close()
                    return
                except Exception as e:
                    traceback.print_exception(e)
                    for _, _, result in transaction:
                        result.done(None, was_rolled_back=True)
                    conn.rollback()
                    break
            else:
                for r, v in results:
                    r.done(v)
                if not n_needs_commit:
                    conn.commit()

class Statistic:
    COLUMN_ID = "id"
    COLUMN_HAPPENED = "happened"

    TABLE_NAME:str = NotImplemented
    COLUMN_NAME_MAP:dict[str, str] = NotImplemented #maps column names to attribute names

    _ALL_NAMES = object()

    @classmethod
    def construct(cls, **kw):
        obj = cls.__new__(cls)
        obj.__setstate__(kw)
        return obj
    
    def __init_subclass__(cls):
        assert cls.TABLE_NAME is not NotImplemented, f"{cls.__qualname__} must have a TABLE_NAME value"
        
    def __init__(self, id:int, happened:datetime):
        self.id = id
        self.happened = happened
    
    def __setstate__(self, d:dict[str]):
        if isinstance(self.COLUMN_NAME_MAP, dict):
            for k, v in d.items():
                self.__dict__[self.COLUMN_NAME_MAP.get(k, k)] = v
        else:
            self.__dict__.update(d)

    def default_query_names(self)->list[str]:
        """Returns the default list of column names to query with."""
        return [self.COLUMN_ID]
    
    def all_names(self)->list[str]:
        return list(self.COLUMN_NAME_MAP.keys()) if isinstance(self.COLUMN_NAME_MAP, dict) else list(self.__dict__.keys())
    
    def all_values(self, _rvmap:dict[str,str]=None)->dict[str]:
        if isinstance(self.COLUMN_NAME_MAP, dict):
            if _rvmap is None:
                _rvmap = {v:k for k,v in self.COLUMN_NAME_MAP.items()}
            return {_rvmap.get(k, k):v for k,v in self.__dict__.items()}
        else:
            return self.__dict__.copy()

    def generate_insert(self, names:list[str]=_ALL_NAMES, table_name:str=None)->str:
        if table_name is None:
            table_name = self.TABLE_NAME
        if names is self._ALL_NAMES:
            names = self.all_names()
        return f"INSERT INTO {table_name} ({", ".join(names)}) VALUES ({", ".join("?" for _ in range(len(names)))})"
    
    def generate_update(self, names:list[str]=_ALL_NAMES, query_names:list[str]=_ALL_NAMES, table_name:str=None)->str:
        if table_name is None:
            table_name = self.TABLE_NAME
        if names is self._ALL_NAMES:
            names = list(self.COLUMN_NAME_MAP.keys()) if isinstance(self.COLUMN_NAME_MAP, dict) else list(self.__dict__.keys())
        if query_names is self._ALL_NAMES:
            query_names = list(self.COLUMN_NAME_MAP.keys()) if isinstance(self.COLUMN_NAME_MAP, dict) else list(self.__dict__.keys())
        return f"UPDATE {table_name} SET {", ".join(f"{name}=?" for name in names)}) VALUES ({", ".join(f"{name}=?" for name in query_names)})"
    
    def generate_query(self, names:list[str]=_ALL_NAMES, query_names:list[str]=_ALL_NAMES, table_name:str=None)->str:
        if table_name is None:
            table_name = self.TABLE_NAME
        if names is self._ALL_NAMES:
            names = list(self.COLUMN_NAME_MAP.keys()) if isinstance(self.COLUMN_NAME_MAP, dict) else list(self.__dict__.keys())
        if query_names is self._ALL_NAMES:
            query_names = list(self.COLUMN_NAME_MAP.keys()) if isinstance(self.COLUMN_NAME_MAP, dict) else list(self.__dict__.keys())
        return f"SELECT {", ".join(names)} FROM {table_name} WHERE {", ".join(f"{name}=?" for name in query_names)}"
    
    def generate_delete(self, query_names:list[str]=_ALL_NAMES, table_name:str=None)->str:
        if table_name is None:
            table_name = self.TABLE_NAME
        if query_names is self._ALL_NAMES:
            query_names = list(self.COLUMN_NAME_MAP.keys()) if isinstance(self.COLUMN_NAME_MAP, dict) else list(self.__dict__.keys())
        return f"DELETE FROM {table_name} WHERE {", ".join(f"{name}=?" for name in query_names)}"


class Transaction:
    def __init__(self):
        self.queued:list[SQLEQueueEntry] = []

    def execute_statement(self, statement:str, *values, query_count:int|float=float("inf")):
        entry = _create_entry(query_count, statement, *values)
        self.queued.append(entry)
        return entry[-1]

    def insert_stat(self, t:Statistic, names:list[str]=..., is_column_names:bool=True, table_name:str=None):
        entry = _insert_stat(t, names=names, is_column_names=is_column_names, table_name=table_name)
        self.queued.append(entry)
        return entry[-1]

    def update_stat(self, t:Statistic, names:list[str]=..., query_names:list[str]=..., is_column_names:bool=True, table_name:str=None):
        entry = _update_stat(t, names=names, query_names=query_names, is_column_names=is_column_names, table_name=table_name)
        self.queued.append(entry)
        return entry[-1]

    def query_stat(self, t:Statistic, names:list[str]=..., query_names:list[str]=..., is_column_names:bool=True, query_count:int|float=float("inf"), table_name:str=None):
        entry = _query_stat(t, names=names, query_names=query_names, is_column_names=is_column_names, query_count=query_count, table_name=table_name)
        self.queued.append(entry)
        return entry[-1]
    
    def query_row_stat(self, t:Statistic, names:list[str]=..., query_names:list[str]=..., is_column_names:bool=True, table_name:str=None):
        entry = _query_stat(t, names=names, query_names=query_names, is_column_names=is_column_names, query_count=1, table_name=table_name)
        self.queued.append(entry)
        return entry[-1]

    def delete_stat(self, t:Statistic, query_names:list[str]=..., is_column_names:bool=True, table_name:str=None):
        entry = _delete_stat(t, query_names=query_names, is_column_names=is_column_names, table_name=table_name)
        self.queued.append(entry)
        return entry[-1]
    
    def rollback(self):
        self.queued.clear()

    def commit(self):
        _queue_entries(*self.queued)

TABLES:dict[str,tuple[Statistic, str]] = {}

def add_table(stat_type:type[Statistic], table_statement:str):
    TABLES[stat_type.TABLE_NAME] = stat_type, table_statement

def _queue_entries(*entries:tuple[int, tuple, sqle_loop_result]):
    if _sqle_run:
        with _sqle_lock:
            _sqle_queue.append(entries)
            _sqle_ready.set()

def _create_entry(q:int, s:str, *args):
    return q, (s, *args), sqle_loop_result()

def _prep_insert_stat(t:Statistic, names:list[str], table_name:str):
    return t.generate_insert(names=names, table_name=table_name)

def _prep_update_stat(t:Statistic, names:list[str], query_names:list[str], table_name:str):
    return t.generate_update(names=names, query_names=query_names, table_name=table_name)

def _prep_query_stat(t:Statistic, names:list[str], query_names:list[str], table_name:str):
    return t.generate_query(names=names, query_names=query_names, table_name=table_name)

def _prep_delete_stat(t:Statistic, query_names:list[str], table_name:str):
    return t.generate_delete(query_names=query_names, table_name=table_name)

def _insert_stat(t:Statistic, names:list[str]=..., is_column_names:bool=True, table_name:str=None):
    rmap = {} if t.COLUMN_NAME_MAP is NotImplemented else {attr:column for column, attr in t.COLUMN_NAME_MAP.items()}
    values = t.all_values(_rvmap=rmap)
    if names is ...:
        names = t.all_names()
    elif not is_column_names:
        names = [rmap.get(name,name) for name in names]
    
    common = set(names) & set(values.keys())
    names = [name for name in names if name in common]

    statement = _prep_insert_stat(t, names=names, table_name=table_name)
    return _create_entry(0, statement, *(values[k] for k in names))

def _update_stat(t:Statistic, names:list[str]=..., query_names:list[str]=..., is_column_names:bool=True, table_name:str=None):
    rmap = {} if t.COLUMN_NAME_MAP is NotImplemented else {attr:column for column, attr in t.COLUMN_NAME_MAP.items()}
    values = t.all_values(_rvmap=rmap)
    if names is ...:
        names = t.all_names()
    else:
        names = None
    if query_names is ...:
        query_names = t.default_query_names()
    else:
        query_names = None
    
    if not is_column_names:
        if names is None:
            names = [rmap.get(name,name) for name in names]
        if query_names is None:
            query_names = [rmap.get(name,name) for name in query_names]

    common = set(query_names) & set(values.keys())
    names = [name for name in names if name in common]
    query_names = [name for name in query_names if name in common]
    
    statement = _prep_update_stat(t, names=names, query_names=query_names, table_name=table_name)
    return _create_entry(0, statement, *(values[name] for name in names), *(values[k] for k in names))

def _query_stat(t:Statistic, names:list[str]=..., query_names:list[str]=..., is_column_names:bool=True, query_count:int|float=float("inf"), table_name:str=None):
    rmap = {} if t.COLUMN_NAME_MAP is NotImplemented else {attr:column for column, attr in t.COLUMN_NAME_MAP.items()}
    values = t.all_values(_rvmap=rmap)
    if names is ...:
        names = t.all_names()
    else:
        names = None
    if query_names is ...:
        query_names = t.default_query_names()
    else:
        query_names = None
    
    if not is_column_names:
        if names is None:
            names = [rmap.get(name,name) for name in names]
        if query_names is None:
            query_names = [rmap.get(name,name) for name in query_names]

    common = set(query_names) & set(values.keys())
    names = [name for name in names if name in common]
    query_names = [name for name in query_names if name in common]
    
    statement = _prep_query_stat(t, names=names, query_names=query_names, table_name=table_name)
    return _create_entry(query_count, statement, *(values[name] for name in names), *(values[k] for k in names))

def _delete_stat(t:Statistic, query_names:list[str]=..., is_column_names:bool=True, table_name:str=None):
    rmap = {} if t.COLUMN_NAME_MAP is NotImplemented else {attr:column for column, attr in t.COLUMN_NAME_MAP.items()}
    values = t.all_values(_rvmap=rmap)
    if query_names is ...:
        query_names = t.default_query_names()
    else:
        query_names = None
    
    if not is_column_names:
        if query_names is None:
            query_names = [rmap.get(name,name) for name in query_names]
    
    statement = _prep_delete_stat(t, query_names=query_names, table_name=table_name)
    return _create_entry(0, statement, *(values[k] for k in query_names))


def execute_statement(statement:str, *values, query_count:int|float=float("inf"), timeout:float|None=None):
    entry = _create_entry(query_count, statement, *values)
    _queue_entries(entry)
    x = entry[-1]
    if timeout is None or timeout > 0:
        x.wait(timeout=timeout)
    return x

def insert_stat(t:Statistic, names:list[str]=..., is_column_names:bool=True, table_name:str=None, timeout:float|None=None):
    entry = _insert_stat(t, names=names, is_column_names=is_column_names, table_name=table_name)
    _queue_entries(entry)
    x = entry[-1]
    if timeout is None or timeout > 0:
        x.wait(timeout=timeout)
    return x

def update_stat(t:Statistic, names:list[str]=..., query_names:list[str]=..., is_column_names:bool=True, table_name:str=None, timeout:float|None=None):
    entry = _update_stat(t, names=names, query_names=query_names, is_column_names=is_column_names, table_name=table_name)
    _queue_entries(entry)
    x = entry[-1]
    if timeout is None or timeout > 0:
        x.wait(timeout=timeout)
    return x

def query_stat(t:Statistic, names:list[str]=..., query_names:list[str]=..., is_column_names:bool=True, query_count:int|float=float("inf"), table_name:str=None, timeout:float|None=None):
    entry = _query_stat(t, names=names, query_names=query_names, is_column_names=is_column_names, query_count=query_count, table_name=table_name)
    _queue_entries(entry)
    x = entry[-1]
    if timeout is None or timeout > 0:
        x.wait(timeout=timeout)
    return x

def query_row_stat(t:Statistic, names:list[str]=..., query_names:list[str]=..., is_column_names:bool=True, table_name:str=None, timeout:float|None=None):
    entry = _query_stat(t, names=names, query_names=query_names, is_column_names=is_column_names, query_count=1, table_name=table_name)
    _queue_entries(entry)
    x = entry[-1]
    if timeout is None or timeout > 0:
        x.wait(timeout=timeout)
    return x

def delete_stat(t:Statistic, query_names:list[str]=..., is_column_names:bool=True, table_name:str=None, timeout:float|None=None):
    entry = _delete_stat(t, query_names=query_names, is_column_names=is_column_names, table_name=table_name)
    _queue_entries(entry)
    x = entry[-1]
    if timeout is None or timeout > 0:
        x.wait(timeout=timeout)
    return x

async def execute_statement_async(statement:str, *values, query_count:int|float=float("inf"), timeout:float|None=None):
    entry = _create_entry(query_count, statement, *values)
    _queue_entries(entry)
    x = entry[-1]
    if timeout is None or timeout > 0:
        await x.wait_async(timeout=timeout)
    return x

async def insert_stat_async(t:Statistic, names:list[str]=..., is_column_names:bool=True, table_name:str=None, timeout:float|None=None):
    entry = _insert_stat(t, names=names, is_column_names=is_column_names, table_name=table_name)
    _queue_entries(entry)
    x = entry[-1]
    if timeout is None or timeout > 0:
        await x.wait_async(timeout=timeout)
    return x

async def update_stat_async(t:Statistic, names:list[str]=..., query_names:list[str]=..., is_column_names:bool=True, table_name:str=None, timeout:float|None=None):
    entry = _update_stat(t, names=names, query_names=query_names, is_column_names=is_column_names, table_name=table_name)
    _queue_entries(entry)
    x = entry[-1]
    if timeout is None or timeout > 0:
        await x.wait_async(timeout=timeout)
    return x

async def query_stat_async(t:Statistic, names:list[str]=..., query_names:list[str]=..., is_column_names:bool=True, query_count:int|float=float("inf"), table_name:str=None, timeout:float|None=None):
    entry = _query_stat(t, names=names, query_names=query_names, is_column_names=is_column_names, query_count=query_count, table_name=table_name)
    _queue_entries(entry)
    x = entry[-1]
    if timeout is None or timeout > 0:
        await x.wait_async(timeout=timeout)
    return x

async def query_row_stat_async(t:Statistic, names:list[str]=..., query_names:list[str]=..., is_column_names:bool=True, table_name:str=None, timeout:float|None=None):
    entry = _query_stat(t, names=names, query_names=query_names, is_column_names=is_column_names, query_count=1, table_name=table_name)
    _queue_entries(entry)
    x = entry[-1]
    if timeout is None or timeout > 0:
        await x.wait_async(timeout=timeout)
    return x

async def delete_stat_async(t:Statistic, query_names:list[str]=..., is_column_names:bool=True, table_name:str=None, timeout:float|None=None):
    entry = _delete_stat(t, query_names=query_names, is_column_names=is_column_names, table_name=table_name)
    _queue_entries(entry)
    x = entry[-1]
    if timeout is None or timeout > 0:
        await x.wait_async(timeout=timeout)
    return x


async def joint_wait_results(*results:sqle_loop_result, timeout:float|None=None):
    loop = asyncio.get_running_loop()
    return await asyncio.gather(*(result.wait_for_result_async(timeout=timeout, loop=loop) for result in results))

class StreamStartStat(Statistic):

    COLUMN_BROADCASTER_ID = "broadcaster_id"
    COLUMN_STREAM_TYPE = "stream_type"

    TABLE_NAME = "twitch_stream_starts"
    COLUMN_NAME_MAP = {
        Statistic.COLUMN_ID: "id",
        Statistic.COLUMN_HAPPENED: "happened",
        COLUMN_BROADCASTER_ID: "broadcaster_id",
        COLUMN_STREAM_TYPE: "stream_type"
    }

    @staticmethod
    def from_data(payload:twitchio.StreamOnline):
        return StreamStartStat.construct(happened=payload.started_at, broadcaster_id=int(payload.broadcaster.id), stream_type=payload.type)

    def __init__(self, id:int, happened:datetime, broadcaster_id:int, stream_type:str):
        super().__init__(id=id, happened=happened)
        self.broadcaster_id = broadcaster_id
        self.stream_type = stream_type

class StreamEndStat(Statistic):

    COLUMN_BROADCASTER_ID = "broadcaster_id"

    TABLE_NAME = "twitch_stream_ends"
    COLUMN_NAME_MAP = {
        Statistic.COLUMN_ID: "id",
        Statistic.COLUMN_HAPPENED: "happened",
        COLUMN_BROADCASTER_ID: "broadcaster_id"
    }

    @staticmethod
    def from_data(payload:twitchio.StreamOffline):
        return StreamEndStat.construct(happened=payload.timestamp, broadcaster_id=int(payload.broadcaster.id))

    def __init__(self, id:int, happened:datetime, broadcaster_id:int, stream_type:str):
        super().__init__(id=id, happened=happened)
        self.broadcaster_id = broadcaster_id
        self.stream_type = stream_type

class MessageStat(Statistic):

    COLUMN_BROADCASTER_ID = "broadcaster_id"
    COLUMN_AUTHOR_ID = "author_id"
    COLUMN_MESSAGE_ID = "message_id"

    TABLE_NAME = "twitch_messages"
    COLUMN_NAME_MAP = {
        Statistic.COLUMN_ID: "id",
        Statistic.COLUMN_HAPPENED: "happened",
        COLUMN_BROADCASTER_ID: "broadcaster_id",
        COLUMN_AUTHOR_ID: "author_id",
        COLUMN_MESSAGE_ID: "message_id"
    }

    @staticmethod
    def from_data(msg:twitchio.ChatMessage):
        return MessageStat.construct(happened=msg.timestamp, broadcaster_id=int(msg.broadcaster.id), author_id=int(msg.chatter.id), message_id=UUID(msg.id))

    def __init__(self, id:int, happened:datetime, broadcaster_id:int, author_id:int, message_id:UUID):
        super().__init__(id=id, happened=happened)
        self.broadcaster_id = broadcaster_id
        self.author_id = author_id
        self.message_id = message_id

class RedeemStat(Statistic):

    COLUMN_BROADCASTER_ID = "broadcaster_id"
    COLUMN_AUTHOR_ID = "author_id"
    COLUMN_REWARD_ID = "reward_id"
    COLUMN_REWARD_TITLE = "reward_title"
    COLUMN_REDEEM_ID = "redeem_id"
    COLUMN_REDEEM_TEXT = "redeem_text"

    TABLE_NAME = "twitch_redeems"
    COLUMN_NAME_MAP = {
        Statistic.COLUMN_ID: "id",
        Statistic.COLUMN_HAPPENED: "happened",
        COLUMN_BROADCASTER_ID: "broadcaster_id",
        COLUMN_AUTHOR_ID: "author_id",
        COLUMN_REWARD_ID: "reward_id",
        COLUMN_REWARD_TITLE: "reward_title",
        COLUMN_REDEEM_ID: "redeem_id",
        COLUMN_REDEEM_TEXT: "redeem_text"
    }

    @staticmethod
    def from_data(redeem:twitchio.ChannelPointsRedemptionAdd):
        return RedeemStat.construct(happened=redeem.timestamp, broadcaster_id=int(redeem.broadcaster.id), author_id=int(redeem.user.id),
                           reward_id=UUID(redeem.reward.id), reward_title=redeem.reward.title, redeem_id=UUID(redeem.id), redeem_text=redeem.user_input)

    def __init__(self, id:int, happened:datetime, broadcaster_id:int, author_id:int, reward_id:UUID, reward_title:str, redeem_id:UUID, redeem_text:str=""):
        super().__init__(id=id, happened=happened)
        self.broadcaster_id = broadcaster_id
        self.author_id = author_id
        self.reward_id = reward_id
        self.reward_title = reward_title
        self.redeem_id = redeem_id
        self.redeem_text = redeem_text


class RaidStat(Statistic):

    COLUMN_FROM_ID = "from_id"
    COLUMN_TO_ID = "to_id"
    COLUMN_VIEW_COUNT = "view_count"

    TABLE_NAME = "twitch_raids"
    COLUMN_NAME_MAP = {
        Statistic.COLUMN_ID: "id",
        Statistic.COLUMN_HAPPENED: "happened",
        COLUMN_FROM_ID: "from_id",
        COLUMN_TO_ID: "to_id",
        COLUMN_VIEW_COUNT: "view_count"
    }

    @staticmethod
    def from_data(raid:twitchio.ChannelRaid, happened:datetime|None=None):
        return RaidStat.construct(
            happened=datetime.now(timezone.utc) if happened is None else happened,
            from_id=int(raid.from_broadcaster.id), to_id=int(raid.to_broadcaster.id), view_count=raid.viewer_count
        )

    def __init__(self, id:int, happened:datetime, from_id:int, to_id:int, view_count:int):
        super().__init__(id, happened)
        self.from_id = from_id
        self.to_id = to_id
        self.view_count = view_count

add_table(StreamStartStat, f"""\
CREATE TABLE IF NOT EXISTS {StreamStartStat.TABLE_NAME} (
    {StreamStartStat.COLUMN_ID} INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    {StreamStartStat.COLUMN_HAPPENED} DATETIME NOT NULL,
    {StreamStartStat.COLUMN_BROADCASTER_ID} INTEGER NOT NULL,
    {StreamStartStat.COLUMN_STREAM_TYPE} TEXT NOT NULL
)
""")

add_table(StreamEndStat, f"""\
CREATE TABLE IF NOT EXISTS {StreamEndStat.TABLE_NAME} (
    {StreamEndStat.COLUMN_ID} INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    {StreamEndStat.COLUMN_HAPPENED} DATETIME NOT NULL,
    {StreamEndStat.COLUMN_BROADCASTER_ID} INTEGER NOT NULL
)
""")

add_table(MessageStat, f"""\
CREATE TABLE IF NOT EXISTS {MessageStat.TABLE_NAME} (
    {MessageStat.COLUMN_ID} INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    {MessageStat.COLUMN_HAPPENED} DATETIME NOT NULL,
    {MessageStat.COLUMN_BROADCASTER_ID} INTEGER NOT NULL,
    {MessageStat.COLUMN_AUTHOR_ID} INTEGER NOT NULL,
    {MessageStat.COLUMN_MESSAGE_ID} UUID NOT NULL
)
""")

add_table(RedeemStat, f"""\
CREATE TABLE IF NOT EXISTS {RedeemStat.TABLE_NAME} (
    {RedeemStat.COLUMN_ID} INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    {RedeemStat.COLUMN_HAPPENED} DATETIME NOT NULL,
    {RedeemStat.COLUMN_BROADCASTER_ID} INTEGER NOT NULL,
    {RedeemStat.COLUMN_AUTHOR_ID} INTEGER NOT NULL,
    {RedeemStat.COLUMN_REWARD_ID} UUID NOT NULL,
    {RedeemStat.COLUMN_REWARD_TITLE} TEXT NOT NULL,
    {RedeemStat.COLUMN_REDEEM_ID} UUID NOT NULL,
    {RedeemStat.COLUMN_REDEEM_TEXT} TEXT NOT NULL
)
""")

add_table(RaidStat, f"""\
CREATE TABLE IF NOT EXISTS {RaidStat.TABLE_NAME} (
    {RaidStat.COLUMN_ID} INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    {RaidStat.COLUMN_HAPPENED} DATETIME NOT NULL,
    {RaidStat.COLUMN_FROM_ID} INTEGER NOT NULL,
    {RaidStat.COLUMN_TO_ID} INTEGER NOT NULL,
    {RaidStat.COLUMN_VIEW_COUNT} INTEGER NOT NULL
)
""")