import json
import multiprocessing
import os

import rich
import rich_click as click
import spotipy
from click_params import URL
from downloader import TrackInfo, download_tracks, TrackStatus
from rich.progress import Progress
from spotipy import CacheHandler
from spotipy.oauth2 import SpotifyOAuth
from storage import Store


@click.group()
def main():
    """
    This is an app which can be used to download music specified by spotify playlists.
    Be aware that this program does not download the music from spotify.
    It searches YouTube for Music Videos and downloads those.

    Try a command with '--help' to receive more info about a specific command.

    Quick example:

    \b
    main.py login --help
    main.py login 'client_id' 'client_secret'
    main.py download \\
            https://open.spotify.com/album/5ZDcFocL621yChPnZ1B0Ct \\
            https://open.spotify.com/playlist/5utZBhZZrQEEoOoiKhcDGG \\
            https://open.spotify.com/track/0tk3mMypVcCa05BkPpUF1F
    """
    pass


@main.command()
@click.argument(
    'client_id',
    envvar="S_CLIENT_ID",
    required=False
)
@click.argument(
    'client_secret',
    envvar="S_CLIENT_SECRET",
    required=False
)
@click.option(
    "-r", "--redirect-url",
    default="http://localhost:8888/callback",
    type=URL,
    help="The URL used as redirect url."
         "You have to configure your spotify app to accept this url as valid redirect url.",
    show_default=True
)
@click.option(
    "--nb", "--no-browser",
    is_flag=True,
    show_default=True,
    default=False,
    help="Dont open a browser to login. This is useful if you have no graphical user-interface available to you."
)
def login(client_id, client_secret, redirect_url, nb):
    """
    Set the app id and secret and login with an account to access private play lists.

    This is required when you try to access private playlists.
    You have to create a spotify app @ 'https://developer.spotify.com/dashboard/'.
    This will provide you with a 'client_id' and 'client_secret'.
    Be aware, that you have to add 'http://localhost:8888/callback' as a valid redirect url.
    You can specify a different URL using an argument.

    \b
    CLIENT_ID the client id of the spotify app you created.
    CLIENT_SECRET the client secret of the spotify app you created.

    Be aware, that you can also pass all arguments as environment variable.

    \b
    export S_CLIENT_ID=client_id
    export S_CLIENT_SECRET=client_secret

    or on Windows:

    \b
    set  S_CLIENT_ID=client_id
    set  S_CLIENT_SECRET=client_secret
    """

    data = Store()

    if not client_id or not client_secret:
        click.echo(" No id or secret provided. Check for a stored id or secret.")
        client = data.get_app_client_data()

        if not client:
            raise click.UsageError("CLIENT_ID or CLIENT_SECRET not provided and no id or secret stored.")

        client_id = client.id
        client_secret = client.secret

    click.echo("  Login ...")

    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        scope=data.SPOTIFY_REQUIRED_SCOPE,
        cache_handler=StoreCacheHandler(data),
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_url,
        open_browser=not nb
    ))

    click.echo("  ... as " + click.style(sp.current_user()["display_name"], fg="blue"))
    click.echo(F" Store client id and secret for future use")
    data.add_app_client_data(client_id, client_secret)


@main.command()
def login_info():
    """
    Print the id and secret of the currently active app.

    See teh 'login' command to set a client id or secret.
    This will exit with status code '1' when no id or secret are currently stored.
    """

    client = Store().get_app_client_data()

    if not client:
        click.echo("No client data provided. Try the 'login' command.")
        exit(1)

    click.echo(f"ID:     {click.style(client.id, fg='blue')}")
    click.echo(f"Secret: {click.style(client.secret, fg='blue')}")


@main.command()
def login_logout():
    """
    Delete your current session.

    You have to log in again, before you are able to access private playlists.
    """

    Store().delete_cached_login_token()
    click.echo(f"Logged out")


