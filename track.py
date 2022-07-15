from collections import namedtuple


class TrackInfo(namedtuple("TrackInfo", "id name album album_artists images artists disc_number track_number release_date")):
    def __eq__(self, other):
        return self.id.__eq__(other.id)

    def __hash__(self):
        return self.id.__hash__()
