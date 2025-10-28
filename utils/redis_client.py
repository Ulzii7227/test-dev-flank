import redis
import os

class RedisClient:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisClient, cls).__new__(cls)
            cls._instance._connect()
        return cls._instance

    def _connect(self):
        """
        Initialize Redis connection.
        Reads configuration from environment variables for security.
        """
        self.host = os.getenv("REDIS_HOST", "localhost")
        self.port = int(os.getenv("REDIS_PORT", 6379))
        self.password = os.getenv("REDIS_PASSWORD", None)
        self.decode_responses = os.getenv("REDIS_DECODE_RESPONSES", "true").lower() == "true"

        self.client = redis.Redis(
            host=self.host,
            port=self.port,
            password=self.password,
            decode_responses=self.decode_responses  
        )

        # Test connection
        try:
            if self.client.ping():
                print(f"Connected to Redis at {self.host}:{self.port}")
        except redis.ConnectionError as e:
            print(f"Redis connection failed: {e}")

    def get_client(self):
        return self.client
