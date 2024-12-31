# Podcast Buddy

A local podcast monitoring and transcription system that:
- Monitors RSS feeds for new podcast episodes
- Downloads new episodes automatically
- Transcribes audio using mlx-whisper
- (Optional) Summarizes content using local LLMs
- Stores metadata in SQLite
- Generates daily feed summaries

## Installation

1. Ensure you have Python 3.x installed
2. Install ffmpeg (required for mlx-whisper):
```bash
brew install ffmpeg
```

3. (Optional) Install and set up Ollama for summarization:
```bash
# Install Ollama
brew install ollama

# Start Ollama server
ollama serve

# In a new terminal, pull the model
ollama pull llama3.2

# Verify the model is working
ollama run llama3.2 "Hello, how are you?"
```

4. Set up Python environment:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage

1. Configure your podcast feeds in `config.py`
2. Ensure Ollama is running if you want summaries:
```bash
# Start Ollama in a separate terminal if not already running
ollama serve
```
3. Run the application:
```bash
python main.py
```

The app will:
- Check configured RSS feeds
- Download new episodes
- Generate transcripts
- Create summaries (if configured)
- Generate a daily feed JSON

Audio files are stored in `~/Podcasts/` by default
Transcripts are stored in `~/Podcasts/Transcripts/` 