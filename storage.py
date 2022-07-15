import sqlite3

from collections import namedtuple
from enum import Enum
from itertools import groupby

from track import TrackInfo

ClientInfo = namedtuple("ClientInfo", "id secret")


class Comparator(Enum):
    EQ = "="
    N_EQ = "!="
    L = "<"
    L_EQ = "<="
    B = ">"
    B_EQ = ">="
    LIKE = "LIKE"
    N_LIKE = "NOT LIKE"


class Store:
    """
    DAO for the sql database.
    The database is used to store some global program state,
    which shall persist over multiple executions.
    """

    def __init__(self, db_location="data.db"):
        self.SPOTIFY_REQUIRED_SCOPE = 'playlist-read-private'

        self.__connection = sqlite3.connect(db_location)

        thread_safety = self.__connection.execute("""
            select * from pragma_compile_options where compile_options like 'THREADSAFE=%'
        """).fetchone()[0]

        if thread_safety not in ["THREADSAFE=1", "THREADSAFE=2"]:
            raise Exception(f"Non supported 'THREADSAFE' value: {thread_safety}")

        self.__connection.execute('''
            CREATE TABLE IF NOT EXISTS app (
                client_id TEXT NOT NULL,
                client_secret TEXT NOT NULL,
                insertion_data TIMESTAMP NOT NULL,
                PRIMARY KEY (client_id, client_secret)
            )
            ''')
        self.__connection.execute('''
            CREATE TABLE IF NOT EXISTS login (
                login_id INTEGER NOT NULL PRIMARY KEY,
                token TEXT NOT NULL,
                insertion_data TIMESTAMP NOT NULL
            )
            ''')
        self.__connection.execute('''
            CREATE TABLE IF NOT EXISTS tracks (
                track_id TEXT NOT NULL PRIMARY KEY,
                artist TEXT NOT NULL,
                album TEXT NOT NULL,
                disc_number INTEGER NOT NULL,
                track_number INTEGER NOT NULL,
                name TEXT NOT NULL,
                release_date TIMESTAMP NOT NULL
            )
            ''')
        self.__connection.commit()

    def __del__(self):
        self.__connection.close()

    def add_app_client_data(self, client_id, client_secret):
        self.__connection.execute('''
        INSERT OR REPLACE INTO app
            (client_id, client_secret, insertion_data) VALUES(?,?,CURRENT_TIMESTAMP)
        ''', [client_id, client_secret])

        self.__connection.commit()

    def get_app_client_data(self):
        client = self.__connection.execute('''
        SELECT client_id, client_secret FROM app ORDER BY insertion_data DESC LIMIT 1 
        ''').fetchone()

        return ClientInfo(client[0], client[1]) if client else None

    def get_cached_login_token(self):
        token = self.__connection \
            .execute('SELECT token FROM login') \
            .fetchone()
        return token[0] if token else None

    def store_cached_login_token(self, token):
        self.__connection.execute('''
                INSERT OR REPLACE INTO login
                    (login_id, token, insertion_data) VALUES(?,?,CURRENT_TIMESTAMP)
                ''', [1, token])

        self.__connection.commit()

    def delete_cached_login_token(self):
        self.__connection.execute('DELETE FROM login')
        self.__connection.commit()

    def insert_track_cache_if_new(self, track: TrackInfo):
        try:
            self.__connection.execute('''
                            INSERT INTO tracks
                                (track_id, name, album, artist, disc_number, track_number, release_date)
                                VALUES(?,?,?,?,?, ?, ?)
                            ''', [track.id, track.name, track.album, track.artists[0], track.disc_number,
                                  track.track_number, track.release_date])
            self.__connection.commit()
            return True
        except sqlite3.IntegrityError as e:
            if "tracks.track_id" not in str(e.args):
                raise
            return False

    def get_track_cache_fields(self):
        return [x[1] for x in self.__connection.execute('PRAGMA table_info(tracks);').fetchall()]

    def read_track_cache_size(self):
        return self.__connection.execute('SELECT COUNT(1) FROM tracks').fetchone()[0]

    def read_track_cache(self, order_by, columns, where):
        self._check_for_valid_tracks_column(columns)

        sql = f'select {", ".join(columns)} from tracks'

        params = []

        if where and len(order_by) != where:
            self._check_for_valid_tracks_column([x[0] for x in where])
            for w in where:
                if w[1] not in [x.value for x in Comparator]:
                    raise Exception(f'Unhallowed comparator {w}.')

            grouped = {x[0]: list(x[1]) for x in groupby(where, key=lambda x: x[0])}

            sql += ' WHERE '
            sql += ' AND '.join(
                [f"({' OR '.join([f'{c[0]} {c[1]} ?' for c in v])})"
                 for x, v in grouped.items()]
            )

            for v in grouped.values():
                params.extend([c[2] for c in v])

        if order_by and len(order_by) != 0:
            self._check_for_valid_tracks_column(order_by)
            sql += f' ORDER BY {", ".join(order_by)}'

        return self.__connection.execute(sql, params).fetchall()

    def clear_track_cache(self):
        self.__connection.execute('DELETE FROM tracks')
        self.__connection.commit()

    def _check_for_valid_tracks_column(self, column):
        fields = self.get_track_cache_fields()
        for ob in column:
            if ob not in fields:
                raise Exception(f'Unhallowed column {ob}. ({",".join(fields)})')
