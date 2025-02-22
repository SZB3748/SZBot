import web

import config
import songqueue
from urllib.parse import quote

OAUTH_ENDPOINT = "https://id.twitch.tv/oauth2/authorize"

def get_auth_token(oauth:dict[str]):
    import webbrowser
    redirect = f"http://localhost:6742/oauth"
    scope = " ".join(oauth["Scopes"])
    webbrowser.open(f"{OAUTH_ENDPOINT}?response_type=code&client_id={oauth["Client-Id"]}&redirect_uri={quote(redirect)}&scope={quote(scope)}")
    web.serve()


def run():
    print("starting music queue")
    cycle = songqueue.run_song_cycle()
    print("bot must be started manually")
    try:
        print("stating web server")
        web.serve()
    except KeyboardInterrupt:
        pass
    finally:
        songqueue.song_done.set()
        songqueue.stop_loop.set()
        print("Waiting for song cycle to stop...")
        cycle.join(5)
        if cycle.is_alive():
            print("Song cycle failed to stop after 5 seconds")
        else:
            print("Song cycle stopped")

if __name__ == "__main__":
    oauth = config.read(path=config.OAUTH_FILE)
    if not ("Client-Id" in oauth and "Client-Secret" in oauth and "Scopes" in oauth):
        print("You must create an oauth.json file with your twitch application's \"Client-Id\", \"Client-Secret\", and \"Scopes\".")
    elif "Token" not in oauth:
        try:
            get_auth_token(oauth)
        except KeyboardInterrupt:
            pass
        exit(0)
    else:
        run()