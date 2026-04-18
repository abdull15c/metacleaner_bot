"""
Мониторинг и алерты для MetaCleaner Bot.
Интеграция с различными системами мониторинга.
"""
import logging
import os
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class AlertManager:
    """Менеджер алертов для критических событий."""
    
    def __init__(self):
        self.sentry_enabled = False
        self.webhook_url = os.getenv("ALERT_WEBHOOK_URL")
        
        # Инициализация Sentry если доступен
        try:
            import sentry_sdk
            sentry_dsn = os.getenv("SENTRY_DSN")
            if sentry_dsn:
                sentry_sdk.init(
                    dsn=sentry_dsn,
                    traces_sample_rate=0.1,
                    profiles_sample_rate=0.1,
                    environment=os.getenv("ENVIRONMENT", "production"),
                )
                self.sentry_enabled = True
                logger.info("Sentry monitoring enabled")
        except ImportError:
            logger.warning("Sentry SDK not installed. Install: pip install sentry-sdk")
    
    async def send_alert(self, level: str, message: str, context: dict = None):
        """
        Отправка алерта в различные системы.
        
        Args:
            level: critical, error, warning, info
            message: Текст сообщения
            context: Дополнительный контекст
        """
        context = context or {}
        
        # Логирование
        log_func = getattr(logger, level.lower(), logger.info)
        log_func(f"ALERT [{level.upper()}]: {message}", extra=context)
        
        # Sentry для критических ошибок
        if self.sentry_enabled and level in ("critical", "error"):
            try:
                import sentry_sdk
                with sentry_sdk.push_scope() as scope:
                    for key, value in context.items():
                        scope.set_extra(key, value)
                    scope.set_level(level)
                    sentry_sdk.capture_message(message)
            except Exception as e:
                logger.error(f"Failed to send Sentry alert: {e}")
        
        # Webhook для критических событий
        if self.webhook_url and level == "critical":
            await self._send_webhook(message, context)
    
    async def _send_webhook(self, message: str, context: dict):
        """Отправка webhook уведомления."""
        try:
            import httpx
            payload = {
                "timestamp": datetime.utcnow().isoformat(),
                "level": "critical",
                "message": message,
                "context": context,
                "service": "metacleaner_bot"
            }
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(self.webhook_url, json=payload)
        except Exception as e:
            logger.error(f"Failed to send webhook alert: {e}")


# Глобальный экземпляр
alert_manager = AlertManager()


async def alert_critical(message: str, **context):
    """Критический алерт."""
    await alert_manager.send_alert("critical", message, context)


async def alert_error(message: str, **context):
    """Алерт об ошибке."""
    await alert_manager.send_alert("error", message, context)


async def alert_warning(message: str, **context):
    """Предупреждение."""
    await alert_manager.send_alert("warning", message, context)


async def alert_info(message: str, **context):
    """Информационное сообщение."""
    await alert_manager.send_alert("info", message, context)


# Метрики для Prometheus (уже есть instrumentator в admin/main.py)
class MetricsCollector:
    """Сборщик метрик для мониторинга."""
    
    def __init__(self):
        self.enabled = False
        try:
            from prometheus_client import Counter, Gauge, Histogram
            
            # Счетчики
            self.jobs_total = Counter(
                'metacleaner_jobs_total',
                'Total number of jobs',
                ['status', 'source_type']
            )
            
            self.errors_total = Counter(
                'metacleaner_errors_total',
                'Total number of errors',
                ['error_type']
            )
            
            # Gauges
            self.active_jobs = Gauge(
                'metacleaner_active_jobs',
                'Number of active jobs'
            )
            
            self.disk_usage_percent = Gauge(
                'metacleaner_disk_usage_percent',
                'Disk usage percentage'
            )
            
            self.temp_files_size_mb = Gauge(
                'metacleaner_temp_files_size_mb',
                'Total size of temp files in MB'
            )
            
            # Histograms
            self.job_duration_seconds = Histogram(
                'metacleaner_job_duration_seconds',
                'Job processing duration',
                ['job_action']
            )
            
            self.enabled = True
            logger.info("Prometheus metrics enabled")
            
        except ImportError:
            logger.warning("Prometheus client not installed. Install: pip install prometheus-client")
    
    def record_job_completed(self, status: str, source_type: str):
        """Записать завершение задачи."""
        if self.enabled:
            self.jobs_total.labels(status=status, source_type=source_type).inc()
    
    def record_error(self, error_type: str):
        """Записать ошибку."""
        if self.enabled:
            self.errors_total.labels(error_type=error_type).inc()
    
    def update_active_jobs(self, count: int):
        """Обновить количество активных задач."""
        if self.enabled:
            self.active_jobs.set(count)
    
    def update_disk_usage(self, percent: float):
        """Обновить использование диска."""
        if self.enabled:
            self.disk_usage_percent.set(percent)
    
    def update_temp_size(self, size_mb: float):
        """Обновить размер temp файлов."""
        if self.enabled:
            self.temp_files_size_mb.set(size_mb)
    
    def record_job_duration(self, action: str, duration: float):
        """Записать длительность обработки."""
        if self.enabled:
            self.job_duration_seconds.labels(job_action=action).observe(duration)


# Глобальный экземпляр
metrics = MetricsCollector()
