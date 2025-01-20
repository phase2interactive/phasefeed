import feedparser
import yt_dlp
import os
import datetime
import requests
import re
from database import Show, Episode, ContentType, get_db_session
import config
import logging
from urllib.parse import urlparse, parse_qs
import mimetypes
from progress_handler import DownloadProgressBar
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def sanitize_filename(filename):
    """Create a safe filename from potentially unsafe string."""
    if not filename:
        return ""
    return "".join([c for c in filename if c.isalpha() or c.isdigit() or c in ' ._-']).rstrip()

def extract_channel_id(url: str) -> str | None:
    """Extract channel ID from various YouTube URL formats."""
    parsed = urlparse(url)
    if parsed.hostname not in ('www.youtube.com', 'youtube.com'):
        return None
        
    # Direct channel ID format: /channel/UCxxxxxx
    if parsed.path.startswith('/channel/'):
        return parsed.path.split('/')[2]
        
    # Handle /@username and /c/ formats by fetching the page
    if parsed.path.startswith('/@') or parsed.path.startswith('/c/'):
        try:
            response = requests.get(url, timeout=config.YOUTUBE_TIMEOUT)
            response.raise_for_status()
            
            # Extract channel ID from meta tags or canonical URL
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Try meta tag first
            meta_tag = soup.find('meta', {'itemprop': 'channelId'})
            if meta_tag and meta_tag.get('content'):
                return meta_tag['content']
            
            # Try canonical URL
            canonical = soup.find('link', {'rel': 'canonical'})
            if canonical and 'href' in canonical.attrs:
                channel_match = re.search(r'channel/([^/]+)', canonical['href'])
                if channel_match:
                    return channel_match.group(1)
                    
        except Exception as e:
            logger.error(f"Error extracting channel ID from {url}: {str(e)}")
            
    return None

def get_feed_url(channel_id: str) -> str:
    """Get RSS feed URL for a YouTube channel."""
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

