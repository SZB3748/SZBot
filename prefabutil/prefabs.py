from . import replacement as rpmt, stagedfs
import datafile
import json
import logenv
import os
import re
import shutil
import sys
import tempfile
from typing import Any, Callable, IO
import zipfile

DEFAULT_PREFAB_INST_COMPRESSION_LEVEL = 2
DEFAULT_PREFAB_INST_HEADER_ENCODING = "utf-8"

PREFABS_DIR = os.path.join(stagedfs.BOT_SCOPE, "prefabs")
PREFAB_INSTANCE_DIR = datafile.makepath("prefab_instances")

try:
    import zlib
except:
    zlib = None

class PrefabMeta:

    def __init__(self, name:str, version:str, authors:list[str], description:str, display_name:str, creation_date:str, version_date:str, contact:str):
        self.name = name
        self.version = version
        self.authors = authors
        self.description = description
        self.display_name = display_name
        self.creation_date = creation_date
        self.version_date = version_date
        self.contact = contact

    def __getitem__(self, key):
        return self.__dict__.__getitem__(key)

    def __setitem__(self, key, value):
        return self.__dict__.__setitem__(key, value)

    def __delitem__(self, key):
        return self.__dict__.__delitem__(key)

    def __contains__(self, item):
        return self.__dict__.__contains__(item)

    def __getstate__(self):
        return self.__dict__.copy()

    def __setstate__(self, d:dict[str]):
        self.__dict__.update(d)

