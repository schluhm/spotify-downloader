# Spotify Downloader

This python script downloads all of the songs, in MP3 format, from any given of your playlists on Spotify. It searches for each of the songs from your playlist on YouTube, searches for (what it thinks is) the best video file, and then converts the video file into an audio file.

## Getting Started

### Prerequisites

Set up a Spotify Application to get API keys and add localhost as a valid callback URL. [Instructions](https://developer.spotify.com/web-api/tutorial/).

Install `youtube_dl` and `spotipy` using `pip`.

`pip install youtube_dl`

`pip install spotipy`

Also install lame encoder or if you're on Windows, just drop the .exe in your spotify-downloader directory.

To load songs with age restricted videos install cookies.txt browser extension and save your Youtube Cookies to

### Configuring `config.json`

Check out `config-template.json` as a guide. It should be fairly self-explanatory - put in the API keys where it says "YOUR KEY HERE".

You will absolutely need to set the APP_CONFIG settings, so do that (I put in the values as they are on my system, as a guide.) Here is a brief description of these items:

- `songs_file` sets the location of where the file containing data for all of the downloaded songs is located.
- `download_path` sets the location of where the MP3s will be downloaded.

### Installation

Run `python main.py` in a Terminal window to start installing the application. There isn't really an "installation" process - all that you're going to do is set up some config files so that the script doesn't prompt you for credentials every time it accesses the Spotify API.

The script will prompt you to sign in to Spotify. After signing in, you will be directed to a page that cannot be opened because it is some localhost-based URL. You should copy-paste this URL from your browser into the Terminal from which you are running the application (i.e. paste it where the terminal demands `Enter the URL you were redireccted to:`). When you press Enter, the application will begin downloading your songs.

### Running Application

Once you've done the above, just run `python main.py` to run the application. It will automatically prompt you for a playlist and download any songs that you have added to the given Spotify playlist. 

Also, if a song is missing from your Downloads directory, it will re-download the song from the youtube URL provided in the `youtube_videoid` field for that song from the `songs.json` file. This is useful, since you can update this field manually for a song if the application doesn't find the right one for you on the first try. Note: if you are doing this, only put in the VIDEO ID within this field, not the full URL of the YouTube video. For example, if your youtube URL is http://youtube.com/watch?v=12345678, set the `youtube_videoid` to `12345678`. Also, remember to set `downloaded` to `false` for that song, and remember to delete it from the music folder, so that the application re-downloads it.

## Troubleshooting

If you're getting a 403 just go to command-line and `youtube-dl --rm-cache-dir` to clear cache.

## Roadmap

- Fixing bugs - for some reason, the script doesn't download every single song, and seems to repeatedly download some songs, which is really strange.
- Cleaning up the code and documenting it
- Easier, less hardcoded way of changing download URLs
- Possibly a GUI?

## License

This project is licensed under the GNU AGPLv3 License - which in a nutshell means that if you make any changes to this project and publish them, you must publish your complete source code as well. See the [LICENSE.md](LICENSE.md) file for details.