import click
import requests

from plugins import Plugin, register, PluginSpecificOption


@register
class FilebrowserUploadPlugin(Plugin):
    """Upload downloaded tracks to a hosted https://filebrowser.org/ instance."""

    def __init__(self, **kwargs):
        self.api = kwargs[f"{self.__class__.__name__}_url"].strip().rstrip('/') + "/api"
        self.insecure = kwargs[f"{self.__class__.__name__}_insecure"]
        self.token = self.get_token(
            kwargs[f"{self.__class__.__name__}_username"],
            kwargs[f"{self.__class__.__name__}_password"]
        )

    def get_token(self, username, password):
        try:
            response = requests.post(self.api + "/login", json={
                "password": password, "recaptcha": "", "username": username,
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

    def on_track_done(self, track_path, track_name):
        url = self.api + "/resources/" + track_name
        fileobj = open(track_path, 'rb')
        headers = {
            'X-Auth': self.token,  # version >= 2.0.3 seems use this header
            'Authorization': 'Bearer {}'.format(self.token),  # version <= 2.0.0 seems use this header
        }

        with fileobj:
            response = requests.post(  # TODO somehow display the upload progress
                url, data=fileobj,
                params={"override": False},
                headers=headers,
                verify=not self.insecure,
            )
            response.raise_for_status()
