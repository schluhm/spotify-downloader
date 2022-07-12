import collections.abc
import copy
import multiprocessing
import os
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

YDL_OPTIONS = {
    'noplaylist': True,
    'quiet': True,
    'format': 'bestaudio/best',
    'postprocessors': [{
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


class MessageType(Enum):
    POOL_DONE = 0
    POOL_ERROR = 1
    WORKER_STATUS = 2


def download_tracks(
        tracks: List[TrackInfo],
        out: str,
        name: str,
        track_status_cb: Callable[[TrackInfo, TrackStatus, dict], None],
        cores=multiprocessing.cpu_count(),
        overwrite=False
):
    with Pool(cores) as pool:
        manager = multiprocessing.Manager()
        callback_queue = manager.Queue()

        work = pool.starmap_async(
            _track_download_worker,
            zip(tracks, repeat(out), repeat(name), repeat(overwrite), repeat(callback_queue)),
            callback=lambda _: callback_queue.put({
                'type': MessageType.POOL_DONE
            }, block=True),
            error_callback=lambda e: callback_queue.put({
                'type': MessageType.POOL_ERROR
            }, block=True)
        )

        while True:
            msg = callback_queue.get(block=True)
            match msg:
                case {'type': t} if t is MessageType.POOL_DONE:
                    break
                case {'type': t} if t is MessageType.POOL_ERROR:
                    pool.terminate()
                    break
                case {'type': t, 'payload': (track, status, args)} if t is MessageType.WORKER_STATUS:
                    track_status_cb(track, status, args)
                case _:
                    pool.terminate()
                    raise Exception(f"Internal error (unknown message): {msg}")

        work.get()

        pool.close()
        pool.join()


def _track_download_worker(track: TrackInfo, out_dir, out_name, overwrite, callback_queue: Queue):
    try:
        download_track(
            track,
            out_dir,
            out_name,
            overwrite,
            lambda t, status, args: callback_queue.put({
                'type': MessageType.WORKER_STATUS,
                'payload': (t, status, args)
            }, block=True))
    except Exception as e:
        raise Exception(f"Error for track: {track}") from e


def download_track(track: TrackInfo, out_dir, out_name, overwrite,
                   track_status_cb: Callable[[TrackInfo, TrackStatus, dict], None]):
    track_status_cb(track, TrackStatus.START, {})
    track_status_cb(track, TrackStatus.SEARCHING, {})
    video_id = lookup_song(track.name, track.artists)
    if video_id:
        track_status_cb(track, TrackStatus.DOWNLOADING, {'progress': 0})
        download_youtube_video(track.id, video_id, out_dir,
                               lambda progress: track_status_cb(track, TrackStatus.DOWNLOADING, {'progress': progress}),
                               lambda: track_status_cb(track, TrackStatus.CONVERTING, {}))
        process_video(track, out_dir, out_name, overwrite)
    track_status_cb(track, TrackStatus.DONE, {})


# Looks up tracks on youtube, returns youtube ID if found, otherwise returns None
def lookup_song(track_name, artists):
    arg = track_name + " by " + ",".join(artists)
    with YoutubeDL(YDL_OPTIONS) as ydl:
        return ydl.extract_info(f"ytsearch:{arg}", download=False)['entries'][0]["id"]


def download_youtube_video(song_hash: str, video_id: str, directory: str, download_cb, postprocess_cb) -> str:
    if not os.path.exists(directory):
        os.makedirs(directory)

    url = 'https://youtube.com/watch?v=' + video_id

    options = copy.deepcopy(YDL_OPTIONS)

    options['outtmpl'] = directory + "/" + song_hash + '.%(ext)s'
    options['progress_hooks'] = [
        lambda x: download_cb(float(x['downloaded_bytes']) / float(x['total_bytes']))]
    options['postprocessor_hooks'] = [
        lambda _: postprocess_cb()]
    options['logger'] = _YoutubeDLNullLogger()

    with YoutubeDL(options) as ydl:
        ydl.download(url_list=[url])
    return video_id


def process_video(track: TrackInfo, out_dir, out_name, overwrite):
    mp3_loc = u'{}.mp3'.format(out_dir + "/" + track.id)

    audiofile = eyed3.load(mp3_loc)
    if audiofile.tag is None:
        audiofile.initTag()
    audiofile.tag.artist = ",".join(track.artists)
    audiofile.tag.album = track.album
    audiofile.tag.album_artist = ",".join(track.artists)
    audiofile.tag.title = track.name

    response = urllib.request.urlopen(track.images[0])
    audiofile.tag.images.set(ImageFrame.FRONT_COVER, response.read(), 'image/jpeg')

    audiofile.tag.save()

    for i in range(len(track._fields)):
        if isinstance(track[i], collections.abc.Sequence):
            out_name = out_name.replace("{" + track._fields[i] + "[0]}", _slugify(track[i][0]))
        out_name = out_name.replace("{" + track._fields[i] + "}", _slugify(track[i]))

    try:
        path = u'{}/{}' \
            .format(out_dir, out_name) \
            .replace("\\", os.sep) \
            .replace("/", os.sep)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if overwrite:
            os.replace(mp3_loc, path)
        else:
            os.rename(mp3_loc, path)
    except:
        pass  # TODO handle expectations


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
    return re.sub(r'[^\w\s-]', '', value.lower())


class _YoutubeDLNullLogger(object):
    # TODO keep warnings and present them later
    def debug(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        pass
