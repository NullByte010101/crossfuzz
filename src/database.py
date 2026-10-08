import os
import sqlite3

from utils.config_loader import config


class DBHandler:
    """
    Thin wrapper around a single sqlite3 connection.

    check_same_thread=False allows the connection to be created on one thread
    and used by another. This is only safe when access is strictly serialised.
    """

    def __init__(self, path=None):
        path = path or config.get("paths.db_file")
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False, timeout=30.0)
        self.conn.execute("pragma journal_mode=WAL")      # concurrent reads while writing
        self.conn.execute("pragma synchronous=NORMAL")    # much faster, still crash-safe
        self.conn.execute("pragma busy_timeout=30000")
        self.cursor = self.conn.cursor()

    def close(self):
        try:
            self.conn.commit()
        except Exception:
            pass
        try:
            self.cursor.close()
        finally:
            self.conn.close()
