from collections import namedtuple


class TrackInfo(namedtuple("TrackInfo", "id name album images artists disc_number track_number release_date")):
    def __eq__(self, other):
        return self.id.__eq(other.id)

    def __hash__(self):
        return self.id.__hash__()
