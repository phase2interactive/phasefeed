from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.requests import Request
import json
import os
import config
from datetime import datetime

app = FastAPI(title="Podcast Buddy")
templates = Jinja2Templates(directory="templates")

# Create static directory if it doesn't exist
os.makedirs("static", exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

def load_feed():
    """Load and parse the daily feed JSON file."""
    feed_path = os.path.join(config.AUDIO_STORAGE_PATH, "daily_feed.json")
    try:
        with open(feed_path, 'r') as f:
            feed_data = json.load(f)
            
        # Add formatted date and load summaries
        for episode in feed_data['episodes']:
            if episode['publication_date']:
                date = datetime.fromisoformat(episode['publication_date'])
                episode['formatted_date'] = date.strftime('%B %d, %Y')
            else:
                episode['formatted_date'] = 'Unknown date'
                
            # Load summary if available
            if episode['summary_path'] and os.path.exists(episode['summary_path']):
                with open(episode['summary_path'], 'r') as f:
                    episode['summary'] = f.read()
            else:
                episode['summary'] = 'Summary not available'
                
            # Format duration
            if episode['duration_seconds']:
                minutes = episode['duration_seconds'] // 60
                seconds = episode['duration_seconds'] % 60
                episode['duration_formatted'] = f"{minutes}m {seconds}s"
            else:
                episode['duration_formatted'] = 'Unknown duration'
                
            # Format file size
            if episode['file_size_bytes']:
                mb_size = episode['file_size_bytes'] / (1024 * 1024)
                episode['size_formatted'] = f"{mb_size:.1f} MB"
            else:
                episode['size_formatted'] = 'Unknown size'
            
            # Create audio URL
            if episode['audio_path'] and os.path.exists(episode['audio_path']):
                episode['audio_url'] = f"/audio/{os.path.basename(episode['audio_path'])}"
            else:
                episode['audio_url'] = None
            
        return feed_data
    except Exception as e:
        return {"generated_at": datetime.now().isoformat(), "episodes": []}

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Render the home page with episodes."""
    feed_data = load_feed()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "feed_data": feed_data,
            "last_updated": datetime.fromisoformat(feed_data['generated_at']).strftime('%B %d, %Y %I:%M %p')
        }
    )

@app.get("/audio/{filename}")
async def get_audio(filename: str):
    """Serve audio files."""
    audio_path = os.path.join(config.AUDIO_STORAGE_PATH, filename)
    if os.path.exists(audio_path):
        return FileResponse(audio_path, media_type="audio/mpeg")
    raise HTTPException(status_code=404, detail="Audio file not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000) 