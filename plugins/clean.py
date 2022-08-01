import os

from plugins import Plugin, register


@register
class CleanPlugin(Plugin):
    """Delete tracks, after they got downloaded and converted."""

    def __init__(self, **kwargs):
        pass

    @staticmethod
    def get_name():
        return "clean"

    def on_track_done(self, track_path, track_name, track_status_cb):
        os.remove(track_path)



