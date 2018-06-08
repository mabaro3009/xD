

__author__ = 'MDMa'

from flask import request


def shutdown_server():
    """
    Funcion que para el servidor web

    :raise RuntimeError:
    """
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()


