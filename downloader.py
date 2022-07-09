import os
import urllib.request
import eyed3
from eyed3.id3.frames import ImageFrame
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

    audiofile = eyed3.load(u'{}.mp3'.format(directory + "/" + song_hash))
    if audiofile.tag is None:
        audiofile.initTag()
    audiofile.tag.artist = ",".join(song["artists"])
    audiofile.tag.album = song["album"]
    audiofile.tag.album_artist = ",".join(song["artists"])
    audiofile.tag.title = song["name"]
    audiofile.tag.images.set(ImageFrame.FRONT_COVER, open(u'{}.png'.format(directory + "/" + song_hash), 'rb').read(), 'image/png')
    audiofile.tag.save()
    filename_sanitized = song["name"].replace('/', ' ')
    os.rename(u'{}.mp3'.format(directory + "/" + song_hash), u'{}.mp3'.format(directory + "/" + filename_sanitized))

    if os.path.isfile(directory + "/" + song_hash + ".png"):
        os.remove(directory + "/" + song_hash + '.png')
