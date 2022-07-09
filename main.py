import hashlib
import traceback
import spotipy
from spotipy import util
import json
from downloader import *
from requests import get

SPOTIFY_SECRETS_FILE = "spotify_client_secret.json"



def get_spotify_playlist(secrets):
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


def write_songs_file(songfile, songs):
    song_file = open(songfile, "w")
    song_file.write(json.dumps(songs))
    song_file.close()


def song_missing(song, directory):
    if os.path.isfile(directory + "/" + song["name"] + ".mp3"):
        return False
    else:
        return True


def lookup_song(track_name, artists):
    arg = track_name + " by " + ",".join(artists)
    with YoutubeDL(YDL_OPTIONS) as ydl:
        try:
            print("Trying to get somethign")
            get(arg)
        except:
            video = ydl.extract_info(f"ytsearch:{arg}", download=False)['entries'][0]
        else:
            video = ydl.extract_info(arg, download=False)
    return video["id"]


def download_song(song, directory):
    # Hash the value of song, in order to serve as a unique identifier
    song_hash = hashlib.md5(json.dumps(song).encode('utf-8')).hexdigest()
    selected_video = download_youtube_video(song_hash, song, song["youtube_videoid"], directory)
    song["youtube_videoid"] = selected_video
    process_video(song_hash, song, directory)


def add_page_to_list(songlist, page):
    for track in page["items"]:
        track = track["track"]
        album = track["album"]
        album_name = album["name"]
        images = [x["url"] for x in album["images"]]
        artists = [x["name"] for x in track["artists"]]
        track_name = track["name"]
        track_data = {
            "name": track_name,
            "album": album_name,
            "images": images,
            "artists": artists,
            "youtube_videoid": lookup_song(track_name, artists),
            "downloaded": False,
        }
        songlist.append(track_data)
        print("Collected metadata from Spotify for " + track_name + " by " + ",".join(artists))


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


def download_missing_songs(songfile, secrets):
    print("here we go")
    listed_songs = read_songs_file(songfile)
    distilled_list = [[x["name"], x["artists"]] for x in listed_songs]
    try:
        print("really trying here")
        sp, playlist = get_spotify_playlist(secrets)
        print("Getting authenticated")
        playlist_songs = get_playlist_songs_list(playlist, sp, secrets)
        for song in playlist_songs:
            if [song["name"], song["artists"]] not in distilled_list:
                print("Downloading song: " + song["name"])
                download_song(song, DOWNLOAD_PATH)

                song["downloaded"] = True
                listed_songs.append(song)
                print("Song downloaded")

        for song in listed_songs:
            if not song["downloaded"] or song_missing(song, DOWNLOAD_PATH):
                print("Downloading song: " + song["name"])
                download_song(song, DOWNLOAD_PATH)
                song["downloaded"] = True
                print("Song downloaded")
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
    YDL_OPTIONS['outtmpl'] = CONFIG["APP_CONFIG"]["download_path"] + '/%(title)s.%(ext)s'
    download_missing_songs(CONFIG["APP_CONFIG"]["songs_file"], SPOTIFY_SECRETS)
