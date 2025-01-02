''' reset_summaries.py

This script resets the summaries for all episodes in the database. This is useful if you want to re-run the summarization process.

```bash
python scripts/reset_summaries.py
```
'''

import os
import sys

# Add parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_session, PodcastEpisode, EpisodeContent
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def reset_summaries():
    """Remove summary_path data and set summarized=False for all episodes."""
    session = get_db_session()
    try:
        # Get all episodes that have been summarized
        episodes = session.query(PodcastEpisode).filter_by(summarized=True).all()
        
        for ep in episodes:
            # Delete the summary file if it exists
            if ep.summary_path and os.path.exists(ep.summary_path):
                try:
                    os.remove(ep.summary_path)
                    logger.info(f"Deleted summary file: {ep.summary_path}")
                except OSError as e:
                    logger.error(f"Error deleting summary file {ep.summary_path}: {e}")
            
            # Reset the database fields
            ep.summary_path = None
            ep.summarized = False
            
            # Clear the summary in episode_content if it exists
            content = session.query(EpisodeContent).filter_by(episode_id=ep.id).first()
            if content:
                content.summary = 'Summary not available'
                logger.info(f"Reset summary in episode_content for episode {ep.id}")
        
        session.commit()
        logger.info("Successfully reset all episode summaries")
        
    except Exception as e:
        logger.error(f"Error resetting summaries: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    reset_summaries() 