@main.command()
@click.argument(
    "urls",
    nargs=-1,
    type=URL,
)
@click.option(
    "-o", "--out",
    default=f"{os.getcwd()}/download",
    type=click.Path(file_okay=False, resolve_path=True),
    help="The directory, where the downloaded tracks will be saved.",
    show_default=True
)
@click.option(
    "-n", "--name",
    default="{artists[0]}/{album}/{name}.mp3",
    type=str,
    help="How the files will be named",
    show_default=True
)
@click.option(
    "-c", "--cores",
    default=multiprocessing.cpu_count(),
    type=int,
    help="The number of parallel downloads",
    show_default=True
)
def download(urls, out, name, cores):
    """
    Download tracks.

    Be aware, that the currently logged-in user needs access to the resources specified
    by the provided urls (i.e. he needs access to private playlists).

    An url can be an album url, a playlist url or a track url.

    """

    data = Store()

    client = data.get_app_client_data()

    if not client:
        raise click.UsageError("You have to log in before you can download songs.")

    sp = spotipy.Spotify(auth_manager=SpotifyOAuthNoLogin(
        scope=data.SPOTIFY_REQUIRED_SCOPE,
        cache_handler=StoreCacheHandler(data),
        client_id=client.id,
        client_secret=client.secret,
        redirect_uri="-/-"
    ))

    songs_to_download = []

    for url in urls:
        def create_song(album, track):
            track_info = TrackInfo(
                track["id"],
                track["name"],
                album["name"],
                [x["url"] for x in album["images"]],
                [x["name"] for x in track["artists"]],
                track["disc_number"],
                track["track_number"],
                album["release_date"]
            )
            return track_info

        tracks = []
        url_name = "Unknown"

        if "playlist" in url:
            click.echo(click.style(f"Playlist: {url}", bold=True))
            for item in util_read_pagination(sp, sp.playlist_items(
                    playlist_id=url,
                    fields=
                    'items.track.id,'
                    'items.track.album.images.url,'
                    'items.track.album.name,'
                    'items.track.album.release_date,'
                    'items.track.artists.name,'
                    'items.track.disc_number,'
                    'items.track.name,'
                    'items.track.track_number,'
                    'next'
            )):
                track = item["track"]
                album = track["album"]
                tracks.append(create_song(album, track))
            url_name = sp.playlist(playlist_id=url, fields="name")["name"]
        elif "album" in url:
            click.echo(click.style(f"Album: {url}", bold=True))
            album = sp.album(url)
            for track in util_read_pagination(sp, album["tracks"]):
                tracks.append(create_song(album, track))
            url_name = album["name"]
        elif "track" in url:
            click.echo(click.style(f"Track: {url}", bold=True))
            track = sp.track(url)
            tracks.append(create_song(track["album"], track))
            url_name = track["name"]
        else:
            raise click.UsageError(f"Unrecognized URL: {url}")

        rich.print(
            f"  ╚> [purple]{len(tracks)}[/purple] Track{'s' if len(tracks) != 1 else ''} in [cyan]{url_name}[/cyan]")

        songs_to_download.extend(tracks)

    click.echo("")

    with Progress() as gui:
        overall = gui.add_task(
            description=f"Tracks [purple]0[/purple] / [purple]{len(songs_to_download)}[/purple]",
            total=len(songs_to_download)
        )
        progress = {}

        def handle_progress(current_track, status, args):
            display_name = current_track.name
            if len(display_name) > 25:
                display_name = display_name[:25 - 2] + ".."
            else:
                display_name = f"{display_name:25}"

            if status is TrackStatus.START:
                progress[current_track.id] = gui.add_task(f"  {display_name} [light]...", total=None)
            elif status is TrackStatus.SEARCHING:
                gui.update(
                    progress[current_track.id],
                    description=f"  {display_name} [light]   \[search]"
                )
            elif status is TrackStatus.DOWNLOADING:
                gui.update(
                    progress[current_track.id],
                    description=f"  {display_name} [light] \[download]",
                    completed=args['progress'],
                    total=1
                )
            elif status is TrackStatus.CONVERTING:
                gui.update(
                    progress[current_track.id],
                    description=f"  {display_name} [light]  \[convert]",
                    total=None
                )
            elif status is TrackStatus.DONE:
                gui.update(progress[current_track.id], completed=True, visible=False, refresh=True)
                progress.pop(current_track.id)
                gui.advance(overall, 1)
                gui.update(
                    overall,
                    description=f"Tracks [purple]{gui.tasks[overall].completed}[/purple] / [purple]{len(songs_to_download)}[/purple] "
                )

        gui.refresh()
        download_tracks(songs_to_download, out, name, handle_progress, cores=cores)

    click.echo("")
    rich.print(f"Downloaded [purple]{len(songs_to_download)}[/purple] tracks [green]successfully[/green]")


def util_read_pagination(sp, results):
    items = results["items"]
    while results['next']:
        results = sp.next(results)
        items.extend(results['items'])
    return items


def util_elipse_string(string, length):
    if len(string) <= length:
        return f"{string:length}"
    else:
        return string[:length - 2] + ".."


class StoreCacheHandler(CacheHandler):
    """
    CacheHandler which uses a Store object to store and retrieve cached tokens.
    """

    def get_cached_token(self):
        token = self.__data.get_cached_login_token()
        return json.loads(token) if token else None

    def save_token_to_cache(self, token_info):
        self.__data.store_cached_login_token(json.dumps(token_info))

    def __init__(self, data: Store):
        self.__data = data


class SpotifyOAuthNoLogin(SpotifyOAuth):
    """
    A SpotifyOAuth implementation, which does not allow a new login (only session refreshes)
    """

    def get_auth_response(self, open_browser=None):
        raise click.UsageError("Not logged in anymore. Use 'login' to log in before accessing further commands.")


if __name__ == '__main__':
    main()
