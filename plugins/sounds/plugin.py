from . import soundplayer, tronix_integrations as sti, webroutes


import actions
import asyncio
import plugins
import tronix_integrations as ti
import web


COMPONENT_API = "api"
COMPONENT_PLAYER = "player"
COMPONENT_TRONIX = "tronix"

player_handle:asyncio.Handle|None = None

def on_load(ctx:plugins.LoadEvent):
    global player_handle

    webroutes.web_loaded = True

    m_api = ctx.plugin.get_component_mode(COMPONENT_API)
    m_player = ctx.plugin.get_component_mode(COMPONENT_PLAYER)
    m_tronix = ctx.plugin.get_component_mode(COMPONENT_TRONIX)

    if ctx.is_start:
        webroutes.add_routes(web.api, m_api == plugins.COMPONENT_MODE_NORMAL)
        if m_api == plugins.COMPONENT_MODE_REMOTE:
            web.create_component_proxy(web.api, webroutes.soundsapi.name, webroutes.soundsapi.url_prefix, socket=False)
    
    assert m_player != plugins.COMPONENT_MODE_REMOTE, "Sound Player has no remote mode."
    assert m_tronix != plugins.COMPONENT_MODE_REMOTE, "Sound Player has no remote mode."

    if m_player == plugins.COMPONENT_MODE_NORMAL:
        soundplayer.main_player = soundplayer.Player()
        player_handle = actions.shared_loop.call_soon_threadsafe(soundplayer.main_player.handle)
    
    if m_tronix == plugins.COMPONENT_MODE_NORMAL:
        if ctx.is_start:
            ti.activation_handlers[ctx.plugin.name] = sti.activate
        else:
            sti.activate()
        ti.deactivation_handlers[ctx.plugin.name] = sti.deactivate

def on_unload(ctx:plugins.UnloadEvent):
    global player_handle
    webroutes.web_loaded = False
    
    tronix_deactivate = ti.deactivation_handlers.pop(ctx.plugin.name, None)
    if tronix_deactivate is not None:
        tronix_deactivate()

    if soundplayer.main_player is not None:
        soundplayer.main_player.stop()
        soundplayer.main_player = None
    if player_handle is not None:
        player_handle.cancel()
        player_handle = None