import sqlite3

from collections import namedtuple

ClientInfo = namedtuple("ClientInfo", "id secret")


class Store:
    """
    DAO for the sql database.
    The database is used to store some global program state,
    which shall persist over multiple executions.
    """

    def __init__(self, db_location="data.db"):
        self.SPOTIFY_REQUIRED_SCOPE = 'playlist-read-private'

        self.__connection = sqlite3.connect(db_location)

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
        token = self.__connection\
            .execute('SELECT token FROM login')\
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
