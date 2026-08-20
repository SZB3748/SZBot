from . import soundplayer
from typing import Any

from overlays import media, tronix_integrations as oti
from tronix import duration_types as durtypes, number_units as numunits, script, script_builtins as builtins, utils
from uuid import UUID

def _player_paused_setter(o:script.ScriptValue[soundplayer.Player], n:str, v:script.ScriptVariable[bool]):
    p = o.inner.playback
    if v.get().inner:
        if p.is_playing():
            p.pause()
    elif not p.is_playing():
        p.play()
    return script.wrap_python_value(not p.is_playing())

def _player_playing_setter(o:script.ScriptValue[soundplayer.Player], n:str, v:script.ScriptVariable[bool]):
    p = o.inner.playback
    if v.get().inner:
        if not p.is_playing():
            p.play()
    elif p.is_playing():
        p.pause()
    return script.wrap_python_value(p.is_playing())

def _player_cursor_setter(o:script.ScriptValue[soundplayer.Player], n:str, v:script.ScriptVariable[durtypes._duration|durtypes._complex_duration|int|float]):
    vv = v.get()
    if vv.type.issubtype(builtins.Integer, builtins.Float):
        assert isinstance(vv.inner, (int, bool))
        s = vv.inner
    elif vv.type.issubtype(builtins.Duration):
        assert isinstance(vv.inner, durtypes._duration)
        s = vv.inner.x * durtypes._unitspace_convert(durtypes._seconds_duration.FACTOR, durtypes._seconds_duration.POWER, vv.inner.FACTOR, vv.inner.POWER)
    else:
        assert isinstance(vv.inner, durtypes._complex_duration)
        s = vv.inner.as_seconds()

    return script.wrap_python_value(durtypes._complex_duration(secs=0 if o.inner.playback.audio is None else o.inner.playback.set_elapsed(s)).simplify())

def _player_volume_setter(o:script.ScriptValue[soundplayer.Player], n:str, v:script.ScriptVariable[numunits.percent|int|float]):
    o.inner.playback.main_volume = vol = float(v.get().inner)
    return script.wrap_python_value(numunits.percent(vol))

_AudioPlayerTypeAttrs = utils.ScriptAttributeHandler[soundplayer.Player, Any]()
@_AudioPlayerTypeAttrs.attach
@_AudioPlayerTypeAttrs.enforce_child_attrs()
class _AudioPlayerType(script.ScriptDataType[soundplayer.Player]):

    attrs = _AudioPlayerTypeAttrs
    attrs.entry("playback_cursor")\
            .getter(lambda o, n: script.wrap_python_value(durtypes._complex_duration(ms=0 if o.inner._current is None else o.inner.playback.get_elapsed_ms()).simplify()))\
            .setter(utils.TypedSetter([builtins.Integer, builtins.Float, builtins.Duration, builtins.ComplexDuration], _player_cursor_setter))\
            .nodel()
    attrs.entry("is_paused").getter(lambda o, n: builtins.false if o.inner.playback.is_playing() else builtins.true).setter(utils.TypedSetter(builtins.Bool, _player_paused_setter)).nodel()
    attrs.entry("is_playing").getter(lambda o, n: builtins.true if o.inner.playback.is_playing() else builtins.false).setter(utils.TypedSetter(builtins.Bool, _player_playing_setter)).nodel()
    attrs.entry("current_id").readonly(lambda o, n: builtins.null if o.inner._current is None else script.wrap_python_value(o.inner._current._id))
    attrs.entry("current_duration").readonly(lambda o, n: script.wrap_python_value(durtypes._complex_duration(ms=0 if o.inner._current is None else o.inner.playback.get_duration_ms()).simplify()))
    attrs.entry("volume").getter(lambda o, n: script.wrap_python_value(numunits.percent(o.inner.playback.main_volume))).setter(utils.TypedSetter([builtins.Integer, builtins.Float, builtins.Percent], _player_volume_setter)).nodel()


class SoundRequest_t(builtins._pair[UUID, int]):
    pass


SoundRequest = builtins.pair_alias_subtype("SoundRequest", ["request_id"], ["enqueued_at_position"], SoundRequest_t)
AudioPlayer = _AudioPlayerType("AudioPlayer", soundplayer.Player, script.BASE_TYPE)

f_play_sound = utils.ScriptFunction()
f_skip_sound = utils.ScriptFunction()
f_pause_sounds = utils.ScriptFunction()
f_resume_sounds = utils.ScriptFunction()
f_get_sound_queue_position = utils.ScriptFunction()
f_get_default_audio_player = utils.ScriptFunction()

def _player_or_default(ap:script.ScriptValue[soundplayer.Player]):
    if ap.inner is None:
        if soundplayer.main_player is None:
            assert False #TODO error no sound player
        return soundplayer.main_player
    else:
        assert isinstance(ap.inner, soundplayer.Player)
        return ap.inner

