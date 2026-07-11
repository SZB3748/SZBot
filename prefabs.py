import datafile
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import shutil
import tempfile
import tronix
import tronix.parsingnodes
from typing import Callable, IO, NamedTuple
from uuid import UUID, uuid4
import zipfile

DEFAULT_RESOURCES_DIR = "resources"

PREFAB_INSTANCE_DIR = datafile.makepath("prefab_instances")

class Field:
    def __init__(self, name:str, display_name:str, description:str, input:dict[str]|None=None, default:str|None=None):
        self.name = name
        self.display_name = display_name
        self.description = description
        self.input = {} if input is None else input
        self.default = default

    def __getstate__(self):
        return dict(
            name=self.name,
            display_name=self.display_name,
            description=self.description,
            input=self.input,
            default=self.default
        )
    
    def __setstate__(self, d:dict[str]):
        self.name = str(d["name"])
        self.display_name = str(display_name) if (display_name:=d.get("display_name",None)) is not None else self.name
        self.description = str(d.get("description", ""))
        self.input = {} if (input:=d["input"]) is None else dict(input)
        self.default = None if (default:=d.get("default",None)) is None else str(default)

class Resource:
    def __init__(self, name:str, path:str):
        self.name = name
        self.path = path

    def get_path(self, dir:str):
        dir = os.path.abspath(dir)
        path = os.path.abspath(os.path.join(dir, self.path))
        if path.startswith(dir):
            return path

class Resources:
    def __init__(self, dir:str=DEFAULT_RESOURCES_DIR, files:dict[str, Resource]|None=None):
        self.dir = dir
        self.files = {} if files is None else files

    def __getstate__(self):
        return dict(
            dir=self.dir,
            files={
                file.name: file.path for file in self.files.values()
            }
        )

    def __setstate__(self, d:dict[str]):
        self.dir = str(d.get("dir", DEFAULT_RESOURCES_DIR))
        files = {}
        fd = d.get("files", None)
        if isinstance(fd, dict):
            for name, path in fd.items():
                files[name] = Resource(name, path)
        self.files = files

    def __getitem__(self, name):
        return self.files[name]
    
    def __setitem__(self, name, value:Resource):
        self.files[name] = value

    def __delitem__(self, name):
        del self.files[name]

class TransformationReplace:
    def __init__(self, key:str, method:str, options:dict[str]|None=None):
        self.key = key
        self.method = method
        self.options = {} if options is None else options
    
    def __getstate__(self):
        return dict(key=self.key, method=self.method)
    
    def __setstate__(self, d:dict[str]):
        self.key = str(d["key"])
        self.method = str(d["method"])
        self.options = options if isinstance(options:=d.get("options",None), dict) else {}

TransformationFunction = Callable[[Field, TransformationReplace, str], str]
transformation_methods:dict[str, TransformationFunction] = {}

def add_transformation_method(method:str, transformation:TransformationFunction|None=None):
    def decor(f:TransformationFunction):
        transformation_methods[method] = f
        return f
    if transformation is None:
        return decor
    else:
        return decor(transformation)

def remove_transformation_method(method:str, transformation:TransformationFunction|None=None):
    if transformation is None:
        return transformation_methods.pop(method, None)
    elif transformation_methods.get(method, None) is transformation:
        del transformation_methods[method]
        return transformation

class Transformation:
    def __init__(self, field:str, replace:TransformationReplace):
        self.field = field
        self.replace = replace

    def __getstate__(self):
        return dict(
            field=self.field,
            replace=self.replace.__getstate__()
        )

    def __setstate__(self, d:dict[str]):
        replace = TransformationReplace.__new__(TransformationReplace)
        replace.__setstate__(d["replace"])
        self.field = str(d["field"])
        self.replace = replace

class ResourceTransformation(Transformation):
    def __init__(self, field:str, replace:TransformationReplace, resources:list[str]|None=None):
        super().__init__(field, replace)
        self.resources = [] if resources is None else resources
    
    def __getstate__(self):
        d = super().__getstate__()
        d["resource"] = self.resources
        return d
    
    def __setstate__(self, d):
        super().__setstate__(d)
        self.resources = [str(r) for r in d["resources"]]

class OutputDestinationTransformation(Transformation):
    pass

