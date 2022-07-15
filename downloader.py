import collections.abc
import copy
import io
import multiprocessing
import os
from collections import namedtuple
from enum import Enum
from itertools import repeat
from typing import Callable, List
from multiprocessing import Queue, Pool

import eyed3 as eyed3
from PIL import Image
from eyed3.id3.frames import ImageFrame
from yt_dlp import YoutubeDL
import re
import unicodedata
from urllib.request import urlopen

from storage import Store
from track import TrackInfo

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
    CONVERTING = 3
    META_DATA = 4
    DONE = 5
    MESSAGE = 6


class DoneStatus(Enum):
    CACHED = 0,
    SUCCESS = 1,
    ERROR = 2,
    DRY = -1


class MessageType(Enum):
    POOL_DONE = 0
    POOL_ERROR = 1
    WORKER_STATUS = 2


class MessageSeverity(Enum):
    DEBUG = 0
    WARNING = 1
    ERROR = 2


CoverInfo = namedtuple("CoverInfo", "embedded format")


def download_tracks(
        tracks: List[TrackInfo],
        out: str,
        name: str,
        track_status_cb: Callable[[TrackInfo, TrackStatus, dict], None],
        cores=multiprocessing.cpu_count(),
        overwrite=False,
        cover_info=CoverInfo(True, None)
):
    with Pool(cores) as pool:
        manager = multiprocessing.Manager()
        callback_queue = manager.Queue()

        work = pool.starmap_async(
            _track_download_worker,
            zip(tracks, repeat(out), repeat(name), repeat(overwrite), repeat(cover_info), repeat(callback_queue)),
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


def _track_download_worker(track: TrackInfo, out_dir, out_name, overwrite, cover_info: CoverInfo,
                           callback_queue: Queue):
    try:
        download_track(
            track,
            out_dir,
            out_name,
            overwrite,
            cover_info,
            lambda t, status, args: callback_queue.put({
                'type': MessageType.WORKER_STATUS,
                'payload': (t, status, args)
            }, block=True))
    except Exception as e:
        raise Exception(f"Error for track: {track}") from e


def download_track(track: TrackInfo, out_dir, out_name, overwrite, cover_info: CoverInfo,
                   track_status_cb: Callable[[TrackInfo, TrackStatus, dict], None]):
    track_status_cb(track, TrackStatus.START, {})

    def msg_cb(msg, serv):
        track_status_cb(track, TrackStatus.MESSAGE, {'msg': msg, 'serv': serv})

    state = DoneStatus.ERROR

    try:
        if _acquire_song_lock(track):
            track_status_cb(track, TrackStatus.SEARCHING, {})
            video_id = _lookup_song(track, msg_cb)

            if video_id:
                track_status_cb(track, TrackStatus.DOWNLOADING, {'progress': 0})
                _download_youtube_video(track, video_id, out_dir,
                                        msg_cb,
                                        lambda progress: track_status_cb(track, TrackStatus.DOWNLOADING,
                                                                         {'progress': progress}),
                                        lambda: track_status_cb(track, TrackStatus.CONVERTING, {}))
                track_status_cb(track, TrackStatus.META_DATA, {})
                _process_video(track, out_dir, out_name, msg_cb, overwrite, cover_info)

                state = DoneStatus.SUCCESS
        else:
            state = DoneStatus.CACHED
    finally:
        track_status_cb(track, TrackStatus.DONE, {'state': state})


def _acquire_song_lock(track: TrackInfo):
    """
    A lock can be acquired, when the song is not already downloaded and/or no other takes wants to download the song.
    """
    return Store().insert_track_cache_if_new(track)


# Looks up tracks on youtube, returns youtube ID if found, otherwise returns None
def _lookup_song(track: TrackInfo, msg_cb):
    options = copy.deepcopy(YDL_OPTIONS)
    options['logger'] = _YoutubeDLNullLogger(msg_cb)

    arg = track.name + " by " + ",".join(track.artists)

    try:
        with YoutubeDL(options) as ydl:
            return ydl.extract_info(f"ytsearch:{arg}", download=False)['entries'][0]["id"]
    except Exception as e:
        msg_cb(f"An error occurred searching for the video: [red]{e}[/red]."
               " [yellow]Check your internet connection.[/yellow]", MessageSeverity.ERROR)
        return None


def _download_youtube_video(track: TrackInfo, video_id: str, directory: str, msg_cb, download_cb, postprocess_cb):
    if not os.path.exists(directory):
        os.makedirs(directory)

    def progress_hooks(data):
        try:
            download_cb(float(data['downloaded_bytes']) / float(data['total_bytes']))
        except KeyError:
            pass

    url = 'https://youtube.com/watch?v=' + video_id

    options = copy.deepcopy(YDL_OPTIONS)

    options['outtmpl'] = directory + "/" + track.id + '.%(ext)s'
    options['progress_hooks'] = [progress_hooks]
    options['postprocessor_hooks'] = [lambda _: postprocess_cb()]
    options['logger'] = _YoutubeDLNullLogger(msg_cb)

    with YoutubeDL(options) as ydl:
        ydl.download(url_list=[url])


def _process_video(track: TrackInfo, out_dir, out_name, msg_cb, overwrite, cover_info: CoverInfo):
    mp3_loc = u'{}/{}.mp3'.format(out_dir, track.id)

    audiofile = eyed3.load(mp3_loc)
    if audiofile.tag is None:
        audiofile.initTag()
    audiofile.tag.artist = ";".join(track.artists)
    audiofile.tag.album = track.album
    audiofile.tag.album_artist = ";".join(track.album_artists)
    audiofile.tag.title = track.name
    audiofile.tag.track_num = track.track_number
    audiofile.tag.disc_num = track.disc_number

    audiofile.tag.date = track.release_date
    audiofile.tag.recording_date = track.release_date
    audiofile.tag.release_date = track.release_date

    if cover_info.embedded:
        img = Image.open(urlopen(track.images[0]))
        imgByteArr = io.BytesIO()
        img.save(imgByteArr, format=cover_info.format if cover_info.format else img.format)
        audiofile.tag.images.set(ImageFrame.FRONT_COVER, imgByteArr.getvalue(), f'image/{cover_info.format}')

    audiofile.tag.save()

    for i in range(len(track._fields)):
        if isinstance(track[i], collections.abc.Sequence):
            out_name = out_name.replace("{" + track._fields[i] + "[0]}", _slugify(track[i][0]))
        out_name = out_name.replace("{" + track._fields[i] + "}", _slugify(track[i]))

    path = u'{}/{}' \
        .format(out_dir, out_name) \
        .replace("\\", os.sep) \
        .replace("/", os.sep)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if overwrite:
        os.replace(mp3_loc, path)
    elif os.path.exists(path):
        msg_cb(f"Stored as {mp3_loc} because {path} already existed. See the '[cyan]--overwrite[/cyan]' "
               "option to overwrite already existing files.", MessageSeverity.WARNING)
    else:
        os.rename(mp3_loc, path)


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
    return re.sub(r'[^\w\s-]', '', value.lower()).strip()


class _YoutubeDLNullLogger(object):

    def __init__(self, msg_cb):
        self.__msg_cb = msg_cb

    def debug(self, msg):
        # self.__msg_cb(msg, MessageSeverity.DEBUG)
        pass

    def warning(self, msg):
        self.__msg_cb(msg, MessageSeverity.WARNING)

    def error(self, msg):
        self.__msg_cb(msg, MessageSeverity.ERROR)
