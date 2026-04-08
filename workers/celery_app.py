from celery import Celery
from core.config import settings

app = Celery("metacleaner")
app.config_from_object({
    "broker_url": settings.celery_broker_url,
    "result_backend": settings.celery_result_backend,
    "task_serializer": "json", "result_serializer": "json",
    "accept_content": ["json"], "enable_utc": True, "timezone": "UTC",
    "task_routes": {
        "workers.video_processor.process_video_task": {"queue": "video"},
        "workers.downloader.download_youtube_task":   {"queue": "video"},
        "workers.sender.send_result_task":            {"queue": "video"},
        "workers.sender.notify_failure_task":         {"queue": "video"},
        "workers.cleanup.cleanup_job_files_task":     {"queue": "cleanup"},
        "workers.cleanup.periodic_cleanup_task":      {"queue": "cleanup"},
        "workers.broadcast.send_broadcast_chunk_task":{"queue": "broadcast"},
        "workers.downloader_only.download_only_task": {"queue": "video"},
    },
    "task_default_queue": "video",
    "task_acks_late": True,
    "task_reject_on_worker_lost": True,
    "result_expires": 3600,
    "task_soft_time_limit": 600,
    "task_time_limit": 720,
    "beat_schedule": {
        "periodic-cleanup": {
            "task": "workers.cleanup.periodic_cleanup_task",
            "schedule": 60.0 * 15,
        },
    },
})
app.autodiscover_tasks(["workers.video_processor","workers.downloader",
                        "workers.sender","workers.cleanup","workers.broadcast",
                        "workers.downloader_only"])