class OutputDestination:
    def __init__(self, file:str, transformations:list[OutputDestinationTransformation]|None=None):
        self.file = file
        self.transformations = [] if transformations is None else transformations

    def __getstate__(self):
        return dict(
            file=self.file,
            transformations=[t.__getstate__() for t in self.transformations]
        )

    def __setstate__(self, d:dict[str]):
        td = d.get("transformations", None)
        transformations = []
        if isinstance(td, list):
            for t in td:
                if isinstance(t, dict):
                    transformation = OutputDestinationTransformation.__new__(OutputDestinationTransformation)
                    transformation.__setstate__(t)
                    transformations.append(transformation)
        self.file = str(d["file"])
        self.transformations = transformations

    def prep(self, output:"Output", resource_path:str, dest_path:str)->str|None:
        raise NotImplementedError
    
    def purge(self, output:"Output", dest_path:str, value:bytes):
        raise NotImplementedError


class JsonMergeDestination(OutputDestination):
    def __init__(self, file:str, transformations:list[OutputDestinationTransformation]|None=None, path:list[str|int]|None=None):
        super().__init__(file, transformations)
        self.path = path

    def __getstate__(self):
        d = super().__getstate__()
        d["path"] = self.path
        return d
    
    def __setstate__(self, d:dict[str]):
        super().__setstate__(d)
        self.path = path if isinstance((path:=d["path"]), list) else []

    def prep(self, output, resource_path, dest_path):
        ... #TODO
    
    def purge(self, output, dest_path:str, value):
        ... #TODO

class NewFileDestination(OutputDestination):
    def prep(self, output, resource_path, dest_path):
        return None
    
    def purge(self, output, dest_path, value):
        if os.path.isfile(dest_path):
            os.remove(dest_path)

output_type_to_class:dict[str, type[OutputDestination]] = {
    "json_merge": JsonMergeDestination,
    "new_file": NewFileDestination
}

class Output:
    def __init__(self, resource:str, type:str, destination:OutputDestination, options:dict[str]|None=None):
        self.resource = resource
        self.type = type
        self.destination = destination
        self.options = {} if options is None else options

    def __getstate__(self):
        return dict(
            resource=self.resource, type=self.type,
            destination=self.destination.__getstate__(),
            options=self.options
        )
    
    def __setstate__(self, d:dict[str]):
        self.resource = str(d["resource"])
        self.type = str(d["type"])
        dest_type = output_type_to_class[self.type]
        dest = dest_type.__new__(dest_type)
        dest.__setstate__(d["destination"])
        self.destination = dest
        self.options = options if isinstance(options:=d.get("options",None), dict) else {}

FieldValues = dict[str,str]

class CompiledTransformations:
    def __init__(self, resource:str, field_value_transforms:dict[tuple[str, str], tuple[TransformationReplace, TransformationFunction]]):
        self.resource = resource
        self.field_value_transforms = field_value_transforms

    def apply(self, fields:dict[str, Field], field_values:FieldValues):
        return {key:func(fields[field], tr, field_values[field]) for (field, key), (tr, func) in self.field_value_transforms.items()}

