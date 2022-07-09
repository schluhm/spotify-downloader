import os
import subprocess
import urllib.request

from yt_dlp import YoutubeDL

YDL_OPTIONS = {'noplaylist': 'True', 'format': 'bestaudio/best', 'outtmpl': '%(title)s.%(ext)s', 'cookiefile':'cookies.txt', 'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }]}


def download_youtube_video(song_hash, song, video_id, directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

    url = 'https://youtube.com/watch?v=' + video_id
    YDL_OPTIONS['outtmpl'] = directory + "/" + song_hash + '.%(ext)s'
    with YoutubeDL(YDL_OPTIONS) as ydl:
        ydl.download(url_list=[url])
    return video_id


def get_image(song_hash, song, directory):
    link = song["images"][0]
    urllib.request.urlretrieve(link, directory + "/" + song_hash + ".png")


def process_video(song_hash, song, directory):
    get_image(song_hash, song, directory)

    final_audio = u'lame --tt \"{}\" --tl \"{}\" --ti \"{}.png\" --ta \"{}\" \"{}.mp3\" \"{}.mp3\"'.format(
        song["name"],
        song["album"],
        directory + "/" + song_hash,
        ",".join(song["artists"]),
        directory + "/" + song_hash,
        directory + "/" + song["name"])

    devnull = open(os.devnull, "w")

    subprocess.call(final_audio, shell=True, stdout=devnull, stderr=subprocess.STDOUT)
    os.remove(directory + "/" + song_hash +'.mp3')

    if os.path.isfile(directory + "/" + song_hash + ".png"):
        os.remove(directory + "/" + song_hash +'.png')
