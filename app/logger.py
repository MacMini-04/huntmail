import logging

# Logging configuration
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')

# Create a logger
logger = logging.getLogger('app_logger')

if __name__ == '__main__':
    logger.info('Logger is configured and ready to use.')