import asyncio
import schedule
import time
import os
from feed_monitor import check_feeds, download_new_episodes
from youtube_handler import check_youtube_feeds, download_youtube_videos
from transcriber import TranscriptionService, get_transcriber
from summarizer import summarize_episodes
from database import init_db, cleanup_old_episodes
import logging
import config
import openlit
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize OpenLIT if OTLP endpoint is configured
otlp_endpoint = os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT')
if otlp_endpoint:
    openlit.init()
    logger.info(f"OpenLIT initialized with endpoint: {otlp_endpoint}")
else:
    logger.warning("OTEL_EXPORTER_OTLP_ENDPOINT not set, OpenLIT initialization skipped")

def setup_directories():
    """Create necessary directories if they don't exist."""
    os.makedirs(config.AUDIO_STORAGE_PATH, exist_ok=True)
    os.makedirs(config.TRANSCRIPT_STORAGE_PATH, exist_ok=True)
    logger.info("Storage directories initialized")

async def run_feed_checks():
    """Run feed checks for both podcasts and YouTube channels."""
    try:
        check_feeds()
        check_youtube_feeds()
    except Exception as e:
        logger.error(f"Error in feed checks: {str(e)}")

async def run_downloads():
    """Run downloads for both podcasts and YouTube videos."""
    try:
        download_new_episodes()
        download_youtube_videos()
    except Exception as e:
        logger.error(f"Error in downloads: {str(e)}")

async def run_transcriptions():
    """Process transcription queue."""
    try:
        transcriber = get_transcriber()
        service = TranscriptionService(transcriber)
        service.transcribe_episodes()
    except Exception as e:
        logger.error(f"Error in transcriptions: {str(e)}")

async def run_summaries():
    """Process summary queue."""
    try:
        summarize_episodes()
    except Exception as e:
        logger.error(f"Error in summaries: {str(e)}")

async def cleanup():
    """Run cleanup tasks."""
    try:
        cleanup_old_episodes()
    except Exception as e:
        logger.error(f"Error in cleanup: {str(e)}")

def log_next_run(job_name: str, minutes: int):
    """Log when a job will next run based on its schedule."""
    now = datetime.now()
    next_run = now + timedelta(minutes=minutes)
    logger.info(f"Next {job_name} scheduled for: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")

async def main():
    """Main application loop."""
    # Create directories
    setup_directories()
    
    # Initialize database
    init_db()
    logger.info("Database initialized")
    
    # Initialize transcription service
    transcriber = get_transcriber()
    transcription_service = TranscriptionService(transcriber)
    
    # Schedule all jobs
    schedule.every(config.CHECK_INTERVAL_MINUTES).minutes.do(check_feeds)
    schedule.every(config.CHECK_INTERVAL_MINUTES).minutes.do(check_youtube_feeds)
    schedule.every(config.CHECK_INTERVAL_MINUTES).minutes.do(download_youtube_videos)
    schedule.every(config.CHECK_INTERVAL_MINUTES).minutes.do(lambda: transcription_service.transcribe_episodes())
    schedule.every(config.CHECK_INTERVAL_MINUTES).minutes.do(summarize_episodes)
    
    # Run all jobs immediately on startup
    logger.info("Starting initial run of all jobs...")
    check_feeds()
    check_youtube_feeds()
    download_youtube_videos()
    transcription_service.transcribe_episodes()
    summarize_episodes()
    
    logger.info("Initial run complete. Starting scheduled execution...")
    
    while True:
        schedule.run_pending()
        
        # Log next run times for all jobs
        log_next_run("feed check", config.CHECK_INTERVAL_MINUTES)
        log_next_run("YouTube feed check", config.CHECK_INTERVAL_MINUTES)
        log_next_run("YouTube download", config.CHECK_INTERVAL_MINUTES)
        log_next_run("transcription", config.CHECK_INTERVAL_MINUTES)
        log_next_run("summarization", config.CHECK_INTERVAL_MINUTES)
        
        await asyncio.sleep(60)  # Sleep for 1 minute

if __name__ == "__main__":
    asyncio.run(main()) 