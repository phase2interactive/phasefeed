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

# Transcription configuration
TRANSCRIPTION_MODE = "openai"  # Options: "local" or "openai"

# MLX Whisper model configuration (for local transcription)
WHISPER_MODEL = "mlx-community/distil-whisper-large-v3"

# Summarization configuration
SUMMARIZATION_MODE = "openai"  # Options: "local" or "openai"
OPENAI_SUMMARY_MODEL = "gpt-4o-2024-11-20"  # Model to use for OpenAI summarization

# Ollama configuration used for local summarization
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:3b"

# Transcript processing configuration
TRANSCRIPT_CHUNK_SIZE = 50000  # Characters per chunk
TRANSCRIPT_CHUNK_OVERLAP = 2000  # Characters of overlap between chunks 

# Scheduling configuration
CHECK_INTERVAL_MINUTES = 60  # How often to check feeds
RETAIN_DAYS = 30  # How many days of history to keep 

