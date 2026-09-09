import os
import shutil
from typing import Any, Generator, IO
import weakref

StagedFSFlags = int

BOT_SCOPE = os.path.dirname(os.path.dirname(__file__))

FLAG_DIR:StagedFSFlags = StagedFSFlags(1)
FLAG_WRITE:StagedFSFlags = StagedFSFlags(2)
FLAG_DELETE:StagedFSFlags = StagedFSFlags(4)

_ISFILE_MASK = FLAG_DIR|FLAG_DELETE
_ISDIR_MASK = FLAG_DIR|FLAG_WRITE

NO_OP_FILE:StagedFSFlags = 0
NO_OP_DIR:StagedFSFlags = FLAG_DIR

def ISDIR(x:StagedFSFlags):
    return bool(x & _ISDIR_MASK)

def ISFILE(x:StagedFSFlags):
    return not (x & _ISFILE_MASK)

_NO_CHANGE = object()
NOT_FOUND = object()

class StagedFSEntry:
    def __init__(self, flags:StagedFSFlags, fobj:IO[bytes]|None=None):
        self.flags = flags
        self.fobj = fobj

class StagedFSNode:

    __slots__ = "path", "contents", "_parent", "entry", "__weakref__"

    def __init__(self, path:str):
        self.path = path
        self.contents:dict[str, StagedFSNode] = {}
        self._parent:weakref.ReferenceType[StagedFSNode]|None=None
        self.entry:StagedFSEntry|None=None

    @property
    def parent(self):
        if self._parent is None:
            return None
        else:
            return self._parent()

    @parent.setter
    def parent(self, node:"StagedFSNode|None"):
        self._parent = None if node is None else weakref.ref(node)

    def yield_child_entries(self, recursive:bool=True)->"Generator[tuple[str, StagedFSEntry], Any, None]":
        if recursive:
            for node in self.contents.values():
                yield from node.yield_entries()
        else:
            for node in self.contents.values():
                if node.entry is not None:
                    yield node.path, node.entry

    def yield_entries(self):
        if self.entry is not None:
            yield self.path, self.entry
        yield from self.yield_child_entries()

    def _set_entry_prep(self, path:str):
        path = os.path.relpath(path, self.path)
        parts = path.split(os.path.sep)
        cur = self
        for part in parts:
            if part == ".":
                continue
            elif part == "..":
                cur = cur.parent
                if cur is None:
                    ... #TODO error out of scope
                    assert False
            next = cur.contents.get(part, None)
            if next is None:
                if not (cur.entry is None or cur.entry.flags & FLAG_DIR):
                    ... #TODO error cur.path is a file but given path specifies that it is a folder
                    assert False
                next = cur.contents[part] = StagedFSNode(os.path.join(cur.path, part))
                next.parent = cur
            cur = next
        return cur

    def _set_entry_node(self, entry:StagedFSEntry):
        if self.contents and not entry.flags & FLAG_DIR:
            ... #TODO error entry is file but tree specifies contents
        else:
            old, self.entry = self.entry, entry
            return old
        

    def set_entry(self, path:str, entry:StagedFSEntry):
        node = self._set_entry_prep(path)
        return node._set_entry_node(entry)
        

    def _get_node(self, path:str):
        path = os.path.relpath(path, self.path)
        parts = path.split(os.path.sep)
        cur = self
        for part in parts:
            if part == ".":
                continue
            elif part == "..":
                cur = cur.parent
                if cur is None:
                    ... #TODO error out of scope
            next = cur.contents.get(part, None)
            if next is None:
                return None
            cur = next
        return cur

    def get_entry(self, path:str):
        node = self._get_node(path)
        if node is None:
            return NOT_FOUND
        else:
            return node.entry

    def remove_entry(self, path:str):
        node = self._get_node(path)
        if node is None or node.entry is None:
            return False
        if node.entry.fobj is not None:
            node.entry.fobj.close() 
        node.entry = None
        while not node.contents:
            name = os.path.basename(node.path)
            node = node.parent
            if node is None:
                break
            del node.contents[name]
            if node.entry is not None:
                break
        return True

    def delete(self):
        self._parent = None
        if self.entry is not None:
            if self.entry.fobj is not None:
                self.entry.fobj.close()
            self.entry.fobj = None
        for node in self.contents.values():
            node.delete()
        self.contents.clear()



StagedAction = tuple[str, StagedFSFlags]

