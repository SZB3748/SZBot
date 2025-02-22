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
2. Create a `oauth.json` file. It should look something like:
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
3. Create a `config.json` file. It should look something like:
```json
{
    "Prefix": "YOUR PREFIX", //Usually "!"
    "Channels": [
        "YOUR CHANNEL"
    ],
    //optionally, you can specify a device to play music on
    "Output-Device": "DEVICE NAME" //exclude field to use the default device
}
```
4. Create a `secret.txt` file. Just put a bunch of random keyboard spam in it, or do some research if you want to put a bit more thought into it.
5. Run `main.py`. It will detect that your `oauth.json` file doesn't contain a token and begin the process of generating one. Link your twitch account when it asks to. If you get redirected to a page that says "Restart", then you can restart the server.


## Running

- To run the music queue and web interface, run `main.py`.
- To run the twitch bot, run `bot.py`.
   - If you haven't generated a token yet or the token becomes invalid, run `main.py` first.