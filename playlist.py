import config
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
import json

def get_authenticated_service():
    """Authorize the request and store authorization credentials."""

    with open(config.OAUTH_YOUTUBE_FILE) as f:
        configs = json.load(f)
    credentials = None
    if "credentials" in configs:
        authed = configs["credentials"]
        if isinstance(authed, dict):
            credentials = Credentials.from_authorized_user_info(authed)

    if not (credentials and credentials.valid):
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_config(configs, configs["scopes"])
            credentials = flow.run_local_server(port=0)
        
        config.write(config_updates={
            "credentials": json.loads(credentials.to_json())
        }, path=config.OAUTH_YOUTUBE_FILE)
    
    return build("youtube", "v3", credentials=credentials)

def add_video(youtube, playlist_id:str, video_id:str):
    request = youtube.playlistItems().insert(part="snippet", body={
        "snippet": {
            "playlistId": playlist_id,
            "resourceId": {
                "kind": "youtube#video",
                "videoId": video_id
            }
        }
    })

    return request.execute()

def create_playlist(youtube, name, description, status):
    body = {
        "snippet": {
            "title": name,
            "description": description
        },
        "status": {
            "privacyStatus": status
        }
    }
    
    request = youtube.playlists().insert(part="snippet,status", body=body)
    return request.execute()
    

if __name__ == "__main__":
    name = input("Enter a playlist name: ")
    description = input("Enter a playlist description: ")
    status = input("Enter a playlist status [public/unlisted/private] (defaults to unlisted): ").strip() or "unlisted"
    youtube = get_authenticated_service()
    id = create_playlist(youtube, name, description, status)["id"]
    print("Created playlist with ID:", id)