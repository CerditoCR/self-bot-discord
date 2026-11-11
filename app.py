"""Punto de entrada compatible para el panel de escritorio."""
from ui import window as _window

App = _window.App
run = _window.run


def __getattr__(name):
    # Conserva los atributos históricos accesibles desde ``import app``.
    return getattr(_window, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_window)))


if __name__ == '__main__':
    run()
