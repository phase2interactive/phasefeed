import os

# Storage paths
AUDIO_STORAGE_PATH = os.path.expanduser("~/Podcasts")
TRANSCRIPT_STORAGE_PATH = os.path.expanduser("~/Podcasts/Transcripts")

# Database configuration
DB_PATH = os.path.join(os.getcwd(), "podcast_app.db")

# Example podcast feeds (add your own)
PODCAST_FEEDS = [
    "https://feeds.megaphone.fm/profgmarkets",  # Example feed
]

# Maximum number of episodes to pull from each feed
MAX_EPISODES_PER_FEED = 5

# MLX Whisper model configuration
WHISPER_MODEL = "mlx-community/distil-whisper-large-v3"

# Ollama configuration (optional)
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2"

# Scheduling configuration
CHECK_INTERVAL_MINUTES = 60  # How often to check feeds
RETAIN_DAYS = 30  # How many days of history to keep 