class Prefab:

    @classmethod
    def from_folder(cls, path:str, plugin_filename:str="prefab.json"):
        with open(os.path.join(path, plugin_filename)) as f:
            d = json.load(f)
        p = cls.__new__(cls)
        p.__setstate__(d)
        p._root = path
        return p

    @classmethod
    def from_zipfile(cls, path:str, plugin_filename:str="prefab.json"):
        zf = zipfile.ZipFile(path)
        d = json.loads(zf.read(plugin_filename))
        p = cls.__new__(cls)
        p.__setstate__(d)
        p._root = zf
        return p, zf
        
    def __init__(self, meta:PrefabMeta, fields:rpmt.FieldList, resources:rpmt.ResourceList, outputs:rpmt.OutputList, resource_dirname:str="resources"):
        self.meta = meta
        self.fields = fields
        self.resources = resources
        self.outputs = outputs
        self.resource_dirname = resource_dirname
        self._root:str|zipfile.ZipFile|None = None

    def __getstate__(self):
        fds = {}
        for name, field in self.fields.items():
            fd = field.__getstate__()
            if "name" in fd:
                del fd["name"]
            fds[name] = fd
        return dict(
            meta=self.meta.__getstate__(),
            resource_dir=self.resource_dirname,
            fields=fds,
            resources=self.resources,
            outputs=[output.__getstate__() for output in self.outputs]
        )

    def __setstate__(self, d:dict[str]):
        self._root = None
        metad = d["meta"]
        if isinstance(metad, dict):
            self.meta = PrefabMeta.__new__(PrefabMeta)
            self.meta.__setstate__(metad)
        else:
            self.meta = PrefabMeta("", "", [], "", "", "", "", "")
        fsd = d["fields"]
        fields = {}
        if isinstance(fsd, dict):
            for name, fd in fsd.items():
                fd["name"] = name
                field = rpmt.Field.__new__(rpmt.Field)
                field.__setstate__(fd)
                fields[field.name] = field
        osd = d["outputs"]
        outputs = []
        if isinstance(osd, list):
            for od in osd:
                output = rpmt.Output.__new__(rpmt.Output)
                output.__setstate__(od)
                outputs.append(output)
        resources = d["resources"]
        self.resource_dirname = str(d.get("resources_dir", "resources"))
        self.fields = fields
        if isinstance(resources, dict):
            self.resources:rpmt.ResourceList = resources
        self.outputs = outputs

    def relevant_data(self, field_names:set[str])->tuple[set[str], list[int]]:
        rnames = set()
        oindexes = []
        for i, output in enumerate(self.outputs):
            if any(process.field_name in field_names for process in output.replace_processes):
                rnames.add(output.resource_name)
                oindexes.append(i)
            elif any(process.field_name in field_names for process in output.location_replace_processes):
                oindexes.append(i)
        return rnames, oindexes

    def instantiate(self, field_values:dict[str, str], instance_file:str|IO[bytes], prefab_root:str|zipfile.ZipFile|None=None):
        if prefab_root is None:
            if self._root is None:
                raise ValueError("Prefab needs root path or zip file to instantiate.")
            else:
                prefab_root = self._root

        if isinstance(prefab_root, zipfile.ZipFile):
            r_open = self._root.open
        else:
            r_open = open
        
        fvwdefaults = {}
        for field in self.fields.values():
            if field.default is None:
                fvwdefaults[field.name] = field_values[field.name]
            else:
                fvwdefaults[field.name] = field_values.get(field.name, field.default)

        unique_filled_resources:set[tuple[str,tuple[tuple[str, str, str, tuple[tuple[str, Any], ...]],...]]] = set()
        for output in self.outputs:
            unique_filled_resources.add(output.generate_key())

        filled_resources:dict[tuple, IO[bytes]] = {}
        for key in unique_filled_resources:
            rname, processes = key
            subs:dict[bytes, str] = {}
            for fname, blank, umethod, optionst in processes:
                if blank in subs:
                    ... #TODO error blank cannot be specified twice for the same output
                subs[blank.encode("utf-8")] = field_use_methods[umethod](FieldUseContext(
                    self.fields[fname],
                    rpmt.ReplaceProcess(fname, blank, umethod, {k:rpmt.mutible_unwrap(v) for k,v in optionst}),
                    fvwdefaults[fname]
                ))
            rpath_incomplete = self.resources[rname]
            if isinstance(prefab_root, str):
                rpath = os.path.abspath(os.path.join(prefab_root, self.resource_dirname, rpath_incomplete))
            else:
                rpath = os.path.abspath(os.path.join(self.resource_dirname, rpath_incomplete))
            if subs:
                blanks = re.compile(b"|".join(re.escape(blank) for blank in sorted(subs.keys(), reverse=True)))
                replace:Callable[[re.Match[bytes]], bytes] = lambda m: subs[m.group(0)].encode("utf-8")
                with r_open(rpath, "rb") as inf:
                    tf = filled_resources[key] = tempfile.TemporaryFile("wb+")
                    for line in inf:
                        tf.write(blanks.sub(replace, line))
            else:
                with r_open(rpath, "rb") as inf:
                    tf = filled_resources[key] = tempfile.TemporaryFile("wb+")
                    shutil.copyfileobj(inf, tf)

        staged_destinations = stagedfs.StagedFS()
        ordered_locations = []
        instance = PrefabInstance(self, fvwdefaults, ordered_locations, prefab_root)
        with tempfile.TemporaryFile("wb", delete_on_close=False) as tzf:
            with instance.zip_context(tzf, "w"):
                for output in self.outputs:
                    subs = {}
                    for process in output.location_replace_processes:
                        if process.blank in subs:
                            ... #TODO error blank cannot be specified twice for the same output location
                        subs[process.blank] = field_use_methods[process.use_method](FieldUseContext(
                            self.fields[process.field_name],
                            process,
                            fvwdefaults[process.field_name]
                        ))
                    if subs:
                        replace:Callable[[re.Match], str] = lambda m: subs[m.group(0)]
                        location = re.sub(
                            "|".join(re.escape(blank) for blank in sorted(subs.keys(), reverse=True)),
                            replace,
                            output.destination.location
                        )
                    else:
                        location = output.destination.location
                    location = os.path.abspath(location)
                    ordered_locations.append(location)
                    #TODO ensure location is in bot environment scope
                    key = output.generate_key()
                    tf = filled_resources[key]
                    cursor = tf.tell()
                    tf.seek(0)
                    instance.add_filled_resource(key, tf)
                    tf.seek(cursor)
                    merge_methods[output.destination.merge_method](MergeContext(
                        fs=staged_destinations,
                        output=output,
                        field_values=fvwdefaults,
                        location=location,
                        filled_resource=tf
                    ))


            with open(tzf.name, "rb") as zf:
                if isinstance(instance_file, str):
                    with open(instance_file, "wb") as f:
                        instance.header_to_file(f)
                        shutil.copyfileobj(zf, f)
                else:
                    instance.header_to_file(instance_file)
                    shutil.copyfileobj(zf, instance_file)
            
        staged_destinations.commit()
        return instance


