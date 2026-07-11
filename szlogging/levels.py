
class Level:
    def __init__(self, name:str, value:float):
        self.name = name
        self.value = value
    
    def __str__(self):
        return self.name
    

DEBUG = Level("debug", -1.0)
INFO = Level("info", 0.0)
WARN = Level("warn", 1.0)
ERROR = Level("error", 2.0)