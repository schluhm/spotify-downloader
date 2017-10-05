# Spotify Downloader

This python script downloads all of the songs from all of your playlists on Spotify.

## Getting Started

### Prerequisites

You will need to set up a Google Cloud Platform application, create API keys and enable access to the YouTube API, and ensure localhost is set up as a valid callback URL. Do the same thing with the Spotify API.

Install `pytube` and `spotipy` using `pip`.

`pip install pytube`
`pip install spotipy`

### Configuring `config.json`

Check out `config-template.json` as a guide. It should be fairly self-explanatory - put in the API keys where it says "YOUR KEY HERE". You will absolutely need to set the APP_CONFIG settings, so do that (I put in the values as they are on my system, as a guide.)

### Installation

Run `python main.py` in a Terminal window to start installing the application. There isn't really an "installation" process--all that you're going to do is set up some config files so that the script doesn't prompt you for credentials every time it accesses the Spotify and YouTube APIs.

On the first run of the script, the script will open a web browser to prompt you to sign in to Google to authenticate your connection with the Youtube API. Follow the instructions as prompted.

Then, the script will prompt you to sign in to Spotify. After signing in, you will be directed to a page that cannot be opened because it is some localhost URL. You should copy-paste this URL into the Terminal from which you are running the application (i.e. paste it where the terminal demands `Enter the URL you were redireccted to:`).

### Running Application

Once you've done the above, just run `python main.py` to run the application. It will automatically download any songs that you have added to any of your Spotify playlists. 

Also, if a song is missing from your Downloads directory, it will re-download the song from the youtube URL provided in the `youtube_videoid` field for that song from the `songs.json` file. This is useful, since you can update this field manually for a song if the application doesn't find the right one for you on the first try. Note: if you are doing this, only put in the VIDEO ID within this field, not the full URL of the YouTube video. For example, if your youtube URL is http://youtube.com/watch?v=12345678, set the `youtube_videoid` to `12345678`.

## Contributing

Feel free to send a pull request!

## Roadmap

- Fixing bugs--for some reason, the script doesn't download every single song, and seems to repeatedly download all songs.
- Cleaning up the code and documenting it
- Easier, less hardcode-y way of changing download URLs
- Possibly a GUI?

## License

This project is licensed under the GNU AGPLv3 License - which in a nutshell means that if you make any changes to this project and publish them, you must publish your complete source code as well. See the [LICENSE.md](LICENSE.md) file for details.