class PrefabInstance:
    @classmethod
    def from_file(cls, f_or_p:IO[bytes]|str, open_zip:bool=True):
        if isinstance(f_or_p, str):
            with open(f_or_p, "rb+") as f:
                return cls.from_file(f, open_zip=open_zip)
        d = json.loads(f_or_p.readline())
        instance = cls.__new__(cls)
        instance.__setstate__(d)
        if open_zip:
            tf = tempfile.TemporaryFile("wb+", delete_on_close=False)
            shutil.copyfileobj(f_or_p, tf)
            tf.seek(0)
            instance = instance.zip_context(tf, mode="a")
        else:
            tf = None
        return instance, tf

    def __init__(self, prefab:Prefab, field_values:dict[str,str], ordered_locations:list[str], prefab_root:str|zipfile.ZipFile|None):
        self.prefab = prefab
        self.field_values = field_values
        self.ordered_locations = ordered_locations
        if prefab_root is None or isinstance(prefab_root, str):
            self.prefab_root = prefab_root
        elif isinstance(prefab_root, zipfile.ZipFile):
            if isinstance(prefab_root.filename, str):
                self.prefab_root = os.path.abspath(prefab_root.filename)
            else:
                self.prefab_root = None
        else:
            self.prefab_root = None
        self._zip_pointer:zipfile.ZipFile|None = None

    def __getstate__(self):
        return dict(
            prefab=self.prefab.__getstate__(),
            field_values=self.field_values,
            ordered_locations=self.ordered_locations,
            prefab_root=self.prefab_root
        )

    def __setstate__(self, d:dict[str]):
        prefab = Prefab.__new__(Prefab)
        prefab.__setstate__(d["prefab"])
        self.prefab = prefab
        fvd = d["field_values"]
        if isinstance(fvd, dict):
            self.field_values:dict[str,str] = fvd
        olocd = d["ordered_locations"]
        if isinstance(olocd, list):
            self.ordered_locations = olocd.copy()
        self.prefab_root = None if (pr:=d.get("prefab_root", None)) is None else str(pr)
        self._zip_pointer = None

    def header_to_file(self, f:IO[bytes], encoding:str|None=None):
        c = json.dumps(self.__getstate__(), ensure_ascii=False)
        return f.write((c + "\n").encode(DEFAULT_PREFAB_INST_HEADER_ENCODING if encoding is None else encoding))

    def zip_context(self, b:IO[bytes], mode:str="r", compression_level:int|None=None):
        if zlib is None:
            logenv.main.warn(
                "zlib missing, zip compression not available",
                human_text="Your Python installation is missing a dependency and will not be able to compress prefab instance data."
            )
            zf = zipfile.ZipFile(b, mode)
        else:
            if compression_level is None:
                compression_level = DEFAULT_PREFAB_INST_COMPRESSION_LEVEL
            zf = zipfile.ZipFile(b, mode, compression=zipfile.ZIP_DEFLATED, compresslevel=compression_level)
        self._zip_pointer = zf
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._zip_pointer is not None:
            self._zip_pointer.close()
            self._zip_pointer = None

    def add_filled_resource(self, key:tuple, rf:IO[bytes]):
        keyhash = rpmt.key_to_string(key).hexdigest()
        with self._zip_pointer.open(keyhash, "w") as f:
            shutil.copyfileobj(rf, f)

    def get_filled_resource(self, key:tuple):
        keyhash = rpmt.key_to_string(key).hexdigest()
        return self._zip_pointer.open(keyhash)

    def delete(self):
        assert self._zip_pointer is not None and self._zip_pointer.fp.readable()
        assert len(self.prefab.outputs) == len(self.ordered_locations)

        staged_destinations = stagedfs.StagedFS()
        for output, location in zip(self.prefab.outputs, self.ordered_locations):
            if os.path.isfile(location):
                staged = None
                staged_node = staged_destinations.tree._get_node(location)
                if staged_node is None:
                    staged_node = staged_destinations.tree._set_entry_prep(location)
                if staged_node.entry is None:
                    staged = tempfile.TemporaryFile("wb+")
                    staged_node.entry = stagedfs.StagedFSEntry(0, staged)
                elif staged_node.entry.fobj is None:
                    staged = staged_node.entry.fobj = tempfile.TemporaryFile("wb+")
                if staged is not None:
                    with open(location, "rb") as f:
                        shutil.copyfileobj(f, staged)
            key = output.generate_key()
            with self.get_filled_resource(key) as filled:
                unmerge_methods[output.destination.unmerge_method](UnmergeContext(
                    fs=staged_destinations,
                    output=output,
                    field_values=self.field_values,
                    location=location,
                    filled_resource=filled
                ))

        staged_destinations.commit()
           

    def update(self, field_values:dict[str,str], prefab_root:str|zipfile.ZipFile|None=None):
        assert self._zip_pointer is not None and self._zip_pointer.fp.readable() and self._zip_pointer.fp.writable()
        if prefab_root is None:
            if self.prefab_root is None:
                raise ValueError("Prefab root needed to update instance.")
            elif os.path.isfile(self.prefab_root):
                prefab_root = zipfile.ZipFile(self.prefab_root)
            else:
                prefab_root = self.prefab_root

        if isinstance(prefab_root, zipfile.ZipFile):
            r_open = self.prefab._root.open
        else:
            r_open = open
        
        fvdifferences = set()
        fvchanged = {}
        for k, ev in self.field_values.items():
            v = field_values.get(k, None)
            if v is not None and v != ev:
                fvchanged[k] = v
                fvdifferences.add(k)
            else:
                fvchanged[k] = ev

        unique_filled_resources:set[tuple[str,tuple[tuple[str, str, str, tuple[tuple[str, Any], ...]],...]]] = set()
        required_outputs:set[int] = set()
        required_resources:set[str] = set()
        for i, output in enumerate(self.prefab.outputs):
            if any(lrp.field_name in fvdifferences for lrp in output.location_replace_processes) or any(rp.field_name in fvdifferences for rp in output.replace_processes):
                unique_filled_resources.add(output.generate_key())
                required_resources.add(output.resource_name)
                required_outputs.add(i)

        filled_resources:dict[tuple, IO[bytes]] = {}

        for key in unique_filled_resources:
            rname, processes = key
            subs:dict[bytes, str] = {}
            for fname, blank, umethod, optionst in processes:
                if blank in subs:
                    ... #TODO error blank cannot be specified twice for the same output
                subs[blank.encode("utf-8")] = field_use_methods[umethod](FieldUseContext(
                    self.prefab.fields[fname],
                    rpmt.ReplaceProcess(fname, blank, umethod, {k:rpmt.mutible_unwrap(v) for k,v in optionst}),
                    fvchanged[fname]
                ))
            rpath_incomplete = self.prefab.resources[rname]
            if isinstance(prefab_root, str):
                rpath = os.path.abspath(os.path.join(prefab_root, self.prefab.resource_dirname, rpath_incomplete))
            else:
                rpath = os.path.abspath(os.path.join(self.prefab.resource_dirname, rpath_incomplete))
            if subs:
                blanks = re.compile(b"|".join(re.escape(blank) for blank in sorted(subs.keys(), reverse=True)))
                replace:Callable[[re.Match[bytes]], bytes] = lambda m: subs[m.group(0)].encode("utf-8")
                with r_open(rpath, "rb") as inf:
                    tf = filled_resources[key] = tempfile.TemporaryFile("wb+")
                    for line in inf:
                        tf.write(blanks.sub(replace, line))
            else:
                with r_open(rpath, "rb") as inf:
                    tf = filled_resources[key] = tempfile.TemporaryFile("wb+")
                    shutil.copyfileobj(inf, tf)

        staged_destinations = stagedfs.StagedFS()
        ordered_locations = []

        newtzf = tempfile.TemporaryFile("wb+", delete_on_close=False)
        with self._zip_pointer as old_zip:
            with self.zip_context(newtzf, "w"):
                for i, output in enumerate(self.prefab.outputs):
                    if i not in required_outputs:
                        ordered_locations.append(self.ordered_locations[i])
                        key = output.generate_key()
                        keyhash = rpmt.key_to_string(key).hexdigest()
                        with old_zip.open(keyhash) as f, self._zip_pointer.open(keyhash, "w") as f2:
                            shutil.copyfileobj(f, f2)
                        continue
                    output = self.prefab.outputs[i]
                    subs = {}
                    for process in output.location_replace_processes:
                        if process.blank in subs:
                            ... #TODO error blank cannot be specified twice for the same output location
                        subs[process.blank] = field_use_methods[process.use_method](FieldUseContext(
                            self.prefab.fields[process.field_name],
                            process,
                            fvchanged[process.field_name]
                        ))
                    if subs:
                        replace:Callable[[re.Match[str]], str] = lambda m: subs[m.group(0)]
                        location = re.sub(
                            "|".join(re.escape(blank) for blank in sorted(subs.keys(), reverse=True)),
                            replace,
                            output.destination.location
                        )
                    else:
                        location = output.destination.location
                    location = os.path.abspath(location)
                    ordered_locations.append(location)
                    old_location = self.ordered_locations[i]
                    #TODO ensure location is in bot environment scope
                    if os.path.isfile(old_location):
                        staged = None
                        staged_node = staged_destinations.tree._get_node(old_location)
                        if staged_node is None:
                            staged_node = staged_destinations.tree._set_entry_prep(old_location)
                        if staged_node.entry is None:
                            staged = tempfile.TemporaryFile("wb+")
                            staged_node.entry = stagedfs.StagedFSEntry(0, staged)
                        elif staged_node.entry.fobj is None:
                            staged = staged_node.entry.fobj = tempfile.TemporaryFile("wb+")
                        if staged is not None:
                            with open(old_location, "rb") as f:
                                shutil.copyfileobj(f, staged)
                    key = output.generate_key()
                    with old_zip.open( rpmt.key_to_string(key).hexdigest()) as filled:
                        unmerge_methods[output.destination.unmerge_method](UnmergeContext(
                            fs=staged_destinations,
                            output=output,
                            field_values=self.field_values,
                            location=old_location,
                            filled_resource=filled
                        ))
                    tf = filled_resources[key]
                    cur = tf.tell()
                    tf.seek(0)
                    self.add_filled_resource(key, tf)
                    tf.seek(cur)
                    merge_methods[output.destination.merge_method](MergeContext(
                        fs=staged_destinations,
                        output=output,
                        field_values=fvchanged,
                        location=location,
                        filled_resource=tf
                    ))
        staged_destinations.commit()
        self.field_values = fvchanged
        self.ordered_locations = ordered_locations
        return newtzf

