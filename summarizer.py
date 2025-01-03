import os
import logging
from ollama import Client
from database import PodcastEpisode, get_db_session, update_episode_content
import config
import openai
from abc import ABC, abstractmethod

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Common prompt template for summarization
SUMMARY_PROMPT_TEMPLATE = """
Focus on:
1. Main points discussed
2. Key information
3. Important quotes or moments

Follow these rules:
- Use bullet points when appropriate
- Be sure to include ALL relevant information discussed
- Do not leave out any important information
- Use markdown formatting with headers and subheaders and lists
- Follow markdownbest practices for formatting the content.
            
Follow this format:
## Main Topic
Brief summary of the main topic.
- Key points
- Key quotes
- Key moments
- Key takeaways

{additional_instructions}

{content_type}: {content}

Summary:"""

class BaseSummarizer(ABC):
    @abstractmethod
    def generate_summary(self, text: str, podcast_name: str, episode_title: str, is_chunk: bool = False) -> str:
        """Generate a summary of the given text."""
        pass

    @abstractmethod
    def combine_chunk_summaries(self, chunk_summaries: list[str], metadata: dict) -> str:
        """Combine multiple chunk summaries into a final summary."""
        pass

class LocalOllamaSummarizer(BaseSummarizer):
    def __init__(self):
        self.client = Client(host=config.OLLAMA_URL)

    def generate_summary(self, text: str, podcast_name: str, episode_title: str, is_chunk: bool = False) -> str:
        if is_chunk:
            additional_instructions = """
            Keep in mind that the summary from this section will be combined with summaries from other sections of the podcast. 
            That aggregate conent will be used to generate a final summary."""
            content_type = f"Transcript section from the podcast '{podcast_name}', episode '{episode_title}'"
        else:
            additional_instructions = "Provide a concise summary."
            content_type = f"Full transcript from the podcast '{podcast_name}', episode '{episode_title}'"

        prompt = SUMMARY_PROMPT_TEMPLATE.format(
            additional_instructions=additional_instructions,
            content_type=content_type,
            content=text
        )

        try:
            response = self.client.generate(
                model=config.OLLAMA_MODEL,
                prompt=prompt,
                stream=False
            )
            return response['response']
        except Exception as e:
            logger.error(f"Error calling Ollama API: {e}")
            return None

    def combine_chunk_summaries(self, chunk_summaries: list[str], metadata: dict) -> str:
        combined_text = "\n\n".join(chunk_summaries)
        
        prompt = SUMMARY_PROMPT_TEMPLATE.format(
            additional_instructions="Create a coherent final summary that combines these sections.",
            content_type="Individual section summaries from a podcast episode",
            content=combined_text
        )

        try:
            response = self.client.generate(
                model=config.OLLAMA_MODEL,
                prompt=prompt,
                stream=False
            )
            return response['response']
        except Exception as e:
            logger.error(f"Error calling Ollama API when combining summaries: {e}")
            return None

