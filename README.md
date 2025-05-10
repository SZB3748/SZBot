# SZBot

Very creative name.

## Setup

### Twitch Application

1. Log into the [Twitch Developer Console](https://dev.twitch.tv/console)
2. "Register a New Application"
   - The name can be whatever
   - Make sure at least one of the OAuth Redirect URLs is `http://localhost:6742/oauth`. If you change the port number, make sure to replace the `6742`.
   - I don't know if you have to set the category to Chat Bot, but I did and it works for me ¯\\_(ツ)_/¯.
   - Set the Client Type to Confidential
   - Copy the Client ID and Client Secret, you'll need them in a few steps.


### Files

1. Install requirements.txt: `pip -r requirements.txt`
   - Currently this includes packages for the built-in plugins as well ( `pngbinds`, `songqueue`, and `soundreq` )
2. Create a `oauth_twitch.json` file (if copy-pasting, remove the `//` comments). It should look something like:
```json
{
    "Client-Id": "YOUR CLIENT ID",
    "Client-Secret": "YOUR CLIENT SECRET",
    "Scopes": [
        //i dont know how many of these are necessary, feel free to experiment
        "chat:read",
        "chat:edit",
        "user:read:chat",
        "user:write:chat",
        "user:bot",
        "channel:bot"
    ]
}
```
3. Create a `config.json` file (if copy-pasting, remove the `//` comments). It should look something like:
```json
{
    "Prefix": "YOUR PREFIX (usually '!')",
    "Channels": [
        "YOUR CHANNEL NAME"
    ],
    //optionally, you can include these fields:
    "Links": {
        "link name (creates a command)": "link text"
    },
    "Style": {
        "text_color": "css color",
        "background_color": "css color",
        "primary_foreground_color": "css color",
        "secondary_foreground_color": "css color",
        "fonts": ["css font name"]
    }
}
```
4. If using any plugins (including the built-in ones), create a `plugins.json` file (if copy-pasting, remove the `//` comments). It should look something like:
```json
{
    "plugin_key": {
        "run": {
            "type": "path",
            "value": "PATH/TO/plugin.py"
        },
        "meta": {
            "type": "path",
            "value": "PATH/TO/plugin.json (usually next to plugin.py)"
        },
        //optional fields:
        "loaded": true, //if the plugin should start
        "enabled": true
    },
    ...
}
```
5. Create a `secret.txt` file. Just put a bunch of random keyboard spam in it, or do some research if you want to put a bit more thought into it.
6. Run `main.py`. It will detect that your `oauth_twitch.json` file doesn't contain a token and begin the process of generating one. Link your twitch account when it asks to. If you get redirected to a page that says "Restart", then you can restart the server.

## Built-In Plugins

Plugins that are included with the source code for SZBot, but still need to be added to `plugins.json` to run. It is recommended you use the folder name for each plugin as its keyname in `plugins.json`.

- [PNG Binds](plugins/pngbinds/README.md)
- [Song Queue](plugins/songqueue/README.md)
- [Sound Request](plugins/soundreq/README.md)

## Running

- To run the main program, run `main.py`
- To run the twitch bot, run `main.py` then `twitchbot.py`