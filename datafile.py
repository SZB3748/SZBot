import os

DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(DIR, "data")

def makepath(*paths:str, dir:str=None):
    return os.path.join(DATA_DIR if dir is None else dir, *paths)
