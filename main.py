import json
import multiprocessing
import os
from collections import defaultdict
from enum import Enum

import rich_click as click
import spotipy
from PIL import Image
from click_params import URL
from rich.console import Console
from rich.table import Table

import downloader
from downloader import TrackStatus, MessageSeverity
from rich.progress import Progress
from spotipy import CacheHandler
from spotipy.oauth2 import SpotifyOAuth
from storage import Store, Comparator
from track import TrackInfo

_STORE = Store()

WHERE_OPTION = click.option(
    "-w", "--where",
    multiple=True,
    nargs=3,
    help="Filter for specific fields. "
         "Specify the option for teh same field multiple times, to build a disjunction. "
         "Specify different fields to build a conjugation. "
         "This can be passed like: -w artist LIKE 'The %' -w track_number '<' 4 -w [...] "
         f"i.e. after the flag you first pass the field name "
         f"then you pass the comparator and then the value to compare against.",
    type=click.Tuple([
        click.Choice(_STORE.get_track_cache_fields(), case_sensitive=False),
        click.Choice([x.value for x in Comparator], case_sensitive=False),
        str
    ]),
    show_default=True
)

URL_FILE_OPTION = click.option(
    "-u", "--url-file",
    type=click.Path(dir_okay=False, exists=True, resolve_path=True),
    help="Files containing urls per line. They will be added to the [URLS] list before processing.",
    multiple=True,
)

AGGREGATE_OPTION = click.option(
    "--aggregate/--no-aggregate",
    default=False,
    is_flag=True,
    help="Dont download the individually provided tracks (on a playlist), "
         "but download the complete albums containing the tracks.",
    show_default=True
)

ARTIST_ALBUM_OPTION = click.option(
    "-a", "--artist-album",
    default=["single", "album"],
    multiple=True,
    help="When specifying an artist to download from, this specifies which album types will be downloaded. "
         "Use this option multiple times, to download multiple album types.",
    type=click.Choice(['single', 'album', 'appears_on'], case_sensitive=False),
    show_default=True
)