class StagedFS:
    def __init__(self, root:str=BOT_SCOPE):
        self.tree = StagedFSNode(root)

    def exists(self, path:str, skip_staged:bool=False, check_real:bool=True):
        if skip_staged:
            return os.path.exists(path)
        entry = self.tree.get_entry(path)
        if isinstance(entry, StagedFSEntry):
            return bool(entry.flags & FLAG_WRITE)
        elif check_real:
            return os.path.exists(path)

    def isfile(self, path:str, skip_staged:bool=False, check_real:bool=True):
        if skip_staged:
            return os.path.isfile(path)
        entry = self.tree.get_entry(path)
        if isinstance(entry, StagedFSEntry):
            return ISFILE(entry.flags)
        elif check_real:
            return os.path.isfile(path)
        return False

    def isdir(self, path:str, skip_staged:bool=False, check_real:bool=True):
        if skip_staged:
            return os.path.isdir(path)
        entry = self.tree.get_entry(path)
        if isinstance(entry, StagedFSEntry):
            return ISDIR(entry.flags)
        elif check_real:
            return os.path.isdir(path)
        return False

    def count_dir_contents(self, path:str, skip_staged:bool=False, check_real:bool=True):
        if check_real:
            try:
                contents = set(name for name in os.scandir(path))
            except FileNotFoundError:
                contents = set()
        else:
            contents = set()
        if not skip_staged:
            node = self.tree._get_node(path)
            if node is not None:
                for name in node.contents.keys():
                    contents.add(name)
        return len(contents)

    def writefile(self, path:str, fobj:IO[bytes]|None=_NO_CHANGE):
        node = self.tree._set_entry_prep(path)
        if node.entry is None:
            node._set_entry_node(StagedFSEntry(FLAG_WRITE, fobj))
        elif node.entry.flags & FLAG_DIR:
            raise PermissionError(f"[stagedfs] Permission denied: {repr(path)}")
        else:
            if node.entry.flags & FLAG_DELETE:
                node.entry.flags ^= FLAG_DELETE
            node.entry.flags |= FLAG_WRITE
            if fobj is not _NO_CHANGE:
                node.entry.fobj = fobj
    
    def makedir(self, path:str):
        node = self.tree._set_entry_prep(path)
        if node.entry is None:
            node._set_entry_node(StagedFSEntry(FLAG_WRITE|FLAG_DIR, None))
        elif not (node.entry.flags & FLAG_DIR):
            raise PermissionError(f"[stagedfs] Permission denied: {repr(path)}")
        else:
            node.entry.flags |= FLAG_WRITE

    def rmfile(self, path:str, unlink_fobj:bool=False):
        node = self.tree._get_node(path)
        if node is None:
            node = self.tree._set_entry_prep(path)
            entry = node._set_entry_node(StagedFSEntry(0))
        else:
            entry = node.entry
        if entry is None:
            node.entry = StagedFSEntry(0)
        elif entry.flags & FLAG_DIR:
            raise PermissionError(f"[stagedfs] Permission denied: {repr(path)}")
        else:
            rtv = None
            if unlink_fobj:
                rtv, entry.fobj = entry.fobj, None
            elif entry.fobj is not None:
                entry.fobj.close()
                entry.fobj = None
            if entry.flags & FLAG_WRITE:
                entry.flags ^= FLAG_WRITE
            entry.flags |= FLAG_DELETE
            return rtv

    def rmdir(self, path:str):
        node = self.tree._get_node(path)
        if node is None:
            self.tree.set_entry(path, StagedFSEntry(FLAG_DIR))
        entry = node.entry
        if entry is None:
            node.entry = StagedFSEntry(FLAG_DIR)
        elif not (entry.flags & FLAG_DIR):
            raise PermissionError(f"[stagedfs] Permission denied: {repr(path)}")
        else:
            if entry.fobj is not None:
                entry.fobj.close()
            if entry.flags & FLAG_WRITE:
                entry.flags ^= FLAG_WRITE
            entry.flags |= FLAG_DELETE
            for child in node.contents.values():
                child.delete()
            node.contents.clear()
        
    def discard(self, path:str):
        self.tree.remove_entry(path)

    def link_fobj(self, path:str, fobj:IO[bytes]):
        entry = self.tree.get_entry(path)
        if isinstance(entry, StagedFSEntry):
            old, entry.fobj = entry.fobj, fobj
            return old

    def unlink_fobj(self, path:str):
        entry = self.tree.get_entry(path)
        if isinstance(entry, StagedFSEntry):
            old, entry.fobj = entry.fobj, None
            return old

    def fetch_fobj(self, path:str):
        entry = self.tree.get_entry(path)
        if isinstance(entry, StagedFSEntry):
            return entry.fobj

    def commit(self):
        for path, entry in self.tree.yield_child_entries():
            if entry.flags & FLAG_DIR:
                if entry.flags & FLAG_DELETE:
                    shutil.rmtree(path, ignore_errors=True)
                if entry.flags & FLAG_WRITE:
                    os.makedirs(path, exist_ok=True)
            else:
                if entry.flags & FLAG_DELETE:
                    try:
                        os.remove(path)
                    except FileNotFoundError:
                        pass
                if entry.flags & FLAG_WRITE and entry.fobj is not None:
                    with open(path, "wb+") as fdest, entry.fobj as fsrc:
                        fsrc.seek(0)
                        shutil.copyfileobj(fsrc, fdest)