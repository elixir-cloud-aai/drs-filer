"""Main app module."""

import logging

from foca.foca import foca

from drs_filer.ga4gh.drs.endpoints.service_info import RegisterServiceInfo

logger = logging.getLogger(__name__)


def main():
    app = foca("config.yaml")

    # register service info
    with app.app.app_context():
        service_info = RegisterServiceInfo()
        service_info.set_service_info_from_config()
    # start app
    app.run(port=app.port)


if __name__ == '__main__':
    main()
