from tronix import utils
import threading
from uuid import UUID, uuid4

class Connection:
    def __init__(self, id:UUID, overlay_name:str):
        self._id = id
        self._overlay_name = overlay_name
        self._has_data = threading.Event()
        self._data_lock = threading.Lock()
        self._data = []

    @property
    def id(self):
        return self._id
    
    @property
    def overlay_name(self):
        return self._overlay_name

    def send_data(self, *data):
        with self._data_lock:
            self._data.extend(data)
            self._has_data.set()
    
    def wait_for_data(self, timeout:float|None=None):
        return self._has_data.wait(timeout=timeout)
    
    def dump_data(self, timeout:float|None=None):
        if self.wait_for_data(timeout=timeout):
            with self._data_lock:
                for d in self._data:
                    yield d
                self._data.clear()
                self._has_data.clear()

class ConnectionManager:
    def __init__(self):
        self._connections:dict[UUID, Connection] = {}
        self._name_lookup:dict[str, list[Connection]] = {}

    def new_connection(self, overlay_name:str):
        conn = Connection(uuid4(), overlay_name)
        return self.add_connection(conn)
    
    def add_connection(self, conn:Connection):
        self._connections[conn._id] = conn
        if conn._overlay_name in self._name_lookup:
            self._name_lookup[conn._overlay_name].append(conn)
        else:
            self._name_lookup[conn._overlay_name] = [conn]
        return conn
    
    def drop_connection(self, conn:Connection|UUID):
        if isinstance(conn, Connection):
            name = conn._overlay_name
            conn = conn._id
        else:
            name = None
        self._connections.pop(conn, None)
        if name is None:
            for conns in self._name_lookup.values():
                to_remove = []
                for x in conns:
                    if x._id == conn:
                        to_remove.append(x)
                for x in to_remove:
                    conns.remove(x)
        else:
            conns = self._name_lookup.get(name, None)
            if conns is not None:
                to_remove = []
                for x in conns:
                    if x._id == conn:
                        to_remove.append(x)
                for x in to_remove:
                    conns.remove(x)

    def send_data_to_overlay(self, overlay_name:str, *data):
        conns = self._name_lookup.get(overlay_name, None)
        if conns is not None:
            for conn in conns:
                conn.send_data(*data)
    
    def send_data_to_connection(self, id:UUID, *data):
        conn = self._connections.get(id,None)
        if conn is not None:
            conn.send_data(*data)
    
    def get_connection(self, id:UUID):
        return self._connections.get(id, None)
    
    def get_overlay_connections(self, overlay_name:str):
        conns = self._name_lookup.get(overlay_name, None)
        if conns is None:
            return []
        return conns.copy()
    
default_connection_manager = ConnectionManager()