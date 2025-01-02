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

app = FastAPI(title="Podcast Buddy")
templates = Jinja2Templates(directory="templates")

# Create static directory if it doesn't exist
os.makedirs("static", exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

def get_episodes():
    """Load episodes from the database."""
    session = get_db_session()
    try:
        episodes = (
            session.query(EpisodeContent)
            .join(EpisodeContent.episode)
            .order_by(PodcastEpisode.pub_date.desc())
            .all()
        )
        
        # Convert to dictionary format expected by template
        episodes_data = []
        for content in episodes:
            episode_data = {
                'id': content.episode.id,
                'podcast_title': content.episode.show.title,
                'episode_title': content.episode.episode_title,
                'formatted_date': content.formatted_date,
                'duration_formatted': content.duration_formatted,
                'size_formatted': content.size_formatted,
                'summary': content.summary
            }
            episodes_data.append(episode_data)
            
        return {
            'generated_at': datetime.utcnow().isoformat(),
            'episodes': episodes_data
        }
    finally:
        session.close()

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Render the home page with episodes."""
    feed_data = get_episodes()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "feed_data": feed_data,
            "last_updated": datetime.fromisoformat(feed_data['generated_at']).strftime('%B %d, %Y %I:%M %p')
        }
    )

@app.get("/audio/{episode_id}")
async def get_audio(episode_id: int):
    """Serve audio files."""
    session = get_db_session()
    try:
        episode = (
            session.query(PodcastEpisode)
            .filter(PodcastEpisode.id == episode_id)
            .first()
        )
        
        if not episode or not episode.audio_path:
            raise HTTPException(status_code=404, detail=f"Audio file not found for episode {episode_id}")
            
        if not os.path.exists(episode.audio_path):
            raise HTTPException(status_code=404, detail=f"Audio file missing from disk for episode {episode_id}")
            
        return FileResponse(episode.audio_path, media_type="audio/mpeg")
    finally:
        session.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web_server:app", host="127.0.0.1", port=8000, reload=True) 