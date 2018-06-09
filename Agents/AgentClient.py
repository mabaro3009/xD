# -*- coding: utf-8 -*-
"""
filename: SimplePersonalAgent
Antes de ejecutar hay que añadir la raiz del proyecto a la variable PYTHONPATH
Ejemplo de agente que busca en el directorio y llama al agente obtenido
Created on 09/02/2014
@author: javier
"""

from __future__ import print_function
from multiprocessing import Process
import socket
import argparse

from flask import Flask, render_template, request, redirect, url_for
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import FOAF, RDF
from rdflib import Literal, XSD
import requests

from AgentUtil.OntoNamespaces import ACL, DSO
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.ACLMessages import build_message, send_message, get_agent_info
from AgentUtil.Agent import Agent
from AgentUtil.Logging import config_logger
from AgentUtil.OntoNamespaces import ONT

__author__ = 'javier'

# Definimos los parametros de la linea de comandos
parser = argparse.ArgumentParser()
parser.add_argument('--open', help="Define si el servidor est abierto al exterior o no", action='store_true',
                    default=False)
parser.add_argument('--port', type=int, help="Puerto de comunicacion del agente")
parser.add_argument('--dhost', default=socket.gethostname(), help="Host del agente de directorio")
parser.add_argument('--dport', type=int, help="Puerto de comunicacion del agente de directorio")

# Logging
logger = config_logger(level=1)

# parsing de los parametros de la linea de comandos
args = parser.parse_args()

# Configuration stuff
if args.port is None:
    port = 9002
else:
    port = args.port

if args.open is None:
    hostname = '0.0.0.0'
else:
    hostname = socket.gethostname()

if args.dport is None:
    dport = 9000
else:
    dport = args.dport

if args.dhost is None:
    dhostname = socket.gethostname()
else:
    dhostname = args.dhost

# Flask stuff
app = Flask(__name__, template_folder='../templates')

# Configuration constants and variables
agn = Namespace("http://www.agentes.org#")

# Contador de mensajes
mss_cnt = 0

# Datos del Agente
AgentClient = Agent('AgentClient',
                       agn.AgentClient,
                       'http://%s:%d/comm' % (hostname, port),
                       'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))

# Global dsgraph triplestore
dsgraph = Graph()


def get_count():
    global mss_cnt
    if not mss_cnt:
        mss_cnt = 0
    mss_cnt += 1
    return mss_cnt

def directory_search_message(type):
    """
    Busca en el servicio de registro mandando un
    mensaje de request con una accion Seach del servicio de directorio
    Podria ser mas adecuado mandar un query-ref y una descripcion de registo
    con variables
    :param type:
    :return:
    """
    logger.info('Buscamos en el servicio de registro')

    gmess = Graph()

    gmess.bind('foaf', FOAF)
    gmess.bind('dso', DSO)
    reg_obj = agn[AgentClient.name + '-search']
    gmess.add((reg_obj, RDF.type, DSO.Search))
    gmess.add((reg_obj, DSO.AgentType, type))

    msg = build_message(gmess, perf=ACL.request,
                        sender=AgentClient.uri,
                        receiver=DirectoryAgent.uri,
                        content=reg_obj,
                        msgcnt=get_count())
    gr = send_message(msg, DirectoryAgent.address)
    logger.info('Recibimos informacion del agente')

    return gr

def infoagent_search_message(addr, ragn_uri, gmess, msgResult):
    """
    Envia una accion a un agente de informacion
    """
    logger.info('Hacemos una peticion al servicio de informacion')

    msg = build_message(gmess, perf=ACL.request,
                        sender=AgentClient.uri,
                        receiver=ragn_uri,
                        msgcnt=get_count(),
                        content=msgResult)
    gr = send_message(msg, addr)
    logger.info('Recibimos respuesta a la peticion al servicio de informacion')

    return gr


@app.route("/", methods=['GET', 'POST'])
def pagina_princiapl():
    if request.method == 'GET':
        return render_template('user_principal.html')
    else:
        return redirect(url_for('buscar'))

@app.route('/buscar', methods=['GET', 'POST'])
def buscar():
    if request.method == 'GET':
        return render_template('buscar.html')
    else:
        logger.info("Petición de búsqueda enviada")

        msgResult = ONT['Busqueda' + str(get_count())]

        gr = Graph()
        gr.add((msgResult, RDF.type, ONT.Busqueda))

        nombre = request.form['nombre']
        marca = request.form['marca']
        precio_max = request.form['precio_max']
        tipo_de_producto = request.form['tipo_de_producto']

        if nombre:
            body_nombre = ONT['restriccion_de_nombre' + str(get_count())]
            gr.add((body_nombre, RDF.type, ONT.restriccion_de_nombre))
            gr.add((body_nombre, ONT.nombre, Literal(nombre, datatype=XSD.string)))
            gr.add((body_nombre, ONT.Restringe, URIRef(body_nombre)))

        if marca:
            body_marca = ONT['restriccion_de_marca' + str(get_count())]
            gr.add((body_marca, RDF.type, ONT.restriccion_de_marca))
            gr.add((body_marca, ONT.nombre, Literal(nombre, datatype=XSD.string)))
            gr.add((body_marca, ONT.Restringe, URIRef(body_marca)))

        if tipo_de_producto:
            body_tipo_de_producto = ONT['restriccion_de_tipo_de_producto' + str(get_count())]
            gr.add((body_tipo_de_producto, RDF.type, ONT.restriccion_de_marca))
            gr.add((body_tipo_de_producto, ONT.nombre, Literal(nombre, datatype=XSD.string)))
            gr.add((body_tipo_de_producto, ONT.Restringe, URIRef(body_tipo_de_producto)))

        if precio_max:
            body_precio = ONT['restriccion_de_precio' + str(get_count())]
            gr.add((body_precio, RDF.type, ONT.restriccion_de_nombre))
            gr.add((body_precio, ONT.precio, Literal(nombre, datatype=XSD.integer)))
            gr.add((body_precio, ONT.Restringe, URIRef(body_precio)))

        grAgentBuscador = get_agent_info(agn.AgentBuscador, DirectoryAgent, AgentClient, get_count())

        gr2 = send_message(
            build_message(gr, perf=ACL.request, sender=AgentClient.uri, receiver=grAgentBuscador.uri,
                          msgcnt=get_count(),
                          content=msgResult), grAgentBuscador.address)
        logger.info('funciona :D')
        return render_template('buscar.html', name='OKKKKKK')

@app.route("/iface", methods=['GET', 'POST'])
def browser_iface():
    """
    Permite la comunicacion con el agente via un navegador
    via un formulario
    """
    if request.method == 'GET':
        return render_template('user_principal.html')
    else:
        user = request.form['username']
        mess = request.form['message']
        return render_template('user_principal.html', user=user, mess=mess)


@app.route("/Stop")
def stop():
    """
    Entrypoint que para el agente
    :return:
    """
    tidyup()
    shutdown_server()
    return "Parando Servidor"


@app.route("/comm")
def comunicacion():
    """
    Entrypoint de comunicacion del agente
    """
    return "Hola"


def tidyup():
    """
    Acciones previas a parar el agente
    """
    pass


def agentbehavior1():
    """
    Un comportamiento del agente
    :return:
    """


if __name__ == '__main__':
    # Ponemos en marcha los behaviors
    ab1 = Process(target=agentbehavior1)
    ab1.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    ab1.join()
    logger.info('The End')