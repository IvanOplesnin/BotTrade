import os
import logging
import logging.config


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
