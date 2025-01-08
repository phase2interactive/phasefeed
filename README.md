# PhaseFeed

A local podcast monitoring and transcription system that:
- Monitors RSS feeds for new podcast episodes
- Downloads new episodes automatically
- Transcribes audio using either OpenAI Whisper API or local mlx-whisper
- Summarizes content using either OpenAI GPT-4 or local LLMs via Ollama
- Stores metadata in SQLite
- Generates daily feed summaries

## Installation

1. Ensure you have Python 3.x installed
2. Install ffmpeg (required for audio processing):
```bash
brew install ffmpeg
```

3. Install and set up Ollama (required only for local summarization):
```bash
# Install Ollama
brew install ollama

# Start Ollama server
ollama serve

# In a new terminal, pull the model
ollama pull qwen2.5:3b

# Verify the model is working
ollama run qwen2.5:3b "Hello, how are you?"
```

4. Set up Python environment:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

5. Configure environment variables (if using OpenAI):
```bash
cp .env.example .env
# Edit .env and add your OpenAI API key if using OpenAI services
```

## Configuration

The application can be configured through `config.py`. Key settings include:

### Storage Configuration
- `AUDIO_STORAGE_PATH`: Where to store downloaded podcasts (default: `~/Podcasts`)
- `TRANSCRIPT_STORAGE_PATH`: Where to store transcripts (default: `~/Podcasts/Transcripts`)

### Feed Configuration
- `PODCAST_FEEDS`: List of RSS feed URLs to monitor
- `MAX_EPISODES_PER_FEED`: Maximum number of episodes to pull from each feed (default: 5)

### Transcription Configuration
- `TRANSCRIPTION_MODE`: Choose between "local" or "openai"
  - "local": Uses mlx-whisper locally (free, no API key needed)
  - "openai": Uses OpenAI's Whisper API (requires API key)
- `WHISPER_MODEL`: Model to use for local transcription (default: "mlx-community/distil-whisper-large-v3")

### Summarization Configuration
- `SUMMARIZATION_MODE`: Choose between "local" or "openai"
  - "local": Uses Ollama locally (free, no API key needed)
  - "openai": Uses OpenAI's GPT-4 (requires API key)
- `OPENAI_SUMMARY_MODEL`: Model to use for OpenAI summarization
- `OLLAMA_MODEL`: Model to use for local summarization (default: "qwen2.5:3b")
- `OLLAMA_URL`: URL for Ollama server (default: "http://localhost:11434")

### Processing Configuration
- `CHECK_INTERVAL_MINUTES`: How often to check feeds (default: 60)
- `RETAIN_DAYS`: How many days of history to keep (default: 30)

## Usage

1. Configure your settings in `config.py`
2. If using local summarization, ensure Ollama is running:
```bash
# Start Ollama in a separate terminal if not already running
ollama serve
```
3. Run the services:

### Background Processing Service
To run the background service that monitors feeds and processes episodes:
```bash
python main.py
```

The background service will:
- Check configured RSS feeds
- Download new episodes
- Generate transcripts (using chosen transcription method)
- Create summaries (using chosen summarization method)
- Save all metadata to a local SQLite database

Audio files are stored in `~/Podcasts/` by default
Transcripts are stored in `~/Podcasts/Transcripts/` 

### Web Server
To access the content through a web interface:
```bash
python web_server.py
```
Then open your browser to `http://localhost:8000`

## Observability with OpenLIT (optional)

This project uses OpenLIT to track observability metrics. To enable, set the `OTEL_EXPORTER_OTLP_ENDPOINT` in your .env file or set the environment variable in your shell.

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318
```

Clone the OpenLIT repo:
```bash
git clone git@github.com:openlit/openlit.git
```

Start Docker Compose:
```bash
docker compose up -d
```