import config
import plugins
import twitchbot
from urllib.parse import quote
import web

OAUTH_ENDPOINT = "https://id.twitch.tv/oauth2/authorize"

def get_auth_token(oauth:dict[str], addr:tuple[str, int]=(web.HOST, web.PORT)):
    import webbrowser
    host, port, *_ = addr
    if host == "127.0.0.1":
        host = "localhost"
    redirect = f"http://{host}:{port}/oauth"
    scope = " ".join(twitchbot.OAUTH_SCOPES)
    url = f"{OAUTH_ENDPOINT}?response_type=code&client_id={oauth["Client-Id"]}&redirect_uri={quote(redirect,safe="")}&scope={quote(scope,safe="+")}"
    try:
        webbrowser.open(url)
        print("Opening", url, "in your default browser")
    except:
        print("Could not automatically find a browser, open", url, "in a browser")
    web.serve(host, port)


if __name__ == "__main__":
    get_auth_token(config.read(path=config.OAUTH_TWITCH_FILE))