class FieldUseContext:
    def __init__(self, field:rpmt.Field, process:rpmt.ReplaceProcess, value:str):
        self.field = field
        self.process = process
        self.value = value

class MergeContext:
    def __init__(self, fs:stagedfs.StagedFS, output:rpmt.Output, field_values:dict[str,str], location:str, filled_resource:IO[bytes]):
        self.fs = fs
        self.output = output
        self.field_values = field_values
        self.location = location
        self.filled_resource = filled_resource

    @property
    def method(self):
        return self.output.destination.merge_method

    @property
    def options(self):
        return self.output.destination.merge_options

class UnmergeContext:
    def __init__(self, fs:stagedfs.StagedFS, output:rpmt.Output, field_values:dict[str,str], location:str, filled_resource:IO[bytes]):
        self.fs = fs
        self.output = output
        self.field_values = field_values
        self.location = location
        self.filled_resource = filled_resource

    @property
    def method(self):
        return self.output.destination.unmerge_method

    @property
    def options(self):
        return self.output.destination.unmerge_options

def field_use_plain(use:FieldUseContext):
    return use.value

def field_use_json_value(use:FieldUseContext):
    format_settings = use.process.options.get("format_settings", None)
    if isinstance(format_settings, dict):
        format_settings.setdefault("ensure_ascii", False)
        format_settings.setdefault("indent", 4)
    else:
        format_settings = dict(ensure_ascii=False, indent=4)
    if use.field.input_type == "number":
        return use.value
    else:
        return json.dumps(use.value, **format_settings)

