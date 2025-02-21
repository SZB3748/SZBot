import json

CONFIG_FILE = "config.json"

def read(path:str=CONFIG_FILE)->dict[str]:
    with open(path) as f:
        return json.load(f)
    

def write(new_configs:dict[str]|None=None, config_updates:dict[str]|None=None, path:str=CONFIG_FILE):
    with open(path, "r+") as f:
        contents = f.read()
        configs:dict[str] = new_configs if new_configs is not None else json.loads(contents)
        if config_updates is not None:
            configs.update(**config_updates)
        f.seek(0)
        f.truncate()
        try:
            json.dump(configs, f, indent=4)
        except:
            f.write(contents)
            raise