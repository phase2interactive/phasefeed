from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import datetime
import config
import os

engine = create_engine(f"sqlite:///{config.DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Show(Base):
    __tablename__ = "shows"

    id = Column(Integer, primary_key=True, index=True)
    feed_url = Column(String, unique=True, index=True)
    title = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationship to episodes
    episodes = relationship("PodcastEpisode", back_populates="show", cascade="all, delete-orphan")

class PodcastEpisode(Base):
    __tablename__ = "episodes"

    id = Column(Integer, primary_key=True, index=True)
    show_id = Column(Integer, ForeignKey('shows.id', ondelete='CASCADE'), nullable=False)
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

    # Relationship to show
    show = relationship("Show", back_populates="episodes")

class EpisodeContent(Base):
    __tablename__ = "episode_content"

    id = Column(Integer, primary_key=True, index=True)
    episode_id = Column(Integer, ForeignKey('episodes.id', ondelete='CASCADE'), nullable=False)
    formatted_date = Column(String)
    duration_formatted = Column(String)
    size_formatted = Column(String)
    summary = Column(Text)
    audio_url = Column(String)
    last_updated = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationship to parent episode
    episode = relationship("PodcastEpisode", backref="content")

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

def update_episode_content(session, episode):
    """Update or create content entry for an episode."""
    content = (
        session.query(EpisodeContent)
        .filter(EpisodeContent.episode_id == episode.id)
        .first()
    )
    
    if not content:
        content = EpisodeContent(episode_id=episode.id)
        session.add(content)
    
    # Format date
    content.formatted_date = episode.pub_date.strftime('%B %d, %Y') if episode.pub_date else 'Unknown date'
    
    # Format duration
    if episode.duration:
        minutes = episode.duration // 60
        seconds = episode.duration % 60
        content.duration_formatted = f"{minutes}m {seconds}s"
    else:
        content.duration_formatted = 'Unknown duration'
    
    # Format file size
    if episode.file_size:
        mb_size = episode.file_size / (1024 * 1024)
        content.size_formatted = f"{mb_size:.1f} MB"
    else:
        content.size_formatted = 'Unknown size'
    
    # Load summary if available
    if episode.summary_path and os.path.exists(episode.summary_path):
        with open(episode.summary_path, 'r') as f:
            content.summary = f.read()
    else:
        content.summary = 'Summary not available'
    
    # Create audio URL
    if episode.audio_path and os.path.exists(episode.audio_path):
        content.audio_url = f"/audio/{os.path.basename(episode.audio_path)}"
    else:
        content.audio_url = None
    
    content.last_updated = datetime.datetime.utcnow()
    session.commit() 