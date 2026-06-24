import plugins

class _UnsassignedType(object):
    def __repr__(self):
        return "<UNASSIGNED runtime value>"
    
    def __getattr__(self, name):
        raise RuntimeError("Runtime value was never assigned to.")
    
    def __setattr__(self, name, value):
        raise RuntimeError("Runtime value was never assigned to.")
    
    def __delattr__(self, name):
        raise RuntimeError("Runtime value was never assigned to.")

    def __getitem__(self, key):
        raise RuntimeError("Runtime value was never assigned to.")

    def __setitem__(self, key, value):
        raise RuntimeError("Runtime value was never assigned to.")

    def __delitem__(self, key):
        raise RuntimeError("Runtime value was never assigned to.")
    
UNASSIGNED = _UnsassignedType()
_UnsassignedType.__new__ = lambda cls: UNASSIGNED

host_addr:tuple[str, int] = UNASSIGNED
remote_addr:tuple[str, int]|tuple[None, None] = UNASSIGNED
remote_secure:bool = UNASSIGNED
plugin_list:dict[str,plugins.Plugin] = UNASSIGNED
plugin_load_order:list[str] = UNASSIGNED
core_components:dict[str,str|None] = UNASSIGNED

NO_REMOTE_ADDRESS = None,None