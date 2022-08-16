from time import sleep

import click
import requests
from requests.utils import super_len

from plugins import Plugin, register, PluginSpecificOption


class ProgressFile:
    def __init__(self, fileobj, track_status_cb):
        self.track_status_cb = track_status_cb
        self.fileobj = fileobj
        self._length = super_len(self.fileobj)
        self._read = 0

    def __len__(self):
        return self._length

    def read(self, size=-1):
        data = self.fileobj.read(size)
        self._read += len(data)

        self.track_status_cb({
            'name': 'Upload',
            'total': self._length,
            'progress': self._read
        })

        return data

    def close(self):
        self.fileobj.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


@register
class FilebrowserUploadPlugin(Plugin):
    """Upload downloaded tracks to a hosted https://filebrowser.org/ instance."""

    def __init__(self, **kwargs):
        self.api = kwargs[f"{self.__class__.__name__}_url"].strip().rstrip('/') + "/api"
        self.insecure = kwargs[f"{self.__class__.__name__}_insecure"]
        self.username = kwargs[f"{self.__class__.__name__}_username"]
        self.password = kwargs[f"{self.__class__.__name__}_password"]

    def get_token(self):
        try:
            response = requests.post(self.api + "/login", json={
                "password": self.password, "recaptcha": "", "username": self.username,
            }, verify=not self.insecure)
            response.raise_for_status()
            return response.text
        except Exception as e:
            raise click.UsageError(str(e.args[0]))

    @staticmethod
    def get_name():
        return "filebrowser"

    @classmethod
    def get_plugin_specific_options(cls):
        option = [
                     PluginSpecificOption(
                         f"{cls.__name__}_username",
                         f"--plugin-{cls.get_name()}-username",
                         help="The username, which will be used, to log in into the filebrowser api.",
                         required=True
                     ),
                     PluginSpecificOption(
                         f"{cls.__name__}_password",
                         f"--plugin-{cls.get_name()}-password",
                         help="The password, which will be used, to log in into the filebrowser api.",
                         required=True
                     ),
                     PluginSpecificOption(
                         f"{cls.__name__}_url",
                         f"--plugin-{cls.get_name()}-url",
                         help="The url of the filebrowser instance.",
                         required=True
                     ),
                     PluginSpecificOption(
                         f"{cls.__name__}_insecure",
                         f"--plugin-{cls.get_name()}-insecure",
                         help="Allow insecure server connections when using SSL.",
                         default=False,
                         required=False
                     )
                 ] + super().get_plugin_specific_options()
        return option

    def on_track_done(self, track_path, track_name, track_status_cb):
        fileobj = ProgressFile(open(track_path, 'rb'), track_status_cb)
        token = self.get_token()
        headers = {
            'X-Auth': token,  # version >= 2.0.3 seems use this header
            'Authorization': 'Bearer {}'.format(token),  # version <= 2.0.0 seems use this header
        }

        for i in range(3, -1, -1):
            try:
                with fileobj:
                    response = requests.post(
                        self.api + "/resources/" + track_name,
                        data=fileobj,
                        params={"override": True},
                        headers=headers,
                        verify=not self.insecure,
                    )
                    response.raise_for_status()
                    break
            except:
                if 0 == i:
                    raise
                else:
                    self.track_status_cb({
                        'name': 'retry-upload',
                        'total': 3,
                        'progress': 4 - i
                    })
                    sleep(5)