class OpenAISummarizer(BaseSummarizer):
    def __init__(self):
        self.client = openai.OpenAI()

    def generate_summary(self, text: str, podcast_name: str, episode_title: str, is_chunk: bool = False) -> str:
        if is_chunk:
            system_prompt = "You are a podcast summarization assistant. Provide clear, concise summaries focusing on main points, key information, and important quotes."
            content_type = f"section of a transcript from the podcast '{podcast_name}', episode '{episode_title}'"
        else:
            system_prompt = "You are a podcast summarization assistant. Provide comprehensive episode summaries focusing on main topics, key takeaways, and important moments."
            content_type = f"full transcript from the podcast '{podcast_name}', episode '{episode_title}'"

        prompt = SUMMARY_PROMPT_TEMPLATE.format(
            additional_instructions="",
            content_type=content_type,
            content=text
        )

        try:
            response = self.client.chat.completions.create(
                model=config.OPENAI_SUMMARY_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            return None

    def combine_chunk_summaries(self, chunk_summaries: list[str], metadata: dict) -> str:
        combined_text = "\n\n".join(chunk_summaries)
        
        system_prompt = "You are a podcast summarization assistant. Create unified, coherent summaries from multiple section summaries."
        prompt = SUMMARY_PROMPT_TEMPLATE.format(
            additional_instructions="Create a unified summary that combines these sections.",
            content_type="section summaries from a podcast episode",
            content=combined_text
        )

        try:
            response = self.client.chat.completions.create(
                model=config.OPENAI_SUMMARY_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error calling OpenAI API when combining summaries: {e}")
            return None

def get_summarizer() -> BaseSummarizer:
    """Factory function to get the appropriate summarizer based on configuration."""
    if config.SUMMARIZATION_MODE == "local":
        return LocalOllamaSummarizer()
    elif config.SUMMARIZATION_MODE == "openai":
        return OpenAISummarizer()
    else:
        raise ValueError(f"Invalid summarization mode: {config.SUMMARIZATION_MODE}")

def chunk_text(text, chunk_size=config.TRANSCRIPT_CHUNK_SIZE, overlap=config.TRANSCRIPT_CHUNK_OVERLAP):
    """Split text into overlapping chunks of approximately chunk_size characters.
    
    Args:
        text (str): The text to split
        chunk_size (int): Target size of each chunk in characters
        overlap (int): Number of characters to overlap between chunks
        
    Returns:
        list[str]: List of text chunks
    """
    # Split into sentences (roughly) by splitting on periods followed by whitespace
    sentences = [s.strip() + '.' for s in text.split('. ')]
    chunks = []
    current_chunk = []
    current_size = 0
    
    for sentence in sentences:
        sentence_size = len(sentence)
        
        if current_size + sentence_size > chunk_size and current_chunk:
            # Store the chunk
            chunks.append(' '.join(current_chunk))
            # Keep last few sentences for overlap
            overlap_text = ' '.join(current_chunk[-3:])  # Keep ~3 sentences for context
            current_chunk = [overlap_text, sentence]
            current_size = len(overlap_text) + sentence_size
        else:
            current_chunk.append(sentence)
            current_size += sentence_size
    
    # Add the last chunk if there is one
    if current_chunk:
        chunks.append(' '.join(current_chunk))
    
    return chunks

def summarize_episodes():
    """Find all transcribed but not summarized episodes and generate summaries."""
    session = get_db_session()
    episodes = (
        session.query(PodcastEpisode)
        .filter_by(transcribed=True, summarized=False)
        .all()
    )

    summarizer = get_summarizer()

    for ep in episodes:
        if not ep.transcript_path or not os.path.exists(ep.transcript_path):
            logger.error(f"Transcript not found for {ep.episode_title}")
            continue

        try:
            logger.info(f"Summarizing {ep.episode_title}...")
            
            # Read transcript
            with open(ep.transcript_path, "r", encoding="utf-8") as f:
                transcript_text = f.read()
            
            # Extract just the transcript part (after "Transcript:" line)
            transcript_parts = transcript_text.split("Transcript:")
            if len(transcript_parts) > 1:
                transcript_text = transcript_parts[1].strip()
            
            # Check if transcript is long enough to need chunking
            if len(transcript_text) > config.TRANSCRIPT_CHUNK_SIZE:
                logger.info(f"Transcript is long ({len(transcript_text)} chars), processing in chunks...")
                
                # Split into chunks and summarize each
                chunks = chunk_text(transcript_text)
                chunk_summaries = []
                
                for i, chunk in enumerate(chunks, 1):
                    logger.info(f"Processing chunk {i} of {len(chunks)}...")
                    chunk_summary = summarizer.generate_summary(chunk, ep.show.title, ep.episode_title, is_chunk=True)
                    if chunk_summary:
                        chunk_summaries.append(chunk_summary)
                
                if not chunk_summaries:
                    logger.error("Failed to generate any chunk summaries")
                    continue
                
                # Combine chunk summaries
                metadata = {
                    'title': ep.episode_title,
                    'podcast': ep.show.title,
                    'date': ep.pub_date,
                    'duration': ep.duration
                }
                summary = summarizer.combine_chunk_summaries(chunk_summaries, metadata)
            else:
                # For shorter transcripts, summarize directly
                summary = summarizer.generate_summary(transcript_text, ep.show.title, ep.episode_title)
                if summary:
                    summary = summary.strip()
            
            if not summary:
                continue
                
            # Save summary to file
            safe_filename = "".join([c for c in ep.episode_title if c.isalpha() or c.isdigit() or c in ' ._-']).rstrip()
            summary_path = os.path.join(
                config.TRANSCRIPT_STORAGE_PATH,
                f"{ep.show.title}_{safe_filename}_summary.txt"
            )
            
            with open(summary_path, "w", encoding="utf-8") as f:
                f.write(summary)
            
            # Update database
            ep.summary_path = summary_path
            ep.summarized = True
            
            # Update episode_content
            update_episode_content(session, ep)
            
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