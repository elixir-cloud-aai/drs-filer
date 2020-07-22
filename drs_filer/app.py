from foca.foca import foca


def init():
    if __name__ == '__main__':
        app = foca("config.yaml")
        app.run(port=app.port)


init()
