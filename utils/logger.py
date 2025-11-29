import json
import os
import logging
import logging.config
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Форматтер, сериализующий LogRecord в JSON для Loki/Promtail."""
    def formatTime(self, record, datefmt=None):
        return datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()

    def format(self, record: logging.LogRecord) -> str:
        # текст сообщения (учтёт %s, .format и т.д.)
        message = record.getMessage()
        payload = {
            "ts": self.formatTime(record),     # UTC ISO-8601
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "line": record.lineno,
            "msg": message,
        }
        # добавим поля из record.__dict__ (в т.ч. extra=...)
        for k, v in record.__dict__.items():
            if k in payload or k.startswith("_"):
                continue
            if k in (
                "msg", "args", "levelno", "levelname", "name", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process"
            ):
                continue
            payload[k] = v

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        # default=str — чтобы внезапные объекты не ломали сериализацию
        return json.dumps(payload, ensure_ascii=False, default=str)


class ContextFilter(logging.Filter):
    """
    Универсальный фильтр: добавляет стабильные поля service/env
    (низкая кардинальность — пригодно для labels в Loki).
    """
    def __init__(self, service: str | None = None, env: str | None = None):
        super().__init__()
        self.service = service or os.getenv("SERVICE_NAME", "trading-bot")
        self.env = env or os.getenv("ENV", "prod")

    def filter(self, record: logging.LogRecord) -> bool:
        setattr(record, "service", self.service)
        setattr(record, "env", self.env)
        return True


def setup_logging_from_dict(config: dict) -> None:
    logging_cfg = config.get("logging")
    if not logging_cfg:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(name)s | %(asctime)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        return

    file_handler = logging_cfg["handlers"].get("file")
    if file_handler:
        fname = file_handler.get("filename")
        if fname:
            os.makedirs(os.path.dirname(fname), exist_ok=True)

    logging.config.dictConfig(logging_cfg)


def get_logger(name: str | None = None) -> logging.Logger:
    return logging.getLogger(name or __name__)
