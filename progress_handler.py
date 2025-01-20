import sys
import threading
from typing import Union
import tqdm
import logging

logger = logging.getLogger(__name__)

class ProgressListener:
    def on_progress(self, current: Union[int, float], total: Union[int, float]):
        pass

    def on_finished(self):
        pass

class ProgressListenerHandle:
    def __init__(self, listener: ProgressListener):
        self.listener = listener
    
    def __enter__(self):
        register_thread_local_progress_listener(self.listener)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        unregister_thread_local_progress_listener(self.listener)
        if exc_type is None:
            self.listener.on_finished()

class _CustomProgressBar(tqdm.tqdm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._current = self.n

    def update(self, n):
        super().update(n)
        self._current += n
        listeners = _get_thread_local_listeners()
        for listener in listeners:
            listener.on_progress(self._current, self.total)

_thread_local = threading.local()

def _get_thread_local_listeners():
    if not hasattr(_thread_local, 'listeners'):
        _thread_local.listeners = []
    return _thread_local.listeners

_hooked = False

def init_progress_hook():
    global _hooked
    if _hooked:
        return

    # Inject into tqdm.tqdm of mlx_whisper
    import mlx_whisper
    mlx_whisper.tqdm = _CustomProgressBar
    _hooked = True

def register_thread_local_progress_listener(progress_listener: ProgressListener):
    init_progress_hook()
    listeners = _get_thread_local_listeners()
    listeners.append(progress_listener)
    
def unregister_thread_local_progress_listener(progress_listener: ProgressListener):
    listeners = _get_thread_local_listeners()
    if progress_listener in listeners:
        listeners.remove(progress_listener)

def create_progress_listener_handle(progress_listener: ProgressListener):
    return ProgressListenerHandle(progress_listener)

class DownloadProgressBar:
    def __init__(self, episode_title):
        self.episode_title = episode_title
        self.started = False
        
    def yt_dlp_hook(self, d):
        if d['status'] == 'downloading':
            if not self.started:
                self.started = True
                logger.info(f"Starting download of: {self.episode_title}")
            
            if 'total_bytes' in d and 'downloaded_bytes' in d:
                percentage = (d['downloaded_bytes'] / d['total_bytes']) * 100
                logger.info(f"Download progress for {self.episode_title}: {percentage:.1f}%")
        elif d['status'] == 'finished':
            logger.info(f"Download completed for: {self.episode_title}")
    
    def close(self):
        pass 