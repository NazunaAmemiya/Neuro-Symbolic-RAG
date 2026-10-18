import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)-15s - %(levelname)-8s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("logger.txt", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)
