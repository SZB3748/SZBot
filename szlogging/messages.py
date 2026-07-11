from . import contexts, levels


class Message:
    def __init__(self, level:levels.Level, context:contexts.Context):
        self.level = level
        self.context = context