def field_use_json_value_uncontained(use:FieldUseContext):
    format_settings = use.process.options.get("format_settings", None)
    if isinstance(format_settings, dict):
        format_settings.setdefault("ensure_ascii", False)
        format_settings.setdefault("indent", 4)
    else:
        format_settings = dict(ensure_ascii=False, indent=4)
    if use.field.input_type == "number":
        return use.value
    else:
        return json.dumps(use.value, **format_settings)[1:-1]

def merge_new_file(merge:MergeContext):
    fstaged = merge.fs.fetch_fobj(merge.location)
    if fstaged is None:
        fstaged = tempfile.TemporaryFile("wb+")
    else:
        fstaged.seek(0)
        fstaged.truncate()
    merge.filled_resource.seek(0)
    merge.fs.writefile(merge.location, fstaged)
    shutil.copyfileobj(merge.filled_resource, fstaged)

def unmerge_new_file(unmerge:UnmergeContext):
    fstaged = unmerge.fs.fetch_fobj(unmerge.location)
    if unmerge.options.get("strict", False):
        if fstaged is not None:
            chunk_size = int(unmerge.options.get("chunk_size", 1024))
            fstaged.seek(0)
            unmerge.filled_resource.seek(0)
            while True:
                chunk1 = fstaged.read(chunk_size)
                chunk2 = unmerge.filled_resource.read(chunk_size)
                if chunk1 != chunk2:
                    unmerge.fs.rmfile(unmerge.location)
                elif not chunk1:
                    return
    else:
        unmerge.fs.rmfile(unmerge.location)

