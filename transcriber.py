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
from pydub import AudioSegment
import tempfile

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
        self.max_file_size = 24 * 1024 * 1024  # 24MB to be safe (API limit is 25MB)

    def _calculate_chunk_duration(self, audio: AudioSegment, target_size: int, bitrate: str = "64k") -> int:
        """Calculate chunk duration in milliseconds based on target file size and bitrate."""
        # Convert bitrate string to bits per second
        bitrate_value = int(bitrate.replace('k', '')) * 1024
        # Calculate bytes per millisecond
        bytes_per_ms = bitrate_value / 8 / 1000
        # Calculate duration that would result in target size
        target_duration = target_size / bytes_per_ms
        # Round down to nearest second and convert to ms
        return int(target_duration / 1000) * 1000

    def _split_audio(self, audio_path: str) -> list[str]:
        """Split audio file into chunks smaller than max_file_size."""
        audio = AudioSegment.from_file(audio_path)
        chunks = []
        
        # Create temporary directory for chunks
        temp_dir = tempfile.mkdtemp()
        
        # First try with 64k bitrate
        bitrate = "64k"
        chunk_duration = self._calculate_chunk_duration(audio, self.max_file_size, bitrate)
        
        # If chunk duration is too small, try with 32k bitrate
        if chunk_duration < 60000:  # Less than 1 minute
            bitrate = "32k"
            chunk_duration = self._calculate_chunk_duration(audio, self.max_file_size, bitrate)
            logger.info(f"Using lower bitrate ({bitrate}) for smaller file size")
        
        logger.info(f"Splitting audio into chunks of {chunk_duration/1000:.1f} seconds with {bitrate} bitrate")
        
        # Split audio into chunks
        for i, start in enumerate(range(0, len(audio), chunk_duration)):
            chunk = audio[start:start + chunk_duration]
            chunk_path = os.path.join(temp_dir, f"chunk_{i}.mp3")
            
            # Export with calculated bitrate
            chunk.export(chunk_path, format="mp3", bitrate=bitrate)
            
            # Verify file size
            if os.path.getsize(chunk_path) > self.max_file_size:
                logger.warning(f"Chunk {i} is still too large, trying with lower bitrate")
                # If still too large, try with even lower bitrate
                chunk.export(chunk_path, format="mp3", bitrate="32k")
                
                # If still too large after 32k, raise an error
                if os.path.getsize(chunk_path) > self.max_file_size:
                    raise ValueError(f"Unable to reduce chunk {i} to acceptable size even with 32k bitrate")
            
            chunks.append(chunk_path)
            logger.info(f"Created chunk {i+1} with size {os.path.getsize(chunk_path)/1024/1024:.1f}MB")
        
        return chunks

    def transcribe_audio(self, audio_path: str, progress_listener: Optional[ProgressListener] = None) -> str:
        try:
            # Check if file is too large
            if os.path.getsize(audio_path) > self.max_file_size:
                logger.info(f"File {audio_path} is too large, splitting into chunks...")
                chunk_paths = self._split_audio(audio_path)
                transcripts = []
                
                for i, chunk_path in enumerate(chunk_paths):
                    try:
                        with open(chunk_path, "rb") as audio_file:
                            response = self.client.audio.transcriptions.create(
                                model="whisper-1",
                                file=audio_file
                            )
                            transcripts.append(response.text)
                            
                            # Update progress
                            if progress_listener:
                                progress_listener.on_progress(i + 1, len(chunk_paths))
                    except Exception as e:
                        logger.error(f"Failed to transcribe chunk {i}: {e}")
                    finally:
                        # Clean up chunk file
                        try:
                            os.remove(chunk_path)
                        except:
                            pass
                
                # Clean up temp directory
                try:
                    os.rmdir(os.path.dirname(chunk_paths[0]))
                except:
                    pass
                
                return " ".join(transcripts)
            else:
                # Original code for files under size limit
                with open(audio_path, "rb") as audio_file:
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