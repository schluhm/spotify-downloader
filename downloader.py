import os
import subprocess
import sys
import urllib
import time
import json
import httplib2

from pytube import YouTube
from pytube.exceptions import DoesNotExist, AgeRestricted
from apiclient.discovery import build
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from oauth2client.tools import argparser, run_flow

def create_google_secrets_file(google_secrets_path):
    GOOGLE_SECRETS = CONFIG["GOOGLE_SECRETS"]
    GOOGLE_SECRETS_FILE = open(google_secrets_path, "w+")
    GOOGLE_SECRETS_FILE.write(json.dumps(GOOGLE_SECRETS))
    GOOGLE_SECRETS_FILE.close()

config_file = open("config.json", "r")
CONFIG = json.loads(config_file.read())
config_file.close()

GOOGLE_CONFIG = CONFIG["GOOGLE_CONFIG"]
APP_CONFIG = CONFIG["APP_CONFIG"]
if not os.path.exists(APP_CONFIG["google_secrets_location"]):
    create_google_secrets_file(APP_CONFIG["google_secrets_location"])

DOWNLOAD_PATH = APP_CONFIG["download_path"]

def get_authenticated_service(args):
    flow = flow_from_clientsecrets(APP_CONFIG["google_secrets_location"],
                                   scope=GOOGLE_CONFIG["youtube_read_write_ssl_scope"],
                                   message=GOOGLE_CONFIG["missing_client_secrets_message"])

    storage = Storage("%s-oauth2.json" % sys.argv[0])
    credentials = storage.get()

    if credentials is None or credentials.invalid:
        credentials = run_flow(flow, storage, args)

    return build(GOOGLE_CONFIG["api_service_name"], GOOGLE_CONFIG["api_version"], http=credentials.authorize(httplib2.Http()))

args = argparser.parse_args()
service = get_authenticated_service(args)

def get_human_time(sec):
    if sec >= 3600:  # Converts to Hours
        return '{0:d} hour(s)'.format(int(sec / 3600))
    elif sec >= 60:  # Converts to Minutes
        return '{0:d} minute(s)'.format(int(sec / 60))
    else:            # No Conversion
        return '{0:d} second(s)'.format(int(sec))

def bytes_to_str(bts):
    bts = float(bts)
    if bts >= 1024 ** 4:    # Converts to Terabytes
        terabytes = bts / 1024 ** 4
        size = '%.2fTb' % terabytes
    elif bts >= 1024 ** 3:  # Converts to Gigabytes
        gigabytes = bts / 1024 ** 3
        size = '%.2fGb' % gigabytes
    elif bts >= 1024 ** 2:  # Converts to Megabytes
        megabytes = bts / 1024 ** 2
        size = '%.2fMb' % megabytes
    elif bts >= 1024:       # Converts to Kilobytes
        kilobytes = bts / 1024
        size = '%.2fKb' % kilobytes
    else:                   # No Conversion
        size = '%.2fb' % bts
    return size

class progressBar:
    def __init__(self, barlength=25):
        self.barlength = barlength
        self.position = 0
        self.longest = 0

    def print_progress(self, cur, total, start):
        currentper = cur / total
        elapsed = int(time.clock() - start) + 1
        curbar = int(currentper * self.barlength)
        bar = '\r[' + '='.join(['' for _ in range(curbar)])  # Draws Progress
        bar += '>'
        bar += ' '.join(['' for _ in range(int(self.barlength - curbar))]) + '] '  # Pads remaining space
        bar += bytes_to_str(cur / elapsed) + '/s '  # Calculates Rate
        bar += get_human_time((total - cur) * (elapsed / cur)) + ' left'  # Calculates Remaining time
        if len(bar) > self.longest:  # Keeps track of space to over write
            self.longest = len(bar)
            bar += ' '.join(['' for _ in range(self.longest - len(bar))])
        sys.stdout.write(bar)

    def print_end(self, *args):  # Clears Progress Bar
        sys.stdout.write('\r{0}\r'.format((' ' for _ in range(self.longest))))

def get_video(video_id):
    try:
        yt = YouTube("https://youtube.com/watch?v=" + video_id)
        video = yt.get('mp4', '720p')
        return True, video, yt.filename
    except DoesNotExist:  # Sorts videos by resolution and picks the highest quality video if a 720p video doesn't exist
        video = sorted(yt.filter("mp4"), key=lambda video: int(video.resolution[:-1]), reverse=True)[0]
        return True, video, yt.filename
    except AgeRestricted:
        return False, None, ""

def download_youtube_video(song_hash, song, video_ids, directory):
    if not os.path.exists(directory):
        os.makedirs(directory)
    
    found_video = False
    video = None
    filename = ""
    i = 0
    while not found_video:
        found_video, video, filename = get_video(video_ids[i])
        if found_video:
            break
        else:
            i += 1

    bar = progressBar()
    print directory
    video.download(directory, on_progress=bar.print_progress, on_finish=bar.print_end, force_overwrite = True)
    os.rename(directory + "/" + filename + ".mp4", directory + "/" + song_hash + ".mp4")
    return video_ids[i]

def get_image(song_hash, song, directory):
    link = song["images"][0]
    urllib.urlretrieve(link, directory + "/" + song_hash + ".png")

def process_video(song_hash, song, directory):
    get_image(song_hash, song, directory)

    aud = u'ffmpeg -i \"{}.mp4\" \"{}.wav\"'.format(directory + "/" + song_hash, directory + "/" + song_hash)
    final_audio = u'lame --tt \"{}\" --tl \"{}\" --ti \"{}.png\" --ta \"{}\" \"{}.wav\" \"{}.mp3\"'.format(
        song["name"],
        song["album"],
        directory + "/" + song_hash,
        ",".join(song["artists"]),
        directory + "/" + song_hash,
        directory + "/" + song["name"])

    devnull = open(os.devnull, "w")

    subprocess.call(aud, shell=True, stdout=devnull, stderr=subprocess.STDOUT)
    subprocess.call(final_audio, shell=True, stdout=devnull, stderr=subprocess.STDOUT)
    os.remove(directory + "/" + song_hash +'.mp4')
    os.remove(directory + "/" + song_hash +'.wav')

    if os.path.isfile(directory + "/" + song_hash + ".png"):
        os.remove(directory + "/" + song_hash +'.png')
