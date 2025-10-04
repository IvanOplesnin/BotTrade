import logging
from logging.handlers import RotatingFileHandler

FORMAT = (
    "%(name)-15s | %(asctime)s | "
    "%(module)-15s | line:%(lineno)4d | %(levelname)-8s | "
    "%(message)s"
)
formatter = logging.Formatter(FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
stream_handler.setLevel(logging.DEBUG)

file_handler = RotatingFileHandler(
    'logs/logs.log', mode='a', maxBytes=10 * 1024 * 1024, backupCount=15
)
file_handler.setFormatter(formatter)
file_handler.setLevel(logging.DEBUG)

logging.basicConfig(level=logging.DEBUG, handlers=[stream_handler, file_handler])
logger = logging.getLogger(__name__)
