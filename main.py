import web

import config
import songqueue
from urllib.parse import quote

OAUTH_ENDPOINT = "https://id.twitch.tv/oauth2/authorize"

def get_auth_token():
    import webbrowser
    redirect = f"http://localhost:8080/oauth"
    scope = " ".join(configs["Scopes"])
    webbrowser.open(f"{OAUTH_ENDPOINT}?response_type=code&client_id={configs["Client-Id"]}&redirect_uri={quote(redirect)}&scope={quote(scope)}")
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
        songqueue.song_done()
        songqueue.stop_loop.set()
        songqueue.queue_populated.set() #just making sure the cycle stops
        print("Waiting for song cycle to stop...")
        cycle.join(5)
        if cycle.is_alive():
            print("Song cycle failed to stop after 5 seconds")
        else:
            print("Song cycle stopped")

if __name__ == "__main__":
    configs = config.read()
    if "Token" not in configs:
        try:
            get_auth_token()
        except KeyboardInterrupt:
            pass
        exit(0)
    else:
        run()