class Prefab:
    def __init__(self, name:str, description:str, authors:list[str], version:str, created:datetime|None=None, version_released:datetime|None=None,
                 fields:dict[str,Field]|None=None, resources:Resources|None=None, transformations:list[ResourceTransformation]|None=None, outputs:list[Output]|None=None):
        self.name = name
        self.description = description
        self.authors = authors
        self.version = version
        self.created = created
        self.version_released = version_released
        self.fields = None if fields is None else fields
        self.resources = Resources() if resources is None else resources
        self.transformations = [] if transformations is None else transformations
        self.outputs = [] if outputs is None else outputs

    def __getstate__(self):
        fields = {}
        for field in self.fields.values():
            fd = field.__getstate__()
            fields[fd.pop("name")] = fd
        return dict(
            name=self.name, description=self.description, authors=self.authors,
            version=self.version,
            created=None if self.created is None else self.created.astimezone(timezone.utc).isoformat(),
            version_released=None if self.version_released is None else self.version_released.astimezone(timezone.utc).isoformat(),
            fields=fields, resources=self.resources.__getstate__(),
            transformations=[t.__getstate__() for t in self.transformations],
            outputs=[o.__getstate__() for o in self.outputs]
        )
    
    def __setstate__(self, d:dict[str]):
        fd = d.get("fields",None)
        fields = {}
        if isinstance(fd, dict):
            for name, data in fd.items():
                if isinstance(data, dict):
                    data.setdefault("name", name)
                    field = Field.__new__(Field)
                    field.__setstate__(d)
                    fields[name] = field
        resources = Resources.__new__(Resources)
        resources.__setstate__(d["resources"])
        td = d.get("transformations",None)
        transformations = []
        if isinstance(td, list):
            for t in td:
                transformation = ResourceTransformation.__new__(ResourceTransformation)
                transformation.__setstate__(t)
                transformations.append(transformation)
        outputs = []
        for o in d["outputs"]:
            if isinstance(o, dict):
                output = Output.__new__(Output)
                output.__setstate__(o)
                outputs.append(output)

        self.name = str(d.get("name", ""))
        self.description = str(d.get("description", ""))
        self.authors = [str(author) for author in d["authors"]]
        self.version = str(d.get("version", ""))
        self.created = None if (created:=d["created"]) is None else datetime.fromisoformat(created)
        self.version_released = None if (vr:=d["version_released"]) is None else datetime.fromisoformat(vr)
        self.fields = fields
        self.resources = resources
        self.transformations = transformations
        self.outputs = outputs

    def _hash_base(self):
        fields = {}
        for field in self.fields.values():
            fd = field.__getstate__()
            fields[fd.pop("name")] = fd
        data = dict(
            fields=fields, resources=self.resources.__getstate__(),
            transformations=[t.__getstate__() for t in self.transformations],
            outputs=[o.__getstate__() for o in self.outputs]
        )
        return self.name + self.version + json.dumps(data)

    def hash(self):
        return hashlib.sha256(self._hash_base())

    def compile_resource_transformations(self, fields:set[str])->dict[str, CompiledTransformations|None]:
        needed_resources:set[str] = set()
        needed_transformations:dict[str, list[ResourceTransformation]] = {}
        for output in self.outputs:
            needed_resources.add(output.resource)
        for t in self.transformations:
            if t.field in fields and any(r in needed_resources for r in t.resources):
                for resource in t.resources:
                    l = needed_transformations.get(resource, None)
                    if l is None:
                        needed_transformations[resource] = [t]
                    else:
                        l.append(t)
                    
        rtv = {}
        for resource in self.resources.files.values():
            ts = needed_transformations.get(resource.name, None)
            if ts:
                tfuncs = {}
                key_set = set()
                for t in ts:
                    key = t.replace.key
                    if key in key_set:
                        ... #TODO error multiple transformations for the same resource+key pair
                    key_set.add(key)
                    tfuncs[(t.field, key)] = (t.replace, transformation_methods[t.replace.method])
                rtv[resource.name] = CompiledTransformations(resource, tfuncs)
            elif resource.name in needed_resources:
                rtv[resource.name] = None
        return rtv
    
    def compile_output_destination_transformations(self, fields:set[str])->list[CompiledTransformations|None]:
        rtv = []
        for output in self.outputs:
            ct = None
            if output.destination.transformations:
                tfuncs = {}
                key_set = set()
                for t in output.destination.transformations:
                    key = t.replace.key
                    if t.field in fields:
                        continue
                    elif key in key_set:
                        ... #TODO error key used multiple times for a single output
                    key_set.add(key)
                    tfuncs[(t.field, key)] = (t.replace, transformation_methods[t.replace.method])
                if tfuncs:
                    ct = CompiledTransformations(output.resource, tfuncs)
            rtv.append(ct)
        return rtv


    def fill_fields(self, field_values:FieldValues, names:list[str]|None=None)->FieldValues:
        if names is None:
            names = self.fields.values()
        rtv = {}
        for name in names:
            field = self.fields[name]
            v = field_values(field.name, field.default)
            if isinstance(v, str):
                rtv[field.name] = v
        return rtv
                        
    def instantiate(self, prefab_file_root:str, field_values:FieldValues, compiled_rt:dict[str, CompiledTransformations]|None=None, compiled_odt:list[CompiledTransformations|None]|None=None, replace_patterns:dict[str,re.Pattern]|None=None, all_outputs:bool=True, instance_id:UUID|None=None):
        if compiled_rt is None:
            compiled_rt = self.compile_resource_transformations(field_values.keys())
        if compiled_odt is None:
            compiled_odt = self.compile_output_destination_transformations(field_values.keys())
        if replace_patterns is None:
            replace_patterns = generate_resource_replaces(compiled_rt)
        
        temps:list[str] = {}
        try:
            resource_files:dict[str, str] = {}
            for resource_name, cts in compiled_rt.items():
                p = replace_patterns[resource_name]
                resource = self.resources[resource_name]
                path = resource.get_path(os.path.join(prefab_file_root, self.resources.dir))
                if path is None:
                    ... #TODO error invalid path, must be inside of the resources dir
                    assert path is not None #DEBUG
                if cts is not None and cts.field_value_transforms:
                    transformed = cts.apply(self.fields, field_values)
                    with open(path, "r") as f:
                        resource_value = f.read()
                    with tempfile.NamedTemporaryFile("w", delete_on_close=False) as tf:
                        resource_files[resource_name] = tf.name
                        temps.append(tf.name)
                        tf.write(p.sub(lambda m: transformed[m[0]], resource_value))
                else:
                    resource_files[resource_name] = path
            if len(self.outputs) != len(compiled_odt):
                ... #TODO exception compiled output destination transformations are incompatible with the current outputs

            working_file:dict[str, str] = {}
            mfiles:dict[str, str] = {}
            for output, cts in zip(self.outputs, compiled_odt):
                rp = resource_files.get(output.resource, None)
                if rp is None:
                    ... #TODO exception compiled resource transformations are incompatible with the current outputs
                    assert rp is not None #DEBUG
                dest_path = os.path.abspath(os.path.join(datafile.DIR, output.destination.file))
                if not dest_path.startswith(datafile.DIR):
                    ... #TODO error output destination file must be within the bot directory
                wfpath = working_file.get(dest_path, rp)
                v = output.destination.prep(output, wfpath, dest_path)

                mfiles[dest_path] = rp
                if v is not None:
                    if wfpath == rp:
                        with tempfile.NamedTemporaryFile("w", delete_on_close=False) as tf, open(rp) as f:
                            working_file[dest_path] = tf.name
                            temps.append(tf.name)
                            shutil.copyfileobj(f, tf)
                    else:
                        with open(wfpath, "w") as f:
                            f.write(v)


            if instance_id is not None:
                instance_path = os.path.join(PREFAB_INSTANCE_DIR, str(instance_id))
                if os.path.isfile(instance_path):
                    with open(instance_path, "rb") as f:
                        old_instance = read_prefab_instance_data(f)
                        old_instance_files = load_prefab_instance_files(f)
                        #TODO merge new changes with old instance values, modify existing instance file with the changes
                        for resource_name, path in resource_files.items():
                            
                else:
                    instance_id = None
            if instance_id is None:
                for dest_path, rp in mfiles.items():
                    src_path = working_file.get(dest_path, rp)
                    shutil.copyfile(src_path, dest_path)
                instance_id = uuid4()
                os.makedirs(PREFAB_INSTANCE_DIR, exist_ok=True)
                instance_path = os.path.join(PREFAB_INSTANCE_DIR, str(instance_id))
                with open(instance_path, "wb") as f:
                    write_prefab_instance(f, self, field_values, resource_files)
        finally:
            for file in temps:
                os.remove(file)
        return instance_id
    
