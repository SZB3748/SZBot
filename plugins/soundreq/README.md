# SZBot Sound Request Plugin

[SZBot](https://github.com/SZB3748/SZBot) Plugin

Allows for users to request that designated sounds be played. There is currently no support for channel point or bit redeems since I cannot reliably test those things (I'm not affiliate).

## Setup

### Files

There are some extra configs you can specify in `config.json` for this plugin (if copy-pasting, remove the `//` comments). They should all be inside the `PNG-Binds` field. All of them are optional. Check this plugin's [plugin.json](plugin.json) or the config editor interface for more info. It should look something like:
```json
{
    ...

    "Sound-Request": {
        "Sounds": {
            "SOUND_KEY": {
                "name": "sound display name",
                "file": "PATH/TO/SOUND.mp3"
            },
            ...
        },
        "Output-Device": "DEVICE_NAME"
    }
}
```

## Running

For this plugin to run, make sure that it has been added to `plugins.json` with [`plugin.py`](plugin.py) and [`plugin.json`](plugin.json) specified as the run and meta targets.

### VLC Plugins

If you get a bunch of warnings about dlls when running `main.py`, then run this command:

- Windows (Admin): `"C:\Program Files\VideoLAN\VLC\vlc-cache-gen.exe" "C:\Program Files\VideoLAN\VLC\plugins"`
- Linux: Haven't tested