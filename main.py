import hashlib
import multiprocessing
from ssl import ALERT_DESCRIPTION_CLOSE_NOTIFY
import traceback
from itertools import repeat
import spotipy
from spotipy import util
import json
from downloader import *
from requests import get

SPOTIFY_SECRETS_FILE = "spotify_client_secret.json"
DOWNLOAD_PATH = "music"


# Takes Spotify Secrets and Playlist ID and returns Authentication and Playlist
def get_spotify_playlist(secrets: json):
    auth_token = util.prompt_for_user_token(secrets["username"],
                                            'playlist-read-private',
                                            client_id=secrets["client_id"],
                                            client_secret=secrets["client_secret"],
                                            redirect_uri='https://localhost/')

    sp = spotipy.Spotify(auth=auth_token)
    return sp, sp.user_playlist(secrets["username"], secrets["playlistID"])


##Load the downloaded songs list, and check to see if any new songs have been created
def read_songs_file(songfile):
    if os.path.exists(songfile):
        songs = open(songfile, "r")
        songs_list = json.loads(songs.read())
        songs.close()
        return songs_list
    else:
        songs = open(songfile, "w+")
        songs.write(json.dumps([]))
        songs.close()
        return []

# Dumps songs list to json (and makes it pretty)
def write_songs_file(songfile, songs):
    song_file = open(songfile, "w")
    song_file.write(json.dumps(json.loads(songs), indent=4, sort_keys=True))
    song_file.close()


def song_missing(song, directory):
    if os.path.isfile(directory + "/" + song["name"] + ".mp3"):
        return False
    else:
        return True

# Looks up tracks on youtube, returns youtube ID if found, otherwise returns None
def lookup_song(track_name, artists):
    arg = track_name + " by " + ",".join(artists)
    with YoutubeDL(YDL_OPTIONS) as ydl:
        try:
            video = ydl.extract_info(f"ytsearch:{arg}", download=False)['entries'][0]
        except:
            return None
    return video["id"]


def download_song(song, directory):
    print("Download: " + song["name"] + " @ " + directory)

    # Hash the value of song, in order to serve as a unique identifier
    song_hash = hashlib.md5(json.dumps(json.loads(song), indent=4, sort_keys=True).encode('utf-8')).hexdigest()
    selected_video = download_youtube_video(song_hash, song, song["youtube_videoid"], directory)
    song["youtube_videoid"] = selected_video
    process_video(song_hash, song, directory)

    song["downloaded"] = True
    print("Downloaded: " + song["name"])

# Adds songs with spotifies Metadata to list. Skips songs that aren't found on Youtube
def add_page_to_list(songlist, page):
    for track in page["items"]:
        track = track["track"]
        album = track["album"]
        album_name = album["name"]
        images = [x["url"] for x in album["images"]]
        artists = [x["name"] for x in track["artists"]]
        track_name = track["name"]
        id = lookup_song(track_name, artists)
        if id is None: 
            print("Couldn't find anything for " + track_name + " by " + ",".join(artists))
            continue
        track_data = {
            "name": track_name,
            "album": album_name,
            "images": images,
            "artists": artists,
            "youtube_videoid": id,
            "downloaded": False,
        }
        songlist.append(track_data)
        print("Collected metadata from Spotify for " + track_name + " by " + ",".join(artists))

# Adds all songs from playlist to songlist
def get_playlist_songs_list(playlist, sp, secrets):
    songs_list = []
    tracks = sp.user_playlist(secrets["username"], playlist["id"], fields="tracks,next")["tracks"]
    numtracks = tracks["total"]
    add_page_to_list(songs_list, tracks)
    while tracks["next"]:
        tracks = sp.next(tracks)
        add_page_to_list(songs_list, tracks)
    print("Processed " + str(len(songs_list)) + " songs")
    return songs_list


def download_songs(songfile, secrets):
    listed_songs = read_songs_file(songfile)
    distilled_list = [[x["name"], x["artists"]] for x in listed_songs]    
    try:
        sp, playlist = get_spotify_playlist(secrets)
        playlist_songs = get_playlist_songs_list(playlist, sp, secrets)

        new_songs = filter(lambda s: [s["name"], s["artists"]] not in distilled_list, playlist_songs)
        listed_songs += new_songs

        with multiprocessing.Pool(multiprocessing.cpu_count()) as p:
            for s in p.starmap(download_song, zip(new_songs, repeat(DOWNLOAD_PATH))):
                s["downloaded"] = True

            p.close()
            p.join()

        for song in listed_songs:
            if not song["downloaded"] or song_missing(song, DOWNLOAD_PATH):
                download_song(song, DOWNLOAD_PATH)
                song["downloaded"] = True

    except Exception as e:
        print(traceback.format_exc())
    finally:
        for song in listed_songs:
            song.pop("youtube_videoids", None)
        write_songs_file(songfile, listed_songs)


if __name__ == "__main__":
    config_file = open("config.json", "r")
    CONFIG = json.loads(config_file.read())
    config_file.close()

    SPOTIFY_SECRETS = CONFIG["SPOTIFY_SECRETS"]
    playlistID = input("Which playlist would you like to download? Enter the link: \n")
    SPOTIFY_SECRETS["playlistID"] = playlistID.split('/')[-1]

    YDL_OPTIONS['outtmpl'] = CONFIG["APP_CONFIG"]["download_path"] + '/%(title)s.%(ext)s'
    DOWNLOAD_PATH = CONFIG["APP_CONFIG"]["download_path"]
    download_songs(CONFIG["APP_CONFIG"]["songs_file"], SPOTIFY_SECRETS)