def check_youtube_feeds():
    """Check YouTube channel feeds for new videos."""
    session = get_db_session()
    
    try:
        # First, ensure all channels have proper channel IDs
        for url in config.YOUTUBE_CHANNELS:
            existing = session.query(Show).filter_by(feed_url=url).first()
            if not existing:
                channel_id = extract_channel_id(url)
                if channel_id:
                    # Use yt-dlp to get channel info
                    ydl_opts = {
                        'quiet': True,
                        'no_warnings': True,
                        'extract_flat': True,
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        channel_info = ydl.extract_info(url, download=False)
                        channel_title = channel_info.get('channel') or channel_info.get('uploader')
                    
                    show = Show(
                        feed_url=url,
                        channel_id=channel_id,
                        content_type=ContentType.YOUTUBE,
                        title=channel_title or f"channel_{channel_id}"  # Fallback if title not found
                    )
                    session.add(show)
                    logger.info(f"Added new YouTube channel: {channel_title or url}")
                else:
                    logger.error(f"Could not extract channel ID from: {url}")
        
        session.commit()
        
        # Now check feeds for all channels
        youtube_shows = session.query(Show).filter_by(content_type=ContentType.YOUTUBE).all()
        
        for show in youtube_shows:
            try:
                feed_url = get_feed_url(show.channel_id)
                logger.info(f"Checking YouTube feed: {feed_url}")
                
                feed = feedparser.parse(feed_url)
                if feed.bozo:
                    logger.error(f"Error parsing feed: {feed_url} - {feed.bozo_exception}")
                    continue

                for entry in feed.entries[:config.MAX_EPISODES_PER_FEED]:
                    video_id = entry.yt_videoid
                    
                    # Check if we already have this video
                    existing = session.query(Episode).filter_by(
                        show_id=show.id,
                        video_id=video_id
                    ).first()
                    
                    if not existing:
                        # Create new episode
                        episode = Episode(
                            show_id=show.id,
                            episode_title=entry.title,
                            pub_date=datetime.datetime.strptime(entry.published, "%Y-%m-%dT%H:%M:%S%z"),
                            video_id=video_id,
                            thumbnail_url=entry.media_thumbnail[0]['url'] if entry.get('media_thumbnail') else None,
                            original_url=entry.link
                        )
                        session.add(episode)
                        logger.info(f"Added new video: {entry.title}")

                session.commit()
                
            except Exception as e:
                logger.error(f"Error processing YouTube feed for {show.feed_url}: {str(e)}")
                session.rollback()
                continue

    except Exception as e:
        logger.error(f"Error in check_youtube_feeds: {str(e)}")
        session.rollback()
    finally:
        session.close()

def download_youtube_videos():
    """Download new YouTube videos and extract audio."""
    session = get_db_session()
    
    try:
        new_episodes = (
            session.query(Episode)
            .join(Show)
            .filter(
                Show.content_type == ContentType.YOUTUBE,
                Episode.downloaded == False
            )
            .all()
        )

        if not new_episodes:
            logger.info("No new YouTube episodes to download")
            return

        for episode in new_episodes:
            # Create channel-specific directory
            channel_dir = os.path.join(config.AUDIO_STORAGE_PATH, sanitize_filename(episode.show.title or f"channel_{episode.show.id}"))
            os.makedirs(channel_dir, exist_ok=True)
            
            # Setup output path in channel directory
            output_path = os.path.join(
                channel_dir,
                f"{sanitize_filename(episode.episode_title)}_{episode.video_id}"  # Removed .mp3 extension
            )
            
            success = False
            error_msg = None
            
            try:
                # Setup progress tracking
                progress_bar = DownloadProgressBar(episode.episode_title)
                
                # Setup yt-dlp options
                ydl_opts = {
                    # Format selection
                    'format': 'bestaudio/best',
                    'format_sort': ['abr', 'asr', 'res', 'br'],  # Prefer better audio quality
                    
                    # Audio extraction
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': config.YOUTUBE_AUDIO_QUALITY,
                    }],
                    
                    # Output settings
                    'outtmpl': output_path,
                    'writethumbnail': False,
                    
                    # Download settings
                    'progress_hooks': [progress_bar.yt_dlp_hook],
                    'retries': config.YOUTUBE_MAX_RETRIES,
                    'fragment_retries': config.YOUTUBE_MAX_RETRIES,
                    'socket_timeout': config.YOUTUBE_TIMEOUT,
                    'extractor_retries': config.YOUTUBE_MAX_RETRIES,
                    
                    # Network settings
                    'socket_timeout': config.YOUTUBE_TIMEOUT,
                    'nocheckcertificate': False,
                    
                    # Error handling
                    'ignoreerrors': False,
                    'no_warnings': False,
                    'verbose': False,
                    
                    # Geo-restriction handling
                    'geo_bypass': True,
                    'geo_bypass_country': 'US',
                    
                    # System settings
                    'quiet': False,
                    'no_color': False,
                    
                    # Sponsorblock settings (optional)
                    # 'sponsorblock_remove': ['sponsor', 'intro', 'outro', 'selfpromo'],
                    
                    # Age-gate bypass
                    'cookiesfrombrowser': None,  # Can be set to ('chrome', 'firefox', etc)
                }

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    logger.info(f"Downloading video: {episode.episode_title}")
                    ydl.download([episode.original_url])
                success = True
                
            except yt_dlp.utils.DownloadError as e:
                error_msg = str(e)
                if "Video unavailable" in error_msg:
                    logger.error(f"Video {episode.episode_title} is no longer available")
                elif "Sign in to confirm your age" in error_msg:
                    logger.error(f"Video {episode.episode_title} is age restricted. Consider setting cookiesfrombrowser")
                elif "The uploader has not made this video available in your country" in error_msg:
                    logger.error(f"Video {episode.episode_title} is geo-restricted")
                elif "This video is only available to users with special access" in error_msg:
                    logger.error(f"Video {episode.episode_title} requires special access (members only, etc)")
                else:
                    logger.error(f"Error downloading video {episode.episode_title}: {error_msg}")
                # Cleanup partial download if it exists
                if os.path.exists(output_path):
                    try:
                        os.remove(output_path)
                    except OSError:
                        pass
                        
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Unexpected error downloading video {episode.episode_title}: {error_msg}")
                # Cleanup partial download if it exists
                if os.path.exists(output_path):
                    try:
                        os.remove(output_path)
                    except OSError:
                        pass
            
            if success:
                try:
                    # Get final output path with .mp3 extension
                    final_output_path = f"{output_path}.mp3"
                    
                    # Update episode record
                    episode.audio_path = final_output_path
                    episode.downloaded = True
                    episode.file_size = os.path.getsize(final_output_path)
                    
                    # Get duration using existing function from feed_monitor
                    from feed_monitor import get_audio_duration
                    episode.duration = get_audio_duration(final_output_path)
                    
                    # Log the values before committing
                    logger.info(f"Updating database for {episode.episode_title}:")
                    logger.info(f"  - audio_path: {final_output_path}")
                    logger.info(f"  - downloaded: True")
                    logger.info(f"  - file_size: {episode.file_size} bytes")
                    logger.info(f"  - duration: {episode.duration} seconds")
                    
                    session.commit()
                    logger.info(f"Successfully downloaded and processed: {episode.episode_title}")
                    
                except Exception as e:
                    logger.error(f"Error updating episode record for {episode.episode_title}: {str(e)}")
                    session.rollback()
                    # Cleanup downloaded file if we couldn't update the database
                    if os.path.exists(final_output_path):
                        try:
                            os.remove(final_output_path)
                            logger.info(f"Cleaned up failed download: {final_output_path}")
                        except OSError as ose:
                            logger.error(f"Failed to clean up file {final_output_path}: {str(ose)}")
            
    except Exception as e:
        logger.error(f"Error in download_youtube_videos: {str(e)}")
        session.rollback()
    finally:
        session.close() 