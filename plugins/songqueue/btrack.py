import argparse
import json
import os
import requests
import subprocess
import sys
import time
from typing import IO

class BTrackEntry:
    def __init__(self, id:str, title:str, duration:str, thumbnail_path:str, song_path:str):
        self.id = id
        self.title = title
        self.duration = duration
        self.thumbnail_path = thumbnail_path
        self.song_path = song_path

    def __getstate__(self):
        return self.__dict__.copy()
    
    def __setstate__(self, d:dict):
        self.__dict__.update(d)

BTrackData = dict[str, BTrackEntry] #{id: data}

def load_data_file(file_or_path:str|IO)->BTrackData:
    if isinstance(file_or_path, str):
        if not os.path.isfile(file_or_path):
            return {}
        with open(file_or_path) as f:
            raw = json.load(f)
    else:
        raw = json.load(file_or_path)
    if not isinstance(raw, dict):
        return {}
    rtv = {}
    for k, d in raw.items():
        entry = BTrackEntry.__new__(BTrackEntry)
        d["id"] = k
        entry.__setstate__(d)
        rtv[k] = entry
    return rtv

def save_data_file(data:BTrackData, file_or_path:str|IO, indent=""):
    raw = {}
    for k, entry in data.items():
        d = entry.__getstate__()
        if "id" in d:
            del d["id"]
        raw[k] = d
    if isinstance(file_or_path, str):
        raw_s = json.dumps(raw, indent=indent)
        with open(file_or_path, "w") as f:
            f.write(raw_s)
    else:
        json.dump(file_or_path, raw, indent=indent)


parser = argparse.ArgumentParser(description="Tool used to manage local B Track for SZBot Songqueue Plugin.")
parser.add_argument("playlist_url", help="URL for the youtube playlist to use.")
parser.add_argument("song_dir", help="Directory to use for storing song files.")
parser.add_argument("thumbnail_dir", help="Directory to use for storing song thumbnails.")
parser.add_argument("data_file", help="File that keeps all song metadata.")
parser.add_argument("--skip-existing", action="store_true", default=False, help="When used, skips downloading songs that are already downloaded.")
parser.add_argument("--skip-songs", action="store_true", default=False, help="When used, skips downloading songs; only downloads thumbnails and fetches metadata (if enabled).")
parser.add_argument("--skip-thumbnails", action="store_true", default=False, help="When used, skips downloading thumbnails; only downloads songs and fetches metadata (if enabled).")
parser.add_argument("--skip-data", action="store_true", default=False, help="When used, skips fetching metadata; only downloads songs and thumbnails (if enabled).")

SongInfoSet = set[tuple[str, str, str]] #id,duration,title

def fetch_song_info(playlist_url:str)->SongInfoSet:
    p = subprocess.run(["yt-dlp", "--flat-playlist", "--print", "%(id)s\t%(duration>%H:%M:%S)s\t%(title)s", playlist_url], capture_output=True)
    lines_s = p.stdout.strip().decode("utf-8", "ignore")
    if not lines_s:
        return set()
    lines = lines_s.split("\n")
    return {tuple(line.split("\t", 2)) for line in lines}

def download_song(filepath:str, video_url:str):
    p = subprocess.Popen(["yt-dlp", "--ignore-errors", "-f", "bestaudio", video_url, "-o", filepath], stderr=subprocess.PIPE)
    t = 60
    while p.poll() is None:
        err = p.stderr.read()
        if err and b"Got error: HTTP Error 403: Forbidden" in err:
            p.terminate()
            print("Got HTTP Error 403 (ratelimitng), waiting", t, "seconds before retrying...", file=sys.stderr)
            time.sleep(t)
            t *= 2
            p = subprocess.Popen(["yt-dlp", "--ignore-errors", "-f", "bestaudio", video_url, "-o", filepath], stderr=subprocess.PIPE)
        else:
            t = 60
        yield


def compare_song_info(remote_info:SongInfoSet, local_info:BTrackData):
    l = {(e.id, e.duration, e.title) for e in local_info.values()}
    new, removed = remote_info - l, l - remote_info
    new_ids = {id for id, *_ in new}
    removed_ids = {id for id, *_ in removed}
    changed = new_ids.intersection(removed_ids)
    return new, removed, changed


