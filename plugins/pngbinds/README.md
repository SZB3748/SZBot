# SZBot PNG Binds Plugin

[SZBot](https://github.com/SZB3748/SZBot) Plugin

Creates an overlay which displays different images, and allows for transitions between these images when set keybinds are pressed.

## Setup

### Files

There are some extra configs you can specify in `config.json` for this plugin (if copy-pasting, remove the `//` comments). They should all be inside the `PNG-Binds` field. All of them are optional. Check this plugin's [plugin.json](plugin.json) or the config editor interface for more info. It should look something like:
```json
{
    ...

    "PNG-Binds": {
        "Default-State": "STATE_NAME"
    }

    ...
}
```

## Running

For this plugin to run, make sure that it has been added to `plugins.json` with [`plugin.py`](plugin.py) and [`plugin.json`](plugin.json) specified as the run and meta targets.

### Adding States, Transitions, and Media

After running `main.py`, go to [http://localhost:6742/pngbinds/media]. Here, you can add images and gifs to use for the overlay. You'll want to add an asset for the border and some content assets.

Next, go to [http://localhost:6742/pngbinds]. Here, you can add/edit states and the keybinds that will be made to transition between them. Each state has a border and content asset. Transitions have a state, a keybind, an activation mode, and a transition.

### VLC Plugins

If you get a bunch of warnings about dlls when running `main.py`, then run this command:

- Windows (Admin): `"C:\Program Files\VideoLAN\VLC\vlc-cache-gen.exe" "C:\Program Files\VideoLAN\VLC\plugins"`
- Linux: Haven't tested