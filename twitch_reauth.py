import argparse
import config
import plugins
import twitchbot
from urllib.parse import quote
import web

parser = argparse.ArgumentParser(description="Script for generating twitch OAuth tokens.")
parser.add_argument("-d", "--host", default=None, help="Host to run the redirect-handling webserver on. Defaults to 127.0.0.1:6742")
parser.add_argument("-s", "--scopes", choices=["identity", "channel"], default="identity", help="Category of scopes to use when authenticating.")

OAUTH_ENDPOINT = "https://id.twitch.tv/oauth2/authorize"
DEFAULT_ADDR = web.HOST, web.PORT

def get_auth_token(oauth:dict[str], addr:tuple[str, int]=DEFAULT_ADDR, redirect:str="http://{host}:{port}/oauth", scopes=twitchbot.OAUTH_SCOPES):
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
    addr_arg:str = args.host
    if addr_arg is None:
        addr = DEFAULT_ADDR
    elif ":" in addr_arg:
        host, port = addr_arg.split(":", 1)
        host = host.strip().lower()
        # using localhost can cause significant slowdowns for the
        # API proxy on Windows. cite: https://stackoverflow.com/a/75425128
        if host == "localhost":
            host = "127.0.0.1"
        if host and port:
            if port.isdecimal():
                addr = host, int(port)
            else:
                print("Address port must be an integer")
                exit(-1)
        elif port and not port.isdecimal():
            print("Address port must be an integer")
            exit(-1)
        else:
            addr = host or web.HOST, int(port) if port else web.PORT
    elif addr_arg.isdecimal():
        addr = web.HOST, int(addr_arg)
    else:
        host = addr_arg.strip().lower()
        addr = "127.0.0.1" if host == "localhost" else host, web.PORT
    get_auth_token(config.read(path=config.OAUTH_TWITCH_FILE), addr=addr, scopes=scopes)
