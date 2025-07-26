import argparse
import config
import plugins
import twitchbot
from urllib.parse import quote
import web

parser = argparse.ArgumentParser(description="Script for generating twitch OAuth tokens.")
parser.add_argument("-s", "--scopes", choices=["identity", "channel"], default="identity", help="Category of scopes to use when authenticating.")

OAUTH_ENDPOINT = "https://id.twitch.tv/oauth2/authorize"

def get_auth_token(oauth:dict[str], addr:tuple[str, int]=(web.HOST, web.PORT), redirect:str="http://{host}:{port}/oauth", scopes=twitchbot.OAUTH_SCOPES):
    import webbrowser
    host, port, *_ = addr
    if host == "127.0.0.1":
        host = "localhost"
    redirect = redirect.format(host=host, port=port)
    scope = "+".join(scopes)
    url = f"{OAUTH_ENDPOINT}?response_type=code&client_id={oauth["identity"]["Client-Id"]}&redirect_uri={quote(redirect,safe="")}&scope={quote(scope,safe="+")}"
    try:
        webbrowser.open(url)
        print("Opening", url, "in your default browser")
    except:
        print("Could not automatically find a browser, open", url, "in a browser")
    try:
        web.serve(host, port)
    except OSError:
        print("Webserevr is already running, or had oter issues which prevented it from starting.")


if __name__ == "__main__":
    args = parser.parse_args()
    if args.scopes == "channel":
        scopes = twitchbot.OAUTH_CHANNEL_SCOPES
    else:
        scopes = twitchbot.OAUTH_SCOPES
    get_auth_token(config.read(path=config.OAUTH_TWITCH_FILE), scopes=scopes)
