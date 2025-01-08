from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.requests import Request
import os
import config
from datetime import datetime
from database import get_db_session, EpisodeContent, PodcastEpisode
from urllib.parse import unquote
import markdown2
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI(title="PhaseFeed")

@app.on_event("startup")
async def startup_event():
    logger.debug("Starting up FastAPI application")

# Create static directory if it doesn't exist
os.makedirs("static", exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize templates
templates = Jinja2Templates(directory="templates")

def get_episodes():
    """Load episodes from the database."""
    logger.debug("Fetching episodes from database")
    session = get_db_session()
    try:
        query = (
            session.query(EpisodeContent)
            .join(EpisodeContent.episode)
            .order_by(PodcastEpisode.pub_date.desc())
        )
        logger.debug(f"Executing query: {query}")
        
        episodes = query.all()
        logger.debug(f"Query executed successfully, got {len(episodes)} episodes")
        
        # Convert to dictionary format expected by template
        episodes_data = []
        for content in episodes:
            try:
                # Convert markdown to HTML if summary exists
                summary_html = markdown2.markdown(content.summary) if content.summary else None
                
                episode_data = {
                    'id': content.episode.id,
                    'podcast_title': content.episode.show.title,
                    'episode_title': content.episode.episode_title,
                    'formatted_date': content.formatted_date,
                    'duration_formatted': content.duration_formatted,
                    'size_formatted': content.size_formatted,
                    'summary': summary_html
                }
                episodes_data.append(episode_data)
            except Exception as e:
                logger.error(f"Error processing episode {content.id}: {str(e)}")
                continue
            
        logger.debug(f"Found {len(episodes_data)} episodes")
        return {
            'generated_at': datetime.utcnow().isoformat(),
            'episodes': episodes_data
        }
    except Exception as e:
        logger.error(f"Database error in get_episodes: {str(e)}")
        raise
    finally:
        session.close()

@app.get("/")
async def home(request: Request):
    """Render the home page with episodes."""
    logger.debug("Home route accessed")
    try:
        feed_data = get_episodes()
        logger.debug(f"Got {len(feed_data['episodes'])} episodes")
        response = templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "feed_data": feed_data,
                "last_updated": datetime.fromisoformat(feed_data['generated_at']).strftime('%B %d, %Y %I:%M %p')
            }
        )
        logger.debug("Template response generated")
        return response
    except Exception as e:
        logger.error(f"Error in home route: {str(e)}")
        raise

@app.get("/audio/{episode_id}")
async def get_audio(episode_id: int):
    """Serve audio files."""
    logger.debug(f"Audio route accessed for episode {episode_id}")
    session = get_db_session()
    try:
        episode = (
            session.query(PodcastEpisode)
            .filter(PodcastEpisode.id == episode_id)
            .first()
        )
        
        if not episode or not episode.audio_path:
            logger.error(f"Audio file not found for episode {episode_id}")
            raise HTTPException(status_code=404, detail=f"Audio file not found for episode {episode_id}")
            
        if not os.path.exists(episode.audio_path):
            logger.error(f"Audio file missing from disk for episode {episode_id}")
            raise HTTPException(status_code=404, detail=f"Audio file missing from disk for episode {episode_id}")
            
        return FileResponse(episode.audio_path, media_type="audio/mpeg")
    finally:
        session.close()

if __name__ == "__main__":
    import uvicorn
    logger.debug("Starting uvicorn server")
    uvicorn.run("web_server:app", host="127.0.0.1", port=8000, reload=True) 