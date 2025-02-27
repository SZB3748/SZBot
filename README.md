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

### Youtube Setup

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

1. Install requirements.txt: `pip -r requirements.txt`
2. Create a `oauth_twitch.json` file. It should look something like:
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
3. Create a `oauth_youtube.json` file. Start with the contents from the file you downloaded and add the other field(s). It should look something like:
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
4. Create a `config.json` file. It should look something like:
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
    "B-Track": {
        "url": "https://youtube.com/watch?playlist=PLAYLIST_ID",
        "start": 5 //index in playlist to start at (optional, default=1)
    },
    "Playlist": "PLAYLIST_ID",
    "Output-Device": "DEVICE NAME"
}
```
5. Create a `secret.txt` file. Just put a bunch of random keyboard spam in it, or do some research if you want to put a bit more thought into it.
6. Run `main.py`. It will detect that your `oauth.json` file doesn't contain a token and begin the process of generating one. Link your twitch account when it asks to. If you get redirected to a page that says "Restart", then you can restart the server.


### Creating a Playlist

Run the `playlist.py` file and fill out the inputs it asks for. It will create a playlist and display the ID. Put that ID into `config.json` under the `Playlist` field.

## Running

- To run the music queue and web interface, run `main.py`.
- To run the twitch bot, run `bot.py`.
   - If you haven't generated a token yet, make sure you run `main.py` first.