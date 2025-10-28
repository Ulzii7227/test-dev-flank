import os
from pymongo import MongoClient
from dotenv import load_dotenv
from pymongo.database import Database
from typing import Optional

load_dotenv()

class MongoDB:
    _client: Optional[MongoClient] = None
    _db: Optional[Database] = None

    @classmethod
    def initialize(cls):
        """Initialize the MongoDB client and database."""
        if cls._client is None:
            MONGODB_URI = os.getenv("MONGODB_URI")
            MONGODB_DB = os.getenv("MONGODB_DB", "Flank")
            cls._client = MongoClient(MONGODB_URI)
            cls._db = cls._client[MONGODB_DB]
        return cls._db

    @classmethod
    def get_client(cls):
        """Get the MongoDB client."""
        if cls._client is None:
            cls.initialize()
        return cls._client

    @classmethod
    def get_db(cls)->Database:
        """Get the MongoDB database."""
        if cls._db is None:
            cls.initialize()
        
        assert cls._db is not None, "MongoDB database not initialized"
        
        return cls._db