@click.group()
def main():
    """
    This is an app which can be used to download music specified by spotify playlists.
    Be aware that this program does not download the music from spotify.
    It searches YouTube for Music Videos and downloads those.

    It uses a 'cache' which stores which tracks where already downloaded.
    You may have to clear the tracks from the cache before you can download those tracks again.

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
    "--nb", "--browser/--no-browser",
    is_flag=True,
    show_default=True,
    default=False,
    help="Open a browser to login."
         " Opening no borowser is useful if you have no graphical user-interface available to you."
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

    if not client_id or not client_secret:
        click.echo(" No id or secret provided. Check for a stored id or secret.")
        client = _STORE.get_app_client_data()

        if not client:
            raise click.UsageError("CLIENT_ID or CLIENT_SECRET not provided and no id or secret stored.")

        client_id = client.id
        client_secret = client.secret

    click.echo("  Login ...")

    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        scope=_STORE.SPOTIFY_REQUIRED_SCOPE,
        cache_handler=StoreCacheHandler(_STORE),
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_url,
        open_browser=not nb
    ))

    click.echo("  ... as " + click.style(sp.current_user()["display_name"], fg="blue"))
    click.echo(F" Store client id and secret for future use")
    _STORE.add_app_client_data(client_id, client_secret)


@main.command()
def login_info():
    """
    Print the id and secret of the currently active app.

    See the 'login' command to set a client id or secret.
    This will exit with status code '1' when no id or secret are currently stored.
    """

    client = _STORE.get_app_client_data()

    if not client:
        click.echo("No client data provided. Try the 'login' command.")
        exit(1)

    table = Table("[bold]App Info[/bold]", box=None)
    table.add_row("[white]ID[/white]", f"[bold]{client.id}[/bold]")
    table.add_row("[white]SECRET[/white]", f"[bold]{client.secret}[/bold]")

    Console().print(table)


@main.command()
def login_logout():
    """
    Delete your current session.

    You have to log in again, before you are able to access private playlists.
    """

    Store().delete_cached_login_token()
    click.echo(f"Logged out")


@main.command()
@click.option(
    "-o", "--order-by",
    default=["album_artist", "release_date", "album", "disc_number", "track_number", "track_id"],
    multiple=True,
    help="Specify the order of shown cache entries. "
         "Specify the option multiple times, to order lexicographically by multiple elements.",
    type=click.Choice(_STORE.get_track_cache_fields(), case_sensitive=False),
    show_default=True
)
@click.option(
    "-c", "--column",
    default=_STORE.get_track_cache_fields(),
    multiple=True,
    help="Specify which entries to show. "
         "Specify the option multiple times, to order lexicographically by multiple elements.",
    type=click.Choice(_STORE.get_track_cache_fields(), case_sensitive=False),
    show_default=True
)
@WHERE_OPTION
def cache(order_by, column, where):
    """
    Display which tracks are stored in the internal track cache.

    The cache stores which tracks are already downloaded.
    When downloading tracks, tracks, which are in the cache will not be downloaded again.
    """
    data = _STORE.read_track_cache(order_by, column, where)

    table = Table(title="[bold]Track cache "
                        f"([purple]{len(data)}[/purple] / [purple]{_STORE.read_track_cache_size()}[/purple] "
                        "displayed)[/bold]")

    column_header = {
        'track_id': lambda: table.add_column("track_id", style="white", no_wrap=True),
        'artist': lambda: table.add_column("artist", style="bold", no_wrap=True),
        'album': lambda: table.add_column("album", no_wrap=True),
        'disc_number': lambda: table.add_column("disc_number", justify="center", no_wrap=True),
        'name': lambda: table.add_column("name", justify="left", style="bold", no_wrap=True),
        'track_number': lambda: table.add_column("track_number", justify="center", no_wrap=True),
        'release_data': lambda: table.add_column("release_data", no_wrap=True),
    }

    for c in column:
        column_header.get(c, lambda: table.add_column(c, no_wrap=True))()

    for result in data:
        table.add_row(*[str(x) for x in result])

    Console().print(table)


@main.command()
@WHERE_OPTION
def cache_clear(where):
    """
    Clear tracks from the internal cache.
    """
    old_count = _STORE.read_track_cache_size()
    _STORE.clear_track_cache(where)
    count = _STORE.read_track_cache_size()
    cons = Console()
    cons.print(f"Removed [purple]{old_count - count}[/purple] cached tracks.")
    cons.print(f"[purple]{count}[/purple] tracks still cached.")


@main.command()
@click.argument(
    "urls",
    nargs=-1,
    type=URL,
)
@URL_FILE_OPTION
@ARTIST_ALBUM_OPTION
@AGGREGATE_OPTION
def cache_load(urls: list, url_file: list, artist_album, aggregate):
    """
    Load some songs into the internal cache without downloading them.
    """

    cons = Console()

    sp = _load_spotify_api()

    urls = _add_urls_from_file(cons, urls, url_file)
    songs_to_download = _extract_tracks(cons, sp, urls, artist_album, aggregate)

    inserted = 0
    already_inserted = 0

    for track in songs_to_download:
        if _STORE.insert_track_cache_if_new(track):
            inserted += 1
        else:
            already_inserted += 1

    table = Table("[bold]Insertion Results[/bold]", box=None)
    table.add_row("[green]INSERTED[/green]", str(inserted))
    table.add_row("[purple]CACHED[/purple]", str(already_inserted))

    cons.print("")
    cons.print(table)


@main.command()
@click.argument(
    "urls",
    nargs=-1,
    type=URL,
)
@URL_FILE_OPTION
@click.option(
    "-o", "--out",
    default=f"{os.getcwd()}/download",
    type=click.Path(file_okay=False, resolve_path=True),
    help="The directory, where the downloaded tracks will be saved.",
    show_default=True
)
@click.option(
    "-n", "--name",
    default="{album_artists[0]}/{album}/{name}.mp3",
    type=str,
    help="How the files will be named.\n"
         "The following placeholders will be interpolated with track information: " +
         ', '.join(map(lambda n: '{' + n + '}', TrackInfo._fields)) +
         ". You can also access the first element of some fields by using i.e. {artists[0]}",
    show_default=True
)
@click.option(
    "-c", "--cores",
    default=multiprocessing.cpu_count(),
    type=click.IntRange(min=1),
    help="The number of parallel downloads",
    show_default=True
)
@click.option(
    "-f", "--overwrite/--no-overwrite",
    default=False,
    is_flag=True,
    help="Overwrite tracks, that already exist on the hard disk. "
         "Be aware, that this will not ignore the cache.",
    show_default=True
)
@ARTIST_ALBUM_OPTION
@AGGREGATE_OPTION
@click.option(
    "-d", "--dry-run/--no-dry-run",
    default=False,
    is_flag=True,
    help="Dont try to download any track.",
    show_default=True
)
@click.option(
    "--embed-cover/--no-embed-cover",
    default=True,
    is_flag=True,
    help="Whether the album cover of a song should be embedded or not.",
    show_default=True
)
@click.option(
    "--cover-format",
    help="The image type used to store the embedded album cover. "
         "before it gets embedded. Be aware, that not all players may support all image types types.",
    type=click.Choice(list({ex[1:] for ex, f in Image.registered_extensions().items() if f in Image.SAVE}),
                      case_sensitive=False),
    default="png",
    show_default=True
)
def download(urls: list, url_file: list, out, name, cores, overwrite, artist_album, aggregate, dry_run, embed_cover,
             cover_format):
    """
    Download tracks.

    Be aware, that the currently logged-in user needs access to the resources specified
    by the provided urls (i.e. he needs access to private playlists).

    An url can be an album url, a playlist url, a track url or an artist url.

    """
    cons = Console()

    sp = _load_spotify_api()

    urls = _add_urls_from_file(cons, urls, url_file)
    songs_to_download = _extract_tracks(cons, sp, urls, artist_album, aggregate)

    if len(songs_to_download) == 0:
        raise click.UsageError("No tracks provided.")

    if dry_run:
        track_messages = {'_': [{
            'serv': MessageSeverity.WARNING,
            'source': '[purple]Dry Run[/purple]',
            'msg': 'This was a dry run. No tracks where actually downloaded.'
        }]}
        track_done_state = {downloader.DoneStatus.DRY: len(songs_to_download)}
    else:
        cons.print("")
        track_messages, track_done_state = download_tracks(cons, songs_to_download, out, name, cores, overwrite,
                                                           cover_info=downloader.CoverInfo(embed_cover, cover_format))

    if len(track_messages) != 0:
        cons.print("")
        table = Table()
        table.add_column("Source", justify="left", no_wrap=True)
        table.add_column("Severity", justify="center", no_wrap=True)
        table.add_column("Message", justify="left", overflow="fold")

        for key, value in track_messages.items():
            for entry in value:
                serv = entry["serv"].name
                if entry["serv"] == MessageSeverity.ERROR:
                    serv = f"[red]{serv}[/red]"
                elif entry["serv"] == MessageSeverity.WARNING:
                    serv = f"[yellow]{serv}[/yellow]"

                if "track" in entry:
                    table.add_row(entry["track"].name, serv, entry["msg"])
                elif "source" in entry:
                    table.add_row(entry["source"], serv, entry["msg"])
                else:
                    table.add_row("Unknown Source", f"[red]{MessageSeverity.ERROR.name}[/red]", json.dumps(entry))

        cons.print(table)

    cons.print("")
    table = Table("[bold]Download Result per Track[/bold]", box=None)
    for status, count in track_done_state.items():
        table.add_row({
                          downloader.DoneStatus.DRY.name: f"[purple]{downloader.DoneStatus.DRY.name}[/purple]",
                          downloader.DoneStatus.SUCCESS.name: f"[green]{downloader.DoneStatus.SUCCESS.name}[/green]",
                          downloader.DoneStatus.CACHED.name: f"[purple]{downloader.DoneStatus.CACHED.name}[/purple]",
                          downloader.DoneStatus.ERROR.name: f"[red]{downloader.DoneStatus.ERROR.name}[/red]"
                      }.get(status.name, status.name), str(count))
    cons.print(table)


def _load_spotify_api():
    client = _STORE.get_app_client_data()

    if not client:
        raise click.UsageError("You have to log in before you can download songs.")

    return spotipy.Spotify(auth_manager=SpotifyOAuthNoLogin(
        scope=_STORE.SPOTIFY_REQUIRED_SCOPE,
        cache_handler=StoreCacheHandler(_STORE),
        client_id=client.id,
        client_secret=client.secret,
        redirect_uri="-/-"
    ))


def _add_urls_from_file(cons, urls, url_files):
    if type(urls) == tuple:
        urls = list(urls)

    for uf in url_files:
        cons.print(f"[bold]Add addition urls from '{uf}'[/bold]")
        with open(uf, 'r') as f:
            lines = f.read().splitlines()
            urls.extend(lines)
            cons.print(f"Added {len(lines)} additional url{'' if len(lines) == 1 else 's'}.\n")
    return urls


def _extract_tracks(cons, sp, urls, album_group, aggregate):
    songs_to_download = set()

    # TODO aggregate came later and now this is a little bit messy.
    # This could be done in two steps:
    #  First: gather all tracks
    #  Second: if aggregate gather all albums and extract the tracks again
    # Currently we have to encode some logic kinda twice wich is not nice.

    def is_playlist(url):
        return "playlist" in url

    def is_track(url):
        return "track" in url

    if aggregate:
        cons.print("[bold]Convert playlists and tracks to albums[/bold]")
        new_urls = set()
        albums = set()
        for url in urls:
            if is_playlist(url):
                playlist_albums = set()
                cons.print(f"Convert [bold]Playlist[/bold] {url}")
                for track in util_read_pagination(sp, sp.playlist_tracks(playlist_id=url)):
                    album = track["track"]["album"]
                    href = album['external_urls']['spotify']
                    if href not in playlist_albums:
                        playlist_albums.add(href)
                        albums.add(href)
                        cons.print(f"  ╚> [bold]Album[/bold] {album['external_urls']['spotify']}")
            elif is_track(url):
                cons.print(f"Convert [bold]Track[/bold] {url}")
                album = sp.track(track_id=url)["album"]
                cons.print(f"  ╚> [bold]Album[/bold] {album['external_urls']['spotify']}")
                albums.add(album['external_urls']['spotify'])
            else:
                new_urls.add(url)
        urls = new_urls
        urls.update(albums)
        cons.print("")

    for url in urls:
        def create_song(album, track):
            track_info = TrackInfo(
                track["id"],
                track["name"],
                album["name"],
                list(sorted(x["name"] for x in album["artists"])),
                [x["url"] for x in album["images"]],
                list(sorted(x["name"] for x in track["artists"])),
                track["disc_number"],
                track["track_number"],
                album["release_date"]
            )
            return track_info

        def add_album(album_id, out_container: list):
            album = sp.album(album_id)
            out_container.extend([create_song(album, t) for t in util_read_pagination(sp, album["tracks"])])
            return album["name"]

        tracks = []

        if is_playlist(url):
            cons.print(f"[bold]Playlist: {url}[/bold]")
            for item in util_read_pagination(sp, sp.playlist_items(
                    playlist_id=url,
                    fields=
                    'items.track.id,'
                    'items.track.album.images.url,'
                    'items.track.album.name,'
                    'items.track.album.artists.name,'
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
            cons.print(f"[bold]Album: {url}[/bold]")
            url_name = add_album(url, tracks)
        elif is_track(url):
            cons.print(f"[bold]Track: {url}[/bold]")
            track = sp.track(url)
            tracks.append(create_song(track["album"], track))
            url_name = track["name"]
        elif "artist" in url:
            click.echo(click.style(f"Artist: {url}", bold=True))
            for album_info in util_read_pagination(sp, sp.artist_albums(url)):
                if album_info["album_group"] not in album_group:
                    continue

                album_tracks = []
                album_name = add_album(album_info["uri"], album_tracks)
                cons.print(f"  ║ ╚> [purple]{len(album_tracks)}[/purple] "
                           f"Track{'s' if len(tracks) != 1 else ''} in [cyan]{album_name}[/cyan]")
                tracks.extend(album_tracks)
            url_name = sp.artist(artist_id=url)["name"]
        elif "show" in url:
            click.echo(click.style(f"Show: {url}", bold=True))
            show = sp.show(show_id=url)
            for idx, ep in enumerate(util_read_pagination(sp, show["episodes"])):
                tracks.append(TrackInfo(
                    ep["id"],
                    ep["name"],
                    show["name"],
                    [x["url"] for x in ep["images"]],
                    [show["publisher"]],
                    1,
                    idx + 1,
                    ep["release_date"]
                ))
            url_name = show["name"]
        else:
            raise click.UsageError(f"Unrecognized URL: {url}")

        cons.print(
            f"  ╚> [purple]{len(tracks)}[/purple] Track{'s' if len(tracks) != 1 else ''} in [cyan]{url_name}[/cyan]")

        for track in tracks:
            songs_to_download.add(track)

    return songs_to_download


def download_tracks(cons, songs_to_download, out_dir, out_name, cores, overwrite, cover_info: downloader.CoverInfo):
    track_messages = {}
    track_done_state = defaultdict(lambda: 0)

    with Progress(console=cons) as gui:
        overall = gui.add_task(
            description=f"Tracks [purple]0[/purple] / [purple]{len(songs_to_download)}[/purple]",
            total=len(songs_to_download)
        )
        progress = {}

        def handle_progress(current_track: TrackInfo, status: TrackStatus, args: dict):
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
                    description=f"  {display_name} [light]   \\[search]"
                )
            elif status is TrackStatus.DOWNLOADING:
                gui.update(
                    progress[current_track.id],
                    description=f"  {display_name} [light] \\[download]",
                    completed=args['progress'],
                    total=1
                )
            elif status is TrackStatus.CONVERTING:
                gui.update(
                    progress[current_track.id],
                    description=f"  {display_name} [light]  \\[convert]",
                    total=None
                )
            elif status is TrackStatus.META_DATA:
                gui.update(
                    progress[current_track.id],
                    description=f"  {display_name} [light]\\[meta-data]",
                    total=None
                )
            elif status is TrackStatus.DONE:
                track_done_state[args["state"]] += 1
                gui.advance(overall, 1)
                gui.update(
                    overall,
                    description=f"Tracks [purple]{gui.tasks[overall].completed}[/purple] /"
                                f" [purple]{len(songs_to_download)}[/purple] "
                )
                gui.remove_task(progress[current_track.id])
                gui.refresh()
                progress.pop(current_track.id)
            elif status is TrackStatus.MESSAGE:
                args["track"] = current_track
                track_messages.setdefault(current_track.id, []).append(args)

        gui.refresh()
        downloader.download_tracks(
            list(songs_to_download),
            out_dir,
            out_name,
            handle_progress,
            cores=cores,
            overwrite=overwrite,
            cover_info=cover_info
        )

        return track_messages, track_done_state


def util_read_pagination(sp, results):
    items = results["items"]
    with Progress(transient=True) as gui:
        gui.add_task(description="Fetch data...", total=None)
        while results['next']:
            results = sp.next(results)
            items.extend(results['items'])
            gui.refresh()
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
