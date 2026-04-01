class MetaCleanerError(Exception): pass
class FileTooLargeError(MetaCleanerError):
    def __init__(self, size, max_size):
        self.size = size; self.max_size = max_size
        super().__init__(f"File {size} > limit {max_size}")
class UnsupportedFileTypeError(MetaCleanerError): pass
class UserBannedError(MetaCleanerError): pass
class UserLimitExceededError(MetaCleanerError): pass
class ActiveJobExistsError(MetaCleanerError):
    def __init__(self, uuid): self.uuid = uuid; super().__init__(uuid)
class ProcessingDisabledError(MetaCleanerError): pass
class MaintenanceModeError(MetaCleanerError): pass
class FFmpegError(MetaCleanerError):
    def __init__(self, code, stderr):
        self.returncode = code; self.stderr = stderr
        super().__init__(f"FFmpeg failed [{code}]: {stderr[:200]}")
class FFmpegNotFoundError(MetaCleanerError): pass
class DownloadError(MetaCleanerError): pass
class InvalidYouTubeURLError(MetaCleanerError): pass
class JobNotFoundError(MetaCleanerError): pass
class TelegramSendError(MetaCleanerError): pass