class PrefabInstance(NamedTuple):
    prefab:Prefab
    field_values:dict[str,str]
    resource_names:list[str]

def read_prefab_instance_data(f:IO[bytes]):
    prefab_bytes_len = int.from_bytes(f.read(2), "big")
    field_values_bytes_len = int.from_bytes(f.read(2), "big")
    resource_names_bytes_len = int.from_bytes(f.read(2), "big")

    prefab = Prefab.__new__(Prefab)
    prefab.__setstate__(json.loads(f.read(prefab_bytes_len)))
    field_values = json.load(f.read(field_values_bytes_len))
    resource_names = json.load(f.read(resource_names_bytes_len))
    return PrefabInstance(prefab, field_values, resource_names)

def load_prefab_instance_files(f:IO[bytes], mode:str="r"):
    return zipfile.ZipFile(f, mode=mode)

def get_prefab_instance_file(zf:zipfile.ZipFile, resource_name:str):
    return zf.read(hashlib.sha256(resource_name.encode("utf-8")).hexdigest())

def read_prefab_instance_files(f:IO[bytes], resource_names:list[str]):
    with zipfile.ZipFile(f, "r") as zf:
        for name in resource_names:
            yield name, get_prefab_instance_file(zf, name)

def write_prefab_instance(f:IO[bytes], prefab:Prefab, field_values:FieldValues, resource_files:dict[str, str]):
    prefab_bytes = json.dumps(prefab.__getstate__()).encode("utf-8")
    field_values_bytes = json.dumps(field_values).encode("utf-8")
    resource_names_bytes = json.dumps(list(resource_files.keys())).encode("utf-8")
    f.write(len(prefab_bytes).to_bytes(2, "big"))
    f.write(len(field_values_bytes).to_bytes(2, "big"))
    f.write(len(resource_names_bytes).to_bytes(2, "big"))
    f.write(prefab_bytes)
    f.write(field_values_bytes)
    f.write(resource_names_bytes)
    with zipfile.ZipFile(f, "a") as zf:
        for resource_name, path in resource_files.items():
            zf.write(path, hashlib.sha256(resource_name.encode("utf-8")).hexdigest())

