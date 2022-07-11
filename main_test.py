from downloader import download_youtube_video
from main import DOWNLOAD_PATH, lookup_song

def lookup_song_age_restricted_test():
    assert lookup_song("Arche Gruber", ["Drangsal"]) == "-dZQBM_qBUI", "Should be -dZQBM_qBUI"
    
def lookup_song_test():
    assert lookup_song("Master of Puppets", ["Metallica"]) == "0obBdrfUMzU", "Should be 0obBdrfUMzU"

def lookup_song_gibberish_test():
    print(lookup_song("akjsdasdka", ["asldjasdasd"]))
    
def download_youtube_video_test():
    download_youtube_video("testhash123", "-dZQBM_qBUI", "music") == "-dZQBM_qBUI", "Should be -dZQBM_qBUI"

if __name__ == "__main__":
    # lookup_song_test()
    # lookup_song_age_restricted_test()
    # lookup_song_gibberish_test()
    download_youtube_video_test()
    print("Everything passed")