import os
import requests
import logging
from database import PodcastEpisode, get_db_session
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_summary(text):
    """Generate a summary using Ollama."""
    prompt = f"""Please provide a concise summary of this podcast episode transcript. Focus on:
1. Main topics discussed
2. Key takeaways
3. Important quotes or moments

Transcript:
{text}

Summary:"""

    try:
        response = requests.post(
            config.OLLAMA_URL,
            json={
                "model": config.OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False
            }
        )
        
        if response.status_code == 200:
            return response.json()["response"]
        else:
            logger.error(f"Ollama API error: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"Error calling Ollama API: {e}")
        return None

def summarize_episodes():
    """Find all transcribed but not summarized episodes and generate summaries."""
    session = get_db_session()
    episodes = (
        session.query(PodcastEpisode)
        .filter_by(transcribed=True, summarized=False)
        .all()
    )

    for ep in episodes:
        if not ep.transcript_path or not os.path.exists(ep.transcript_path):
            logger.error(f"Transcript not found for {ep.episode_title}")
            continue

        try:
            logger.info(f"Summarizing {ep.episode_title}...")
            
            # Read transcript
            with open(ep.transcript_path, "r", encoding="utf-8") as f:
                transcript_text = f.read()
            
            # Generate summary
            summary = generate_summary(transcript_text)
            if not summary:
                continue
                
            # Format summary with metadata
            summary_text = f"""Title: {ep.episode_title}
Podcast: {ep.podcast_title}
Date: {ep.pub_date}
Duration: {ep.duration} seconds

Summary:
{summary}
"""
            
            # Save summary
            safe_filename = "".join([c for c in ep.episode_title if c.isalpha() or c.isdigit() or c in ' ._-']).rstrip()
            summary_path = os.path.join(
                config.TRANSCRIPT_STORAGE_PATH,
                f"{ep.podcast_title}_{safe_filename}_summary.txt"
            )
            
            with open(summary_path, "w", encoding="utf-8") as f:
                f.write(summary_text)
            
            # Update database
            ep.summary_path = summary_path
            ep.summarized = True
            session.commit()
            
            logger.info(f"Successfully summarized: {ep.episode_title}")
            
        except Exception as e:
            logger.error(f"Failed to summarize {ep.episode_title}: {e}")
            continue

    session.close()

def get_summary(episode_id):
    """Retrieve summary for a specific episode."""
    session = get_db_session()
    episode = session.query(PodcastEpisode).filter_by(id=episode_id).first()
    
    if not episode or not episode.summary_path:
        return None
        
    try:
        with open(episode.summary_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error reading summary for episode {episode_id}: {e}")
        return None
    finally:
        session.close() 