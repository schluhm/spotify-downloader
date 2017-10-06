import json
import os
import hashlib
import traceback
import spotipy
from spotipy import util
from downloader import *

SPOTIFY_SECRETS_FILE = "spotify_client_secret.json"

def get_spotify_playlist(secrets):
    auth_token = util.prompt_for_user_token(secrets["username"],
                                            'playlist-read-private',
                                            client_id=secrets["client_id"],
                                            client_secret=secrets["client_secret"],
                                            redirect_uri='https://localhost')

    sp = spotipy.Spotify(auth=auth_token)
    return sp, sp.user_playlists(secrets["username"])

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
    #First try to search for the song by channel name
    channel_results = service.search().list(q=artists[0], part="snippet", maxResults=1, type="channel").execute()
    song_results = None
    query = track_name + " by " + ",".join(artists)
    
    try:
        if not channel_results:
            artist_channel_id = channel_results["items"][0]["id"]["channelId"]
            song_results = service.search().list(q=query, part="snippet", channelId=artist_channel_id, type="video").execute()
            if not song_results:
                song_results = service.search().list(q=query, part="snippet", type='video').execute()
        else:
            song_results = service.search().list(q=query, part="snippet", type='video').execute()
    except:
        song_results = service.search().list(q=query, part="snippet", type='video').execute()

    return [video["id"]["videoId"] for video in song_results["items"]]

def download_song(song, directory):
    #Hash the value of song, in order to serve as a unique identifier
    song_hash = hashlib.md5(json.dumps(song).encode('utf-8')).hexdigest()
    selected_video = download_youtube_video(song_hash, song, song["youtube_videoids"], directory)
    song["youtube_videoid"] = selected_video
    process_video(song_hash, song, directory)

def add_page_to_list(songlist, page):
    for track in page["items"]:
        track      = track["track"]
        album      = track["album"]
        album_name = album["name"]
        images     = [x["url"] for x in album["images"]]
        artists    = [x["name"] for x in track["artists"]]
        track_name = track["name"]
        track_data = {
            "name" : track_name,
            "album" : album_name,
            "images" : images,
            "artists" : artists,
            "youtube_videoid" : "",
            "youtube_videoids" : lookup_song(track_name, artists),
            "downloaded" : False,
        }
        songlist.append(track_data)
        print("Collected metadata from Spotify for " + track_name + " by " + ",".join(artists))

def get_playlist_songs_list(playlists, sp, secrets):
    songs_list = []
    for playlist in playlists["items"]:
        tracks = sp.user_playlist(secrets["username"], playlist["id"], fields="tracks,next")["tracks"]
        numtracks = tracks["total"]
        add_page_to_list(songs_list, tracks)
        while tracks["next"]:
            tracks = sp.next(tracks)
            add_page_to_list(songs_list, tracks)
    
    print("Processed " + str(len(songs_list)) + " songs")
    return songs_list

def download_missing_songs(songfile, secrets):
    listed_songs = read_songs_file(songfile)
    distilled_list = [[x["name"], x["artists"]] for x in listed_songs]
    try: 
        sp, playlists = get_spotify_playlist(secrets)
        playlist_songs = get_playlist_songs_list(playlists, sp, secrets)

        print("STARTING THE DOWNLOAD PROCESS")
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
        print traceback.format_exc()
    finally:
        for song in listed_songs:
            song.pop("youtube_videoids", None)
        write_songs_file(songfile, listed_songs)

if __name__ == "__main__":
    config_file = open("config.json", "r")
    CONFIG = json.loads(config_file.read())
    config_file.close()

    SPOTIFY_SECRETS = CONFIG["SPOTIFY_SECRETS"]

    download_missing_songs(CONFIG["APP_CONFIG"]["songs_file"], SPOTIFY_SECRETS)
    