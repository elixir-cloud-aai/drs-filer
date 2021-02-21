import logging

from foca.foca import foca

logger = logging.getLogger(__name__)


def main():
    app = foca("config.yaml")
    app.run(port=app.port)


if __name__ == '__main__':
    main()