if __name__ == "__main__":
    args = parser.parse_args()

    if args.skip_songs and args.skip_thumbnails and args.skip_data:
        print("Noting to do.")
        exit(0)

    do_songs:bool = not args.skip_songs
    do_thumbnails:bool = not args.skip_thumbnails
    do_data:bool = not args.skip_data
    
    remote_song_info = fetch_song_info(args.playlist_url)
    local_song_info = load_data_file(args.data_file)

    thumbnail_download_queue:list[tuple[str, str]] = []
    song_download_queue:list[tuple[str, str]] = []

    new_entries:BTrackData = {}
    if local_song_info:
        new_info, removed_info, changed = compare_song_info(remote_song_info, local_song_info)
        changed = {id for id, *_ in new_info}.intersection({id for id, *_ in removed_info})
        print(f"Stats: Added {len(new_info) - len(changed)}, Removed {len(removed_info) - len(changed)}, Changed {len(changed)}")
        song_dir = os.path.abspath(args.song_dir)
        thumbnail_dir = os.path.abspath(args.thumbnail_dir)
        if not os.path.isdir(song_dir):
            os.mkdir(song_dir)
        if not os.path.isdir(thumbnail_dir):
            os.mkdir(thumbnail_dir)

        dont_remove = set()

        for id, duration, title in new_info:
            # if id in local_song_info:
            #     entry = local_song_info[id]
            #     entry.title = title
            #     entry.duration = duration
            #     changed_ids.add(id)
            # else:
            thumbnail_file = os.path.join(thumbnail_dir, f"{id}.jpg")
            song_file = os.path.join(song_dir, id)
            if not (args.skip_existing and os.path.isfile(thumbnail_file)):
                thumbnail_download_queue.append((thumbnail_file, f"https://img.youtube.com/vi/{id}/hqdefault.jpg"))
            if not (args.skip_existing and os.path.isfile(song_file)):
                song_download_queue.append((id, song_file, f"https://youtube.com/watch?v={id}"))
            if args.skip_existing and id in local_song_info:
                dont_remove.add(id)
            else:
                new_entries[id] = BTrackEntry(id, title, duration, thumbnail_file, song_file)

        for id, *_ in removed_info:
            # if id in changed_ids:
            #     continue
            if id in dont_remove:
                continue
            if do_data:
                entry = local_song_info.pop(id)
            if do_thumbnails and os.path.isfile(entry.thumbnail_path):
                os.remove(entry.thumbnail_path)
            if do_songs and os.path.isfile(entry.song_path):
                os.remove(entry.song_path)

        for id, entry in local_song_info.items():
            if id in changed:
                continue
            if not os.path.isfile(entry.thumbnail_path):
                thumbnail_download_queue.append((entry.thumbnail_path, f"https://img.youtube.com/vi/{id}/hqdefault.jpg"))
            if not os.path.isfile(entry.song_path):
                song_download_queue.append((id, entry.song_path, f"https://youtube.com/watch?v={id}"))
        
    else:
        song_dir = os.path.abspath(args.song_dir)
        thumbnail_dir = os.path.abspath(args.thumbnail_dir)
        if not os.path.isdir(song_dir):
            os.mkdir(song_dir)
        if not os.path.isdir(thumbnail_dir):
            os.mkdir(thumbnail_dir)

        for id, duration, title in remote_song_info:
            thumbnail_file = os.path.join(thumbnail_dir, f"{id}.jpg")
            song_file = os.path.join(song_dir, id)
            if not (args.skip_existing and os.path.isfile(thumbnail_file)):
                thumbnail_download_queue.append((thumbnail_file, f"https://img.youtube.com/vi/{id}/hqdefault.jpg"))
            if not (args.skip_existing and os.path.isfile(song_file)):
                song_download_queue.append((id, song_file, f"https://youtube.com/watch?v={id}"))
            new_entries[id] = BTrackEntry(id, title, duration, thumbnail_file, song_file)


    if do_songs:
        for id, filepath, video_url in song_download_queue:
            for _ in download_song(filepath, video_url):
                continue
            if not os.path.isfile(filepath):
                print(f"Failed to download song for {id}, removing")
                if id in local_song_info:
                    del local_song_info[id]
                if id in new_entries:
                    del new_entries[id]

    if do_thumbnails:
        for filepath, url in thumbnail_download_queue:
            r = requests.get(url, stream=True)
            if not r.ok:
                print(f"Failed to download thumbnail at {url} to {os.path.basename(filepath)} ({r.status_code}): {r.content}", file=sys.stderr)
                continue
            with open(filepath, "wb") as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)

    if do_data:
        local_song_info.update(new_entries)
        save_data_file(local_song_info, args.data_file, indent="    ")

    print("Finished")
    