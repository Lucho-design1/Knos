import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('knos_relay')

def fix_relay_log_formatting(log_payload):
    if not isinstance(log_payload, dict):
        logger.error('Invalid payload format for relay log')
        return False
    logger.info('Relay log processed successfully: %s', log_payload.get('event', 'unknown'))
    return True
