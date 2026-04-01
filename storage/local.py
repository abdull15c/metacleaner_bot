from pathlib import Path
from core.config import settings


class LocalStorage:
    def __init__(self):
        self.up = settings.temp_upload_dir
        self.pr = settings.temp_processed_dir

    def temp_file_count(self):
        return sum(1 for d in [self.up, self.pr] if d.exists() for f in d.iterdir() if f.is_file())

    def temp_total_size_mb(self):
        total = sum(f.stat().st_size for d in [self.up, self.pr] if d.exists() for f in d.iterdir() if f.is_file())
        return round(total / 1048576, 2)


storage = LocalStorage()
