# Fix for Knos relay log issue #17
import logging

logger = logging.getLogger('Knos.Relay')

def patch_relay_logging():
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('[%(asctime)s] %(levelname)s [%(name)s]: %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    logger.info('Relay logging initialized successfully via patch #17')

if __name__ == '__main__':
    patch_relay_logging()