def merge_append_file(merge:MergeContext):
    fstaged = merge.fs.fetch_fobj(merge.location)
    if fstaged is None:
        if merge.options.get("makedirs", True):
            merge.fs.makedir(os.path.dirname(merge.location))
        fstaged = tempfile.TemporaryFile("wb+")
        try:
            with open(merge.location, "rb") as f:
                shutil.copyfileobj(f, fstaged)
        except FileNotFoundError:
            pass
    else:
        fstaged.seek(0, os.SEEK_END)
    merge.filled_resource.seek(0)
    shutil.copyfileobj(merge.filled_resource, fstaged)
    merge.fs.writefile(merge.location, fstaged)
    return fstaged

def _chunked_write(fsrc:IO[bytes], fdest:IO[bytes], chunk:int, n:int=sys.maxsize):
    i = 0
    while i < n:
        to_read = min(chunk, n-i)
        b = fsrc.read(to_read)
        if not b:
            return i
        fdest.write(b)
        i += to_read
    return n

def unmerge_append_file(unmerge:UnmergeContext):
    fstaged = unmerge.fs.fetch_fobj(unmerge.location)
    if fstaged is None:
        return
    chunk_size = int(unmerge.options.get("chunk_size", 1024))
    fstaged.seek(0)
    unmerge.filled_resource.seek(0)
    if not unmerge.filled_resource.read(1):
        return
    unmerge.filled_resource.seek(0)
    start = None
    i = 0
    chunk1 = b""
    chunk1_start = 0
    chunk2_start = 0
    read_chunk1 = True
    read_chunk2 = True
    while True:
        if read_chunk2:
            read_chunk2 = False
            chunk2 = unmerge.filled_resource.read(chunk_size)
            chunk2_start = 0
            if not chunk2:
                i += chunk1_start
                break
        if read_chunk1:
            read_chunk1 = False
            i += len(chunk1)
            chunk1 = fstaged.read(chunk_size)
            chunk1_start = 0
            if not chunk1:
                start = None
                break
        chunk2_sub = chunk2[chunk2_start:chunk2_start+len(chunk1)-chunk1_start]
        found = chunk1.find(chunk2_sub, chunk1_start)
        if found < 0:
            if chunk2_start == 0:
                read_chunk1 = True
            start = None
            read_chunk2 = True
            unmerge.filled_resource.seek(0)
        elif found > 0:
            start = i + found
        elif start is None:
            start = i

        if not read_chunk1 and found >= 0:
            chunk1_start += found + len(chunk2_sub)
            if chunk1_start >= len(chunk1):
                read_chunk1 = True
        if not read_chunk2:
            chunk2_start += len(chunk2_sub)
            if chunk2_start >= len(chunk2):
                read_chunk2 = True

    if start is None:
        ... #TODO substring not in staged
    else:
        size = fstaged.seek(0, os.SEEK_END)
        fstaged.seek(0)
        if (i-start) >= size:
            fstaged.truncate()
            if unmerge.options.get("delete_empty", False):
                unmerge.fs.rmfile(unmerge.location)
        else:
            unmerge.filled_resource.seek(0)
            with tempfile.TemporaryFile("wb+") as f:
                _chunked_write(fstaged, f, chunk_size, start)
                fstaged.seek(i)
                _chunked_write(fstaged, f, chunk_size)
                fstaged.seek(0)
                fstaged.truncate(f.tell())
                f.seek(0)
                shutil.copyfileobj(f, fstaged)
            unmerge.fs.writefile(unmerge.location, fstaged)


