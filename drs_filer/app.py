from drs_filer.config.app_config import parse_app_config
from drs_filer.factories.connexion_app import create_connexion_app
from drs_filer.database.register_mongodb import register_mongodb
from drs_filer.errors.errors import register_error_handlers
from drs_filer.security.cors import enable_cors

from foca.config.log_config import configure_logging
from foca.config.config_parser import get_conf


def run_server():

    # Configure logger
    configure_logging(config_var='WES_CONFIG_LOG')

    # Parse app configuration
    config = parse_app_config(config_var='WES_CONFIG')

    # Create Connexion app
    connexion_app = create_connexion_app(config)

    # Register MongoDB
    connexion_app.app = register_mongodb(connexion_app.app)

    # Register error handlers
    connexion_app = register_error_handlers(connexion_app)

    # TODO: Register OpenAPI specs

    # Enable cross-origin resource sharing
    enable_cors(connexion_app.app)

    return connexion_app, config


if __name__ == '__main__':
    connexion_app, config = run_server()
    # Run app
    connexion_app.run(
        use_reloader=get_conf(config, 'server', 'use_reloader')
    )
