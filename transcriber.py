import os
import mlx_whisper
import logging
from abc import ABC, abstractmethod
from typing import Optional
import openai
from database import PodcastEpisode, get_db_session
import config
from tqdm import tqdm
from progress_handler import ProgressListener, create_progress_listener_handle

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TranscriptionProgressListener(ProgressListener):
    def __init__(self, episode_title: str):
        self.episode_title = episode_title
        self.pbar = None

    def on_progress(self, current: float, total: float):
        if self.pbar is None:
            self.pbar = tqdm(total=total, desc=f"Transcribing {self.episode_title}", leave=False)
        self.pbar.n = current
        self.pbar.refresh()

    def on_finished(self):
        if self.pbar:
            self.pbar.close()

class BaseTranscriber(ABC):
    @abstractmethod
    def transcribe_audio(self, audio_path: str, progress_listener: Optional[ProgressListener] = None) -> str:
        """Transcribe audio file to text."""
        pass

class LocalWhisperTranscriber(BaseTranscriber):
    def __init__(self, model_path: str = config.WHISPER_MODEL):
        self.model_path = model_path

    def transcribe_audio(self, audio_path: str, progress_listener: Optional[ProgressListener] = None) -> str:
        with create_progress_listener_handle(progress_listener) if progress_listener else nullcontext():
            result = mlx_whisper.transcribe(
                audio_path,
                path_or_hf_repo=self.model_path
            )
        return result["text"]

class OpenAIWhisperTranscriber(BaseTranscriber):
    def __init__(self):
        self.client = openai.OpenAI()  # OpenAI will automatically use OPENAI_API_KEY from env

    def transcribe_audio(self, audio_path: str, progress_listener: Optional[ProgressListener] = None) -> str:
        try:
            with open(audio_path, "rb") as audio_file:
                # Note: OpenAI API doesn't support progress updates
                response = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file
                )
            return response.text
        except Exception as e:
            logger.error(f"OpenAI transcription failed: {e}")
            raise

class TranscriptionService:
    def __init__(self, transcriber: BaseTranscriber):
        self.transcriber = transcriber

    def ensure_transcript_dir(self):
        """Ensure transcript directory exists."""
        os.makedirs(config.TRANSCRIPT_STORAGE_PATH, exist_ok=True)

    def transcribe_episodes(self):
        """Find all downloaded but not transcribed episodes and generate transcripts."""
        session = get_db_session()
        episodes = (
            session.query(PodcastEpisode)
            .filter_by(downloaded=True, transcribed=False)
            .all()
        )

        for ep in tqdm(episodes, desc="Processing episodes", unit="episode"):
            if not ep.audio_path or not os.path.exists(ep.audio_path):
                logger.error(f"Audio file not found for {ep.episode_title}")
                continue

            try:
                logger.info(f"Starting transcription of {ep.episode_title}...")
                
                # Ensure transcript directory exists
                self.ensure_transcript_dir()
                
                # Generate transcript with progress tracking
                progress_listener = TranscriptionProgressListener(ep.episode_title)
                transcript = self.transcriber.transcribe_audio(ep.audio_path, progress_listener)
                
                # Format transcript with metadata
                transcript_text = f"""Title: {ep.episode_title}
Podcast: {ep.podcast_title}
Date: {ep.pub_date}
Duration: {ep.duration} seconds

Transcript:
{transcript}
"""
                
                # Save transcript
                safe_filename = "".join([c for c in ep.episode_title if c.isalpha() or c.isdigit() or c in ' ._-']).rstrip()
                transcript_path = os.path.join(
                    config.TRANSCRIPT_STORAGE_PATH,
                    f"{ep.podcast_title}_{safe_filename}.txt"
                )
                
                with open(transcript_path, "w", encoding="utf-8") as f:
                    f.write(transcript_text)
                
                # Update database
                ep.transcript_path = transcript_path
                ep.transcribed = True
                session.commit()
                
                logger.info(f"Successfully transcribed: {ep.episode_title}")
                
            except Exception as e:
                logger.error(f"Failed to transcribe {ep.episode_title}: {e}")
                continue

        session.close()

    def get_transcript(self, episode_id):
        """Retrieve transcript for a specific episode."""
        session = get_db_session()
        episode = session.query(PodcastEpisode).filter_by(id=episode_id).first()
        
        if not episode or not episode.transcript_path:
            return None
            
        try:
            with open(episode.transcript_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading transcript for episode {episode_id}: {e}")
            return None
        finally:
            session.close()

# Context manager for null progress listener
from contextlib import contextmanager

@contextmanager
def nullcontext():
    yield 