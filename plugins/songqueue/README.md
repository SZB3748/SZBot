# SZBot Song Queue Plugin

[SZBot](https://github.com/SZB3748/SZBot) Plugin

Allows for songs to be requested by chat members. Adds functionality to the web and twitch bot interfaces.

## Setup

### Youtube Data API

Needed to allow for queue-saving functionality.
As songs from the queue finish, they can optionally be added to a specified playlist.

1. Log into the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a New Project
   - If you already have other projects, make sure you select the project you just made.
3. Add the [Youtube Data API v3](https://console.cloud.google.com/marketplace/product/google/youtube.googleapis.com) to your project
4. Configure your project's OAuth Consent Screen and Client
   1. Go to your project's [OAuth Overview](https://console.cloud.google.com/auth/overview)
   2. Go to the "Branding" tab on the left and fill out at least the required fields.
   3. Go to the "Audience" tab on the left and make sure whatever email(s) you'll be using are added as test users.
   4. Go to the "Clients" tab on the left and create a new one.
      - Select the Desktop App type
   5. Go to the "Data Access" tab on the left and add the `https://www.googleapis.com/auth/youtube` scope.
   6. Go back to the "Clients" tab and the download button, then DOWNLOAD JSON button
      - The contents of the file that gets downloaded will be used as the base for the `oauth_youtube.json` file.

### Files

1. Create a `oauth_youtube.json` file in the bot's root folder. Start with the contents from the file you downloaded and add the other field(s). It should look something like:
```json
{
    "installed": {
        ...
    },
    "scopes": [
        "https://www.googleapis.com/auth/youtube"
    ]
}
```
2. There are some extra configs you can specify in `config.json` for this plugin (if copy-pasting, remove the `//` comments). They should all be inside the `Song-Queue` field. All of them are optional. Check this plugin's [plugin.json](plugin.json) or the config editor interface for more info. It should look something like:
```json
{
    ...

    "Song-Queue": {
        "B-Track": {
            //note: "url" is required if "B-Track" is specified
            "url": "https://youtube.com/watch?playlist=PLAYLIST_ID",
            "start": 5,
            "random": true
        },
        "Playlist": "PLAYLIST_ID",
        "Output-Device": "DEVICE_NAME",
        "Song-Blacklist": [
            "youtube video link",
            "youtube video ID"
        ]
    }

    ...
}
```

## Running

For this plugin to run, make sure that it has been added to `plugins.json` with [`plugin.py`](plugin.py) and [`plugin.json`](plugin.json) specified as the run and meta targets.

### Creating a Playlist

Run [`playlist.py`](playlist.py) and fill out the inputs it asks for. It will create a playlist and display the ID. Put that ID into `config.json` under the `Playlist` subfield in `Song-Queue`.


### VLC Plugins

If you get a bunch of warnings about dlls when running `main.py`, then run this command:

- Windows (Admin): `"C:\Program Files\VideoLAN\VLC\vlc-cache-gen.exe" "C:\Program Files\VideoLAN\VLC\plugins"`
- Linux: Haven't tested