import logging

FORMAT = (
    "%(name)-25s | %(asctime)s | "
    "%(module)-15s | line:%(lineno)4d | %(levelname)-8s | "
    "%(message)s"
)
formatter = logging.Formatter(FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
stream_handler.setLevel(logging.DEBUG)

file_handler = logging.FileHandler("logs.log")
file_handler.setFormatter(formatter)
file_handler.setLevel(logging.DEBUG)

logging.basicConfig(level=logging.DEBUG, handlers=[stream_handler, file_handler])
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("grpc").setLevel(logging.WARNING)

def get_logger(name=None) -> logging.Logger:
    if name is None:
        name = __name__
    logger = logging.getLogger(name)
    return logger