def _json_insert_path_option_value_handle(x):
    if x is None:
        return ()
    elif isinstance(x, (str,int)):
        return x,
    elif isinstance(x, float):
        return int(x),
    elif isinstance(x, list) and all(isinstance(p, (str, int, float)) for p in x):
        return tuple(p if isinstance(p, str) else int(p) for p in x)

def _json_insert_list_insert(l:list, index:int, assign, fill_default, fill_order:list|dict|None):
    diff = index - len(l)
    if diff < 0:
        l[index] = assign
    elif diff == 0:
        l.append(assign)
    else:
        if not fill_order:
            l.extend(fill_default for _ in range(diff))
        elif isinstance(fill_order, dict):
            l.extend(fill_order.get(str(i), fill_default) for i in range(len(l), index))
        elif isinstance(fill_order, list):
            l.extend(fill_order[len(l):index])
            if len(l) < index:
                l.extend(fill_default for _ in range(len(l) - index))
        else:
            return
        l.append(assign)

_JSON_INSERT_NO_STAGED = object()
def merge_json_insert(merge:MergeContext):
    insert_path = _json_insert_path_option_value_handle(merge.options.get("insert_path", None))

    fstaged = merge.fs.fetch_fobj(merge.location)
    if fstaged is None:
        if os.path.isfile(merge.location):
            with open(merge.location) as f:
                contents = json.load(f)
        elif not insert_path:
            contents = _JSON_INSERT_NO_STAGED
        elif isinstance(insert_path[-1], str):
            contents = {}
        else:
            contents = []

    else:
        fstaged.seek(0)
        contents = json.load(fstaged)

    popts = merge.options.get("paths", None)
    path_options:dict[tuple[str|int, ...], dict[str]] = {}
    if isinstance(popts, list):
        for o in popts:
            if not isinstance(o, dict) or "path" not in o:
                continue
            options = o.copy()
            path = _json_insert_path_option_value_handle(options.pop("path"))
            if path is not None:
                path_options[path] = options

    merge.filled_resource.seek(0)
    incoming = json.load(merge.filled_resource)

    if contents is _JSON_INSERT_NO_STAGED:
        contents = incoming
    else:
        prev = None
        cur = contents
        for i, p in enumerate(insert_path):
            ip1 = i+1
            if isinstance(cur, dict):
                vp = str(p)
                if vp in cur:
                    prev = cur
                    cur = cur[vp]
                    continue
            elif isinstance(cur, list):
                vp = int(p)
                if vp < len(cur):
                    prev = cur
                    cur = cur[vp]
                    continue
            else:
                path = tuple(*insert_path[0:i], p)
                poptions = path_options.get(path, {})
                if poptions.get("replace_if_present", True):
                    if prev is None:
                        if isinstance(p, str):
                            contents = cur = {}
                        else:
                            contents = cur = []
                    else:
                        if isinstance(p, str):
                            cur = {}
                        else:
                            cur = []
                        if isinstance(prev, dict):
                            prev[str(insert_path[i-1])] = cur
                        else:
                            _json_insert_list_insert(
                                prev,
                                int(insert_path[i-1]),
                                cur,
                                poptions.get("fill_default", None),
                                poptions.get("fill_order", None)
                            )
                    ip1 = i+1
                    if ip1 == len(insert_path):
                        next = incoming
                    if isinstance(insert_path[ip1], str):
                        next = {}
                    else:
                        next = []
                    prev = cur
                    cur[p] = next
                    cur = next
                else:
                    ... #TODO error cannot replace at path
                continue
            path = (*insert_path[0:i], p)
            poptions = path_options.get(path, {})
            if poptions.get("make_if_missing", True):
                if ip1 == len(insert_path):
                    next = incoming
                elif isinstance(insert_path[ip1], str):
                    next = {}
                else:
                    next = []
                prev = cur
                cur[vp] = next
                cur = next
            else:
                ... #TODO error cannot insert, missing at path

    format_settings = merge.options.get("format_settings", None)
    if isinstance(format_settings, dict):
        format_settings.setdefault("ensure_ascii", False)
        format_settings.setdefault("indent", 4)
    else:
        format_settings = dict(ensure_ascii=False, indent=4)

    with tempfile.TemporaryFile("wb+") as f:
        json.dump(contents, f, **format_settings)
        if fstaged is None:
            fstaged = tempfile.TemporaryFile("wb+")
        else:
            fstaged.seek(0)
            fstaged.truncate()
        f.seek(0)
        shutil.copyfileobj(f, fstaged)
    merge.fs.writefile(merge.location, fstaged)
    return fstaged


    
