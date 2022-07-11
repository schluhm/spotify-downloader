import multiprocessing
import os
import random
import time
from collections import namedtuple
from enum import Enum
from itertools import repeat
from typing import Callable, List
from multiprocessing import Queue, Pool

import eyed3 as eyed3
from eyed3.id3.frames import ImageFrame
from yt_dlp import YoutubeDL
import re
import unicodedata
import urllib.request

TrackInfo = namedtuple("TrackInfo", "id name album images artists disc_number track_number release_date")

YDL_OPTIONS = {'noplaylist': 'True', 'quiet': 'True', 'format': 'bestaudio/best', 'outtmpl': '%(title)s.%(ext)s',
               'cookiefile': 'cookies.txt', 'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }]}


class TrackStatus(Enum):
    START = 0
    SEARCHING = 1
    DOWNLOADING = 2
    CONVERTING = 4
    ERROR = 5
    DONE = 6


def _slugify(value, allow_unicode=False):
    """
    Taken from https://github.com/django/django/blob/master/django/utils/text.py
    Convert to ASCII if 'allow_unicode' is False. Convert spaces or repeated
    dashes to single dashes. Remove characters that aren't alphanumerics,
    underscores, or hyphens. Convert to lowercase. Also strip leading and
    trailing whitespace, dashes, and underscores.
    """
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize('NFKC', value)
    else:
        value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value.lower())
    return re.sub(r'[-\s]+', '-', value).strip('-_')


def download_tracks(
        tracks: List[TrackInfo],
        out: str,
        name: str,
        track_status_cb: Callable[[TrackInfo, TrackStatus, {}], None]
):
    with Pool(multiprocessing.cpu_count()) as pool:
        manager = multiprocessing.Manager()
        callback_queue = manager.Queue()

        pool.starmap_async(
            _track_download_worker,
            zip(tracks, repeat(out), repeat(name), repeat(callback_queue)),
            callback=lambda _: callback_queue.put(None, block=True)
        )

        while True:
            cb = callback_queue.get(block=True)
            if cb:
                track_status_cb(cb[0], cb[1], cb[2])
            else:
                break

        pool.close()
        pool.join()


def _track_download_worker(track: TrackInfo, out_dir, out_name, callback_queue: Queue):
    download_track(track, out_dir, out_name, lambda t, status, args: callback_queue.put((t, status, args), block=True))


def download_track(track: TrackInfo, out_dir, out_name, track_status_cb: Callable[[TrackInfo, TrackStatus, {}], None]):
    track_status_cb(track, TrackStatus.START, {})
    track_status_cb(track, TrackStatus.SEARCHING, {})
    video_id = lookup_song(track.name, track.artists)
    if video_id:
        track_status_cb(track, TrackStatus.DOWNLOADING, {'progress': 0})
        download_youtube_video(track.id, video_id, out_dir,
                               lambda x: track_status_cb(track, TrackStatus.DOWNLOADING, {'progress': x}),
                               lambda: track_status_cb(track, TrackStatus.CONVERTING, {}))
        process_video(track, out_dir)
    track_status_cb(track, TrackStatus.DONE, {})


# Looks up tracks on youtube, returns youtube ID if found, otherwise returns None
def lookup_song(track_name, artists):
    arg = track_name + " by " + ",".join(artists)
    with YoutubeDL(YDL_OPTIONS) as ydl:
        try:
            video = ydl.extract_info(f"ytsearch:{arg}", download=False)['entries'][0]
        except:
            return None
    return video["id"]


def download_youtube_video(song_hash: str, video_id: str, directory: str, download_cb, postprocess_cb) -> str:
    if not os.path.exists(directory):
        os.makedirs(directory)

    url = 'https://youtube.com/watch?v=' + video_id
    YDL_OPTIONS['outtmpl'] = directory + "/" + song_hash + '.%(ext)s'
    YDL_OPTIONS['progress_hooks'] = [
        lambda x: download_cb(float(x['downloaded_bytes']) / float(x['total_bytes']))]
    YDL_OPTIONS['postprocessor_hooks'] = [
        lambda _: postprocess_cb()]
    with YoutubeDL(YDL_OPTIONS) as ydl:
        ydl.download(url_list=[url])
    return video_id


def get_image(track, out_dir):
    link = track.images[0]
    urllib.request.urlretrieve(link, out_dir + "/" + track.id + ".png")


def process_video(track: TrackInfo, out_dir):
    get_image(track, out_dir)

    audiofile = eyed3.load(u'{}.mp3'.format(out_dir + "/" + track.id))
    if audiofile.tag is None:
        audiofile.initTag()
    audiofile.tag.artist = ",".join(track.artists)
    audiofile.tag.album = track.album
    audiofile.tag.album_artist = ",".join(track.artists)
    audiofile.tag.title = track.name
    audiofile.tag.images.set(ImageFrame.FRONT_COVER, open(u'{}/{}.png'.format(out_dir, track.id), 'rb').read(),
                             'image/png')
    audiofile.tag.save()
    filename_sanitized = _slugify(track.name)
    try:
        os.rename(u'{}/{}.mp3'.format(out_dir, track.id), u'{}/{}.mp3'.format(out_dir, filename_sanitized))
    except:
        pass  # TODO handle expectations
    if os.path.isfile(out_dir + "/" + track.id + ".png"):
        os.remove(out_dir + "/" + track.id + '.png')
