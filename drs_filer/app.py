from drs_filer.ga4gh.drs.endpoints.service_info import RegisterServiceInfo
from foca.foca import foca

import logging
import os

logger = logging.getLogger(__name__)


def main():
    app = foca(
        os.path.join(
            os.path.dirname(__file__),
            "config.yaml",
        )
    )
    # register service info
    with app.app.app_context():
        service_info = RegisterServiceInfo()
        service_info.set_service_info_from_config()
    # start app

    app.run(port=app.port)


if __name__ == '__main__':
    main()
