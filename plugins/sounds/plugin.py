from . import soundplayer, tronix_integrations as sti, webroutes

import actions
import asyncio
import plugins
import tronix_integrations as ti
import web


COMPONENT_API = "api"
COMPONENT_PLAYER = "player"
COMPONENT_TRONIX = "tronix"

init = plugins.PluginInit().bind()

player_handle:asyncio.Future|None = None

@init.event()
def on_load(ctx:plugins.LoadEvent):
    global player_handle

    webroutes.web_loaded = True

    m_api = ctx.plugin.get_component_mode(COMPONENT_API)
    m_player = ctx.plugin.get_component_mode(COMPONENT_PLAYER)
    m_tronix = ctx.plugin.get_component_mode(COMPONENT_TRONIX)

    if ctx.is_start:
        webroutes.add_routes(web.api, plugins.is_normal(m_api))
        if plugins.is_remote(m_api):
            web.create_component_proxy(web.api, webroutes.soundsapi.name, webroutes.soundsapi.url_prefix, socket=False)

    if plugins.is_normal(m_player):
        soundplayer.main_player = soundplayer.Player()
        player_handle = asyncio.run_coroutine_threadsafe(soundplayer.main_player.handle(), loop=actions.shared_loop)
    
    if plugins.is_normal(m_tronix):
        if ctx.is_start:
            ti.activation_handlers[ctx.plugin.name] = sti.activate
        else:
            sti.activate()
        ti.deactivation_handlers[ctx.plugin.name] = sti.deactivate

@init.event()
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