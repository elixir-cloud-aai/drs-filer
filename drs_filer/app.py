import logging
import os

from foca.foca import foca

logger = logging.getLogger(__name__)


def main():
    app = foca(
        os.path.join(
            os.path.dirname(__file__),
            "config.yaml",
        )
    )
    logger.warning(f"App config: {app.app.config}")
    logger.warning(f"FOCA config: {app.app.config['FOCA']}")
    app.run(port=app.port)


if __name__ == '__main__':
    main()
