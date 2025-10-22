from tinydb import TinyDB, Query
from config import Config

# Simple Key-Value storage using TinyDB
class Storage:
    def __init__(self, db_name: str):
        self.db = TinyDB(Config.BASE_DIR / f"{db_name}.json")
        self.Query = Query()
    
    def get(self, key):
        result = self.db.get(self.Query.key == key)
        return result['value'] if result else None

    def set(self, key, value):
        self.db.upsert({'key': key, 'value': value}, self.Query.key == key)

    def all(self):
        return self.db.all()
    
    def remove(self, key):
        self.db.remove(self.Query.key == key)

# Instances for different states
playback_storage = Storage("playback_state")
language_storage = Storage("user_languages")
