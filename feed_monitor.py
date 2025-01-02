import feedparser
import requests
import os
import datetime
from database import PodcastEpisode, get_db_session, Show
import config
import logging
from urllib.parse import urlparse
import mimetypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def sanitize_filename(filename):
    """Create a safe filename from potentially unsafe string."""
    return "".join([c for c in filename if c.isalpha() or c.isdigit() or c in ' ._-']).rstrip()

def get_audio_duration(file_path):
    """Get audio duration using ffmpeg."""
    try:
        import subprocess
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        return int(float(result.stdout))
    except:
        return None

def check_feeds():
    """Check configured RSS feeds for new episodes (limited to 5 most recent)."""
    session = get_db_session()
    
    for feed_url in config.PODCAST_FEEDS:
        try:
            logger.info(f"Checking feed: {feed_url}")
            feed = feedparser.parse(feed_url)

            if feed.bozo:
                logger.error(f"Error parsing feed: {feed_url} - {feed.bozo_exception}")
                continue

            # Get or create show
            show = session.query(Show).filter_by(feed_url=feed_url).first()
            if not show:
                show = Show(
                    feed_url=feed_url,
                    title=feed.feed.title if hasattr(feed, 'feed') else ""
                )
                session.add(show)
                session.commit()

            # Sort entries by publication date (most recent first)
            sorted_entries = sorted(
                feed.entries,
                key=lambda entry: entry.get('published_parsed', 0),
                reverse=True
            )

            # Process episodes limited by MAX_EPISODES_PER_FEED setting
            for entry in sorted_entries[:config.MAX_EPISODES_PER_FEED]:
                # Skip if episode already exists
                existing = (
                    session.query(PodcastEpisode)
                    .filter_by(show_id=show.id, episode_title=entry.title)
                    .first()
                )
                if existing:
                    continue

                pub_date = None
                if hasattr(entry, "published_parsed"):
                    pub_date = datetime.datetime(*entry.published_parsed[:6])

                new_episode = PodcastEpisode(
                    show_id=show.id,
                    episode_title=entry.title,
                    pub_date=pub_date
                )
                session.add(new_episode)
                logger.info(f"Added new episode: {entry.title}")

            session.commit()
        except Exception as e:
            logger.error(f"Error processing feed {feed_url}: {e}")
            continue

    session.close()

def download_new_episodes():
    """Download audio files for episodes that haven't been downloaded yet."""
    session = get_db_session()
    episodes_to_download = (
        session.query(PodcastEpisode)
        .filter_by(downloaded=False)
        .all()
    )

    for ep in episodes_to_download:
        try:
            feed = feedparser.parse(ep.feed_url)
            for entry in feed.entries:
                if entry.title == ep.episode_title:
                    if hasattr(entry, "enclosures") and len(entry.enclosures) > 0:
                        audio_url = entry.enclosures[0].href
                        
                        # Create safe filename
                        file_name = f"{ep.episode_title}.mp3"
                        safe_file_name = sanitize_filename(file_name)
                        
                        # Create podcast directory
                        podcast_dir = os.path.join(config.AUDIO_STORAGE_PATH, sanitize_filename(ep.podcast_title))
                        os.makedirs(podcast_dir, exist_ok=True)
                        
                        local_path = os.path.join(podcast_dir, safe_file_name)
                        
                        logger.info(f"Downloading {audio_url} to {local_path}")
                        
                        # Stream download to handle large files
                        response = requests.get(audio_url, stream=True)
                        file_size = 0
                        
                        with open(local_path, "wb") as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                if chunk:
                                    file_size += len(chunk)
                                    f.write(chunk)
                        
                        # Update episode record
                        ep.audio_path = local_path
                        ep.downloaded = True
                        ep.file_size = file_size
                        ep.duration = get_audio_duration(local_path)
                        
                        session.commit()
                        logger.info(f"Successfully downloaded: {ep.episode_title}")
                    break
        except Exception as e:
            logger.error(f"Failed to download {ep.episode_title}: {e}")
    
    session.close() 