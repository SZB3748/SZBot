# SZBot

Very creative name.

## Setup

### Twitch Application

1. Log into the [Twitch Developer Console](https://dev.twitch.tv/console)
2. "Register a New Application"
   - The name can be whatever
   - Make sure at least one of the OAuth Redirect URLs is `http://localhost:6742/oauth`. If you run the bot with a different port number, make sure to replace the `6742`.
   - I don't know if you have to set the category to Chat Bot, but I did and it works for me ¯\\_(ツ)_/¯.
   - Set the Client Type to Confidential
   - Copy the Client ID and Client Secret, you'll need them in a few steps.


### Files

1. Install requirements.txt: `pip -r requirements.txt`
   - Currently this also includes packages for the built-in plugins as well ( `pngbinds`, `songqueue`, and `soundreq` )
2. Create a `oauth_twitch.json` file. It should look something like:
```json
{
    "identity": {
        "Bot-Name": "YOUR BOT ACCOUNT'S NAME (either make a new account or use your own)",
        "Client-Id": "YOUR CLIENT ID",
        "Client-Secret": "YOUR CLIENT SECRET"
    },
    "channels": {
        "YOUR CHANNEL": null
    }
}
```
3. Create a `config.json` file (if copy-pasting, remove the `//` comments). It should look something like:
```json
{
    "Prefix": "YOUR PREFIX (usually '!')",
    //optionally, you can include these fields:
    "Links": {
        "link name (creates a command)": "text to send when someone uses the command"
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
        "loaded": true,   //if the plugin should run when the bot starts
        "enabled": true,  //if the plugin should be able to run at all
        "components": {
            "component name (see plugin for details)": "mode name (see plugin for details)"
        }
    },
    ...
}
```
5. Create a `secret.txt` file. You can just put a bunch of random keyboard spam in it, or do some research if you want to put a bit more thought into it.
6. Get the OAuth tokens for the twitch bot.
    - Run `twitch_reauth.py` and make sure to link with the account you plan for the bot to send messages through
    - Run `twitch_reauth.py -s channel` and link with the account (channel) you want your bot to act in

## Built-In Plugins

Plugins that are included with the source code for SZBot, but still need to be added to `plugins.json` to run. It is recommended you use the folder name for each plugin as its keyname in `plugins.json`.

- [PNG Binds](plugins/pngbinds/README.md)
- [Song Queue](plugins/songqueue/README.md)
- [Sound Request](plugins/soundreq/README.md)

## Running

- To run the main program, run `main.py`
- To run the twitch bot, run `main.py` then `twitchbot.py`

For more info on customizing how these files are run, add the `-h` argument when running either of them.