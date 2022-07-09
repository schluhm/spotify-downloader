import os
import subprocess
import urllib.request

from youtube_dl import YoutubeDL

YDL_OPTIONS = {'noplaylist': 'True', 'format': 'bestaudio/best', 'outtmpl': '%(title)s.%(ext)s', 'cookiefile':'cookies.txt', 'postprocessors': [{
        'key': 'FFmpegVideoConvertor',
        'preferedformat': 'mp4',  # one of avi, flv, mkv, mp4, ogg, webm
    }]}


def download_youtube_video(song_hash, song, video_id, directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

    url = 'https://youtube.com/watch?v=' + video_id
    YDL_OPTIONS['outtmpl'] = directory + song_hash + '.%(ext)s'
    with YoutubeDL(YDL_OPTIONS) as ydl:
        ydl.download(url_list=[url])
    return video_id


def get_image(song_hash, song, directory):
    link = song["images"][0]
    urllib.request.urlretrieve(link, directory + "/" + song_hash + ".png")


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