def unmerge_json_insert(unmerge:UnmergeContext):
    _insert_path = unmerge.options.get()
    if "insert_path" in unmerge.options:
        _insert_path = unmerge.options["insert_path"]
    else:
        _insert_path = unmerge.output.destination.merge_options.get("insert_path", None)
    insert_path = _json_insert_path_option_value_handle(_insert_path)

    fstaged = unmerge.fs.fetch_fobj(unmerge.location)
    if fstaged is None:
        if os.path.isfile(unmerge.location):
            with open(unmerge.location) as f:
                contents = json.load(f)
        else:
            ... #TODO look at settings
    else:
        fstaged.seek(0)
        contents = json.load(fstaged)

    unmerge.filled_resource.seek(0)
    incoming = json.load(unmerge.filled_resource)

field_use_methods:dict[str, Callable[[FieldUseContext], str]] = {
    "plain": field_use_plain,
    "json_value": field_use_json_value,
    "json_value_uncontained": field_use_json_value_uncontained
}
merge_methods:dict[str, Callable[[MergeContext], IO[bytes]]] = {
    "new_file": merge_new_file,
    "append_file": merge_append_file,
    "json_insert": merge_json_insert
}
unmerge_methods:dict[str, Callable[[UnmergeContext], IO[bytes]|None]] = {
    "new_file": unmerge_new_file,
    "append_file": unmerge_append_file,
    "json_insert": unmerge_json_insert
}


def update_instance_from_file(f_or_p:IO[bytes]|str, field_values:dict[str,str]):
    if isinstance(f_or_p, str):
        with open(f_or_p, "rb+") as f_or_p:
            return update_instance_from_file(f_or_p, field_values)
    start = f_or_p.tell()
    instance, tf = PrefabInstance.from_file(f_or_p)
    with tf:
        with instance._zip_pointer:
            tzf = instance.update(field_values)
    with tzf:
        with open(tzf.name, "rb") as zf:
            f_or_p.seek(start)
            f_or_p.truncate()
            instance.header_to_file(f_or_p)
            shutil.copyfileobj(zf, f_or_p)

def delete_instance_from_file(f_or_p:IO[bytes]|str):
    instance, zf = PrefabInstance.from_file(f_or_p)
    with zf:
        instance.delete()
    if isinstance(f_or_p, str):
        path = f_or_p
    else:
        path = f_or_p.name
    if path:
        os.remove(path)