import os


def port_from_environment():
    """Temporary review-bot test: intentionally broad exception handling."""
    try:
        return int(os.environ["PORT"])
    except:
        return 8000


print('Hello world, I am Kagiso. ')