def purge_prefab_instance(uid:UUID|str):
    path = os.path.join(PREFAB_INSTANCE_DIR, str(uid))
    with open(path, "r") as f:
        instance = read_prefab_instance_data(f)
        files = load_prefab_instance_files(f)
        file_cache:dict[str,bytes] = {}
        resource_outputs:dict[str, list[Output]] = {}
        for output in instance.prefab.outputs:
            l = resource_outputs.get(output.resource, None)
            if l is None:
                resource_outputs[output.resource] = [output]
            else:
                l.append(output)
        for resource, outputs in resource_outputs.items():
            for output in outputs:
                dest_path = os.path.abspath(os.path.join(datafile.DIR, output.destination.file))
                contents = file_cache.get(resource,None)
                if contents is None:
                    contents = file_cache[resource] = get_prefab_instance_file(files, resource)
                output.destination.purge(output, dest_path, contents)


def generate_resource_replaces(compiled:dict[str, CompiledTransformations]):
    return {
        resource:re.compile("|".join(re.escape(key) for _, key in cts.field_value_transforms.keys()))
        for resource, cts in compiled.items()
    }

@add_transformation_method("plain")
def transform_plain(field:Field, tr:TransformationReplace, field_value:str):
    subs = {}
    swap_string = tr.options.get("swap_string", None)
    swap_pattern = tr.options.get("swap_pattern", None)
    if isinstance(swap_string, dict):
        for s, v in swap_string.items():
            subs[re.escape(s)] = v
    else:
        swap_string = {}
    if isinstance(swap_pattern, dict):
        subs.update(swap_pattern)
    else:
        swap_pattern = {}
    
    if subs:
        def check_match(m:re.Match[str]):
            s = m[0]
            ss = swap_string.get(s, None)
            if ss is not None:
                return ss
            sp = swap_pattern.get(s, None)
            if sp is not None:
                return sp
            return ""
        field_value = re.sub("|".join(subs.keys()), check_match, field_value)
    
    return field_value
    
@add_transformation_method("json_value")
def transform_json_value(field:Field, tr:TransformationReplace, field_value:str):
    if field.input.get("type" "text") == "number":
        return field_value
    else:
        return json.dumps(field_value)
    
@add_transformation_method("json_string_insert")
def transform_json_string_insert(field:Field, tr:TransformationReplace, field_value:str):
    if field.input.get("type" "text") == "number":
        return field_value
    else:
        return json.dumps(field_value)[1:-1]

@add_transformation_method("tronix_literal_serialized")
def transform_tronix_literal_serialized(field:Field, tr:TransformationReplace, field_value:str):
    s = tronix.Script(field_value)
    p = s.parse()
    if len(p.children) == 1:
        expr = p.children[0]
        if isinstance(expr, (tronix.parsingnodes.ParsingNodeExpression, tronix.parsingnodes.ParsingNodeParentheses)) and len(expr.children) == 1:
            literal = expr.children[0]
            if isinstance(literal, tronix.parsingnodes.ParsingNodeValue):
                return json.dumps(tronix.utils.serialize_value(literal.value, type_str=True))
    #TODO error expected tronix literal str|int|float|null