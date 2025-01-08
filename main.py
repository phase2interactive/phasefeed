import os
import json
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from database import init_db, cleanup_old_episodes
from feed_monitor import check_feeds, download_new_episodes
from transcriber import (
    TranscriptionService,
    LocalWhisperTranscriber,
    OpenAIWhisperTranscriber
)
from summarizer import summarize_episodes
import config
import openlit

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize OpenLIT if OTLP endpoint is configured
otlp_endpoint = os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT')
if otlp_endpoint:
    openlit.init()
    logger.info(f"OpenLIT initialized with endpoint: {otlp_endpoint}")
else:
    logger.warning("OTEL_EXPORTER_OTLP_ENDPOINT not set, OpenLIT initialization skipped")

def get_transcriber():
    """Initialize and return the appropriate transcriber based on configuration."""
    if config.TRANSCRIPTION_MODE == "openai":
        return OpenAIWhisperTranscriber()
    else:  # default to local
        return LocalWhisperTranscriber(model_path=config.WHISPER_MODEL)

def generate_daily_feed():
    """Generate a JSON feed of recent episodes with transcripts and summaries."""
    from database import get_db_session, PodcastEpisode
    
    session = get_db_session()
    yesterday = datetime.utcnow() - timedelta(days=1)
    
    recent_episodes = (
        session.query(PodcastEpisode)
        .filter(PodcastEpisode.created_at >= yesterday)
        .all()
    )
    
    feed_entries = []
    for ep in recent_episodes:
        entry = {
            "podcast_title": ep.show.title,
            "episode_title": ep.episode_title,
            "publication_date": ep.pub_date.isoformat() if ep.pub_date else None,
            "duration_seconds": ep.duration,
            "file_size_bytes": ep.file_size,
            "audio_path": ep.audio_path,
            "transcript_path": ep.transcript_path if ep.transcribed else None,
            "summary_path": ep.summary_path if ep.summarized else None
        }
        feed_entries.append(entry)
    
    feed_file = os.path.join(config.AUDIO_STORAGE_PATH, "daily_feed.json")
    os.makedirs(os.path.dirname(feed_file), exist_ok=True)
    
    with open(feed_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at": datetime.utcnow().isoformat(),
                "episodes": feed_entries
            },
            f,
            indent=2
        )
    
    logger.info(f"Generated daily feed with {len(feed_entries)} episodes")
    session.close()

def process_episodes():
    """Main processing function that runs all steps in sequence."""
    try:
        logger.info("Starting episode processing...")
        
        # Check feeds for new episodes
        check_feeds()
        
        # Download new episodes
        download_new_episodes()
        
        # Generate transcripts
        transcriber = get_transcriber()
        transcription_service = TranscriptionService(transcriber)
        transcription_service.transcribe_episodes()
        
        # Generate summaries (if Ollama is configured)
        summarize_episodes()
        
        # Generate daily feed
        generate_daily_feed()
        
        # Cleanup old episodes
        cleanup_old_episodes()
        
        logger.info("Episode processing complete")
        
    except Exception as e:
        logger.error(f"Error in process_episodes: {e}")

def setup_directories():
    """Create necessary directories if they don't exist."""
    os.makedirs(config.AUDIO_STORAGE_PATH, exist_ok=True)
    os.makedirs(config.TRANSCRIPT_STORAGE_PATH, exist_ok=True)

def main():
    """Main entry point."""
    # Create directories
    setup_directories()
    
    # Initialize database
    init_db()
    
    # Set up scheduler
    scheduler = BackgroundScheduler()
    
    # Schedule regular processing
    scheduler.add_job(
        process_episodes,
        'interval',
        minutes=config.CHECK_INTERVAL_MINUTES,
        next_run_time=datetime.now()
    )
    
    # Start the scheduler
    scheduler.start()
    
    try:
        # Keep the main thread alive
        while True:
            pass
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()

if __name__ == "__main__":
    main() 