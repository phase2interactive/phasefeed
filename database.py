from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
import config
import os

engine = create_engine(f"sqlite:///{config.DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class PodcastEpisode(Base):
    __tablename__ = "episodes"

    id = Column(Integer, primary_key=True, index=True)
    feed_url = Column(String)
    podcast_title = Column(String)
    episode_title = Column(String)
    pub_date = Column(DateTime)
    audio_path = Column(String)
    transcript_path = Column(String)
    summary_path = Column(String)
    downloaded = Column(Boolean, default=False)
    transcribed = Column(Boolean, default=False)
    summarized = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    file_size = Column(Integer)  # Size in bytes
    duration = Column(Integer)   # Duration in seconds

def init_db():
    """Initialize the database, creating tables if they don't exist."""
    Base.metadata.create_all(bind=engine)

def get_db_session():
    """Get a new database session."""
    return SessionLocal()

def cleanup_old_episodes(days=None):
    """Remove episodes older than specified days."""
    if days is None:
        days = config.RETAIN_DAYS
    
    session = get_db_session()
    cutoff_date = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    
    old_episodes = (
        session.query(PodcastEpisode)
        .filter(PodcastEpisode.created_at < cutoff_date)
        .all()
    )
    
    for episode in old_episodes:
        # Remove files if they exist
        for path in [episode.audio_path, episode.transcript_path, episode.summary_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
        session.delete(episode)
    
    session.commit()
    session.close() 