import multiprocessing
import random
import time
from collections import namedtuple
from enum import Enum
from itertools import repeat
from typing import Callable, List
from multiprocessing import Queue, Pool

TrackInfo = namedtuple("TrackInfo", "id name album images artists disc_number track_number release_date")


class TrackStatus(Enum):
    START = 0
    SEARCHING = 1
    DOWNLOADING = 2
    CONVERTING = 4
    DONE = 5


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
    time.sleep(random.randrange(0, 10))
    for i in range(0, 80):
        track_status_cb(track, TrackStatus.DOWNLOADING, {'progress': i / 100.0})
        time.sleep(0.1)
    for i in range(80, 100):
        track_status_cb(track, TrackStatus.CONVERTING, {'progress': i / 100.0})
        time.sleep(0.05)
    track_status_cb(track, TrackStatus.DONE, {})