@f_play_sound.overload(("media_entry", [oti.MediaEntry, builtins.String]), ("audio_player", [AudioPlayer, builtins.NullType], None), ("output_device_name", [builtins.String, builtins.NullType], None), ("url_prefix", [builtins.String, builtins.NullType], None), ("volume", [builtins.Percent, builtins.Float, builtins.Integer], 1.0))
async def play_sound(media_entry:script.ScriptVariable[media.MediaEntry|str], audio_player:script.ScriptVariable[soundplayer.Player|None], output_device_name:script.ScriptVariable[str|None], url_prefix:script.ScriptVariable[str|None], volume:script.ScriptVariable[numunits.percent|float|int]):
    v = media_entry.get()
    if v.type.issubtype(oti.MediaEntry):
        assert isinstance(v.inner, media.MediaEntry)
        entry = v.inner
        mime = entry.resolve_type()
        if mime is None:
            ... #TODO error could not resolve mimetype
        elif not mime.startswith("audio/"):
            ... #TODO error mimetype must be audio
        name = v.inner.name
    else:
        assert isinstance(v.inner, str)
        name = v.inner
    p = _player_or_default(audio_player.get())
    urlp = url_prefix.get().inner
    ltype = soundplayer.LOC_TYPE_LOCAL if urlp is None else soundplayer.LOC_TYPE_URL
    uid, l = await p.add_to_queue(name, ltype, urlp, output_device_name.get().inner, float(volume.get().inner))
    return script.wrap_python_value(SoundRequest.inner(uid, l-1))

@f_skip_sound.overload(("request", [SoundRequest, builtins.UUID]), ("audio_player", [AudioPlayer, builtins.NullType], None))
async def skip_sound(request:script.ScriptVariable[SoundRequest_t|UUID], audio_player:script.ScriptVariable[soundplayer.Player|None]):
    r = request.get()
    if r.type.issubtype(SoundRequest):
        assert isinstance(r.inner, SoundRequest_t)
        rid = r.inner.first
    else:
        assert isinstance(r.inner, UUID)
        rid = r.inner
    p = _player_or_default(audio_player.get())
    skipped = await p.skip_id(rid)
    return script.wrap_python_value([item._id for item in skipped])
    

@f_pause_sounds.overload(("audio_player", [AudioPlayer, builtins.NullType], None))
def pause_sounds(audio_player:script.ScriptVariable[soundplayer.Player|None]):
    p = _player_or_default(audio_player.get())
    if p.playback.is_playing():
        p.playback.pause()
    return script.wrap_python_value(not p.playback.is_playing())

@f_resume_sounds.overload(("audio_player", [AudioPlayer, builtins.NullType], None))
def resume_sounds(audio_player:script.ScriptVariable[soundplayer.Player|None]):
    p = _player_or_default(audio_player.get())
    if not p.playback.is_playing():
        p.playback.play()
    return script.wrap_python_value(p.playback.is_playing())

@f_get_sound_queue_position.overload(("request", [SoundRequest, builtins.UUID]), ("audio_player", [AudioPlayer, builtins.NullType], None))
def get_sound_queue_position(request:script.ScriptVariable[SoundRequest_t|UUID], audio_player:script.ScriptVariable[soundplayer.Player|None]):
    r = request.get()
    if r.type.issubtype(SoundRequest):
        assert isinstance(r.inner, SoundRequest_t)
        rid = r.inner.first
    else:
        assert isinstance(r.inner, UUID)
        rid = r.inner
    p = _player_or_default(audio_player.get())
    with p._queuelock:
        cur = p._queue._head
        i = 0
        while cur is not None:
            if cur._id == rid:
                return script.wrap_python_value(i)
            cur = cur._next
            i += 1
    return builtins.null

@f_get_default_audio_player.overload()
def get_default_audio_player():
    return script.wrap_python_value(soundplayer.main_player)


def activate():
    utils.add_type(SoundRequest, constructor=False)
    utils.add_type(AudioPlayer, constructor=False)

    utils.merge_function("play_sound", f_play_sound)
    utils.merge_function("skip_sound", f_skip_sound)
    utils.merge_function("pause_sounds", f_pause_sounds)
    utils.merge_function("resume_sounds", f_resume_sounds)
    utils.merge_function("get_sound_queue_position", f_get_sound_queue_position)
    utils.merge_function("get_default_audio_player", f_get_default_audio_player)

def deactivate():
    utils.remove_type(SoundRequest)
    utils.remove_type(AudioPlayer)

    utils.remove_function("play_sound", f_play_sound)
    utils.remove_function("skip_sound", f_skip_sound)
    utils.remove_function("pause_sounds", f_pause_sounds)
    utils.remove_function("resume_sounds", f_resume_sounds)
    utils.remove_function("get_sound_queue_position", f_get_sound_queue_position)
    utils.remove_function("get_default_audio_player", f_get_default_audio_player)