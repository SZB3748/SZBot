from . import medialist, statemapping, webroutes
import events
import os
import plugins
import web


nav:statemapping.StateMapNavigator = None

def dispatch_state_change_event():
    if nav is not None and nav.stack is not None:
        state = nav.stack.state
        if state is not None:
            events.dispatch(events.Event("pngbinds:state_change", {"name": state.name, "media": state.media.__getstate__()}))
            return
    events.dispatch(events.Event("pngbinds:state_change", {"name": None, "media": None}))
    

def on_nav_push(old:statemapping.NavigatorStackFrame|None, new:statemapping.NavigatorStackFrame):
    dispatch_state_change_event()
    oldname = None
    if old is not None and old.state is not None:
        oldname = old.state.name
    newname = None if new.state is None else new.state.name
    print(f"pngbinds:\t{oldname} >> {newname}")

def on_nav_pop(old:statemapping.NavigatorStackFrame, new:statemapping.NavigatorStackFrame|None):
    dispatch_state_change_event()
    oldname = None if old.state is None else old.state.name
    newname = None
    if new is not None and new.state is not None:
        newname = new.state.name
    print(f"pngbinds:\t{newname} << {oldname}")

def on_nav_change(old:statemapping.NavigatorStackFrame, new:statemapping.NavigatorStackFrame):
    dispatch_state_change_event()
    oldname = None if old.state is None else old.state.name
    newname = None if new.state is None else new.state.name
    print(f"pngbinds:\t{oldname} -> {newname}")


#can be overriden
def create_navigator(statemap:statemapping.StateMap, default_state:str,
                     on_push:statemapping.OnPushCallback, on_pop:statemapping.OnPopCallback, on_change:statemapping.OnChangeCallback):
    return statemapping.StateMapNavigator(statemap, default_state, on_push, on_pop, on_change)

def on_load(ctx:plugins.LoadEvent):
    global nav

    if not os.path.isdir(medialist.MEDIA_DIR):
        os.mkdir(medialist.MEDIA_DIR)

    if os.path.isfile(statemapping.STATEMAP_FILE):
        with open(statemapping.STATEMAP_FILE) as f:
            statemap = statemapping.StateMap.load(f)
    else:
        statemap = statemapping.StateMap()

    #TODO determine the default state (config.json)

    nav = create_navigator(statemap, None, on_nav_push, on_nav_pop, on_nav_change)
    nav.init_default()

    webroutes.web_loaded = True

def on_unload(ctx:plugins.UnloadEvent):
    if nav.stack is not None:
        nav.unbind_frame(nav.stack)
        nav.stack = None
    dispatch_state_change_event()
    webroutes.web_loaded = False


webroutes.add_routes(web.app, web.api)
