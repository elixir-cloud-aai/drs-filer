import os

from foca.foca import foca


def init():
    if __name__ == '__main__':
        app = foca(
            os.path.join(
                os.path.dirname(__file__),
                "config.yaml",
            )
        )
        app.run(port=app.port)


init()
