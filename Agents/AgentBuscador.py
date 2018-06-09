# -*- coding: utf-8 -*-
"""
filename: SimpleInfoAgent
Antes de ejecutar hay que añadir la raiz del proyecto a la variable PYTHONPATH
Agente que se registra como agente de hoteles y espera peticiones
@author: javier
"""
from __future__ import print_function
from multiprocessing import Process, Queue
import socket
import argparse

from flask import Flask, request
from rdflib import Graph, Namespace, Literal
from rdflib.namespace import FOAF, RDF

from AgentUtil.OntoNamespaces import ACL, DSO
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.ACLMessages import build_message, send_message, get_message_properties, register_agent
from AgentUtil.Agent import Agent
from AgentUtil.Logging import config_logger
from AgentUtil.OntoNamespaces import ONT

__author__ = 'MDMa'

# Definimos los parametros de la linea de comandos
parser = argparse.ArgumentParser()
parser.add_argument('--open', help="Define si el servidor esta abierto al exterior o no", action='store_true',
                    default=False)
parser.add_argument('--port', type=int, help="Puerto de comunicacion del agente")
parser.add_argument('--dhost', default='localhost', help="Host del agente de directorio")
parser.add_argument('--dport', type=int, help="Puerto de comunicacion del agente de directorio")

# Logging
logger = config_logger(level=1)

# parsing de los parametros de la linea de comandos
args = parser.parse_args()

# Configuration stuff
if args.port is None:
    port = 9001
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
app = Flask(__name__)

# Configuration constants and variables
agn = Namespace("http://www.agentes.org#")

# Contador de mensajes
mss_cnt = 0

# Datos del Agente
AgentBuscador = Agent('AgentBuscador',
                  agn.AgentBuscador,
                  'http://%s:%d/comm' % (hostname, port),
                  'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:9000/Register' % hostname,
                       'http://%s:9000/Stop' % hostname)

# Global dsgraph triplestore
dsgraph = Graph()

# Cola de comunicacion entre procesos
cola1 = Queue()

messages_cnt = 0

def get_count():
    global messages_cnt
    messages_cnt += 1
    return messages_cnt


def register_message():
    """
    Envia un mensaje de registro al servicio de registro
    usando una performativa Request y una accion Register del
    servicio de directorio
    :param gmess:
    :return:
    """

    logger.info('Nos registramos')

    gr = register_agent(AgentBuscador, DirectoryAgent, AgentBuscador.uri, get_count())
    return gr

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
    Simplemente retorna un objeto fijo que representa una
    respuesta a una busqueda de hotel
    Asumimos que se reciben siempre acciones que se refieren a lo que puede hacer
    el agente (buscar con ciertas restricciones, reservar)
    Las acciones se mandan siempre con un Request
    Prodriamos resolver las busquedas usando una performativa de Query-ref
    """
    global dsgraph
    global mss_cnt

    logger.info('Peticion de informacion recibida')

    # Extraemos el mensaje y creamos un grafo con el
    message = request.args['content']
    gm = Graph()
    gm.parse(data=message)

    msgdic = get_message_properties(gm)

    # Comprobamos que sea un mensaje FIPA ACL
    if msgdic is None:
        # Si no es, respondemos que no hemos entendido el mensaje
        logger.info('none')
        gr = build_message(Graph(), ACL['not-understood'], sender=AgentBuscador.uri, msgcnt=mss_cnt)
    else:
        logger.info('else')
        # Obtenemos la performativa
        perf = msgdic['performative']

        if perf != ACL.request:
            logger.info('perf != acl.request')
            # Si no es un request, respondemos que no hemos entendido el mensaje
            gr = build_message(Graph(), ACL['not-understood'], sender=AgentBuscador.uri, msgcnt=mss_cnt)
        else:
            logger.info('guai')
            # Extraemos el objeto del contenido que ha de ser una accion de la ontologia de acciones del agente
            # de registro

            # Averiguamos el tipo de la accion

            content = msgdic['content']
            accion = gm.value(subject=content, predicate=RDF.type)
            # Aqui realizariamos lo que pide la accion
            # Por ahora simplemente retornamos un Inform-done
            if accion == ONT.Busqueda:
                restricciones = gm.objects(content, ONT.Restringe)
                restricciones_busqueda = {}
                for restriccion in restricciones:
                    if gm.value(subject=restriccion, predicate=RDF.type) == ONT.restriccion_de_nombre:
                        nombre = gm.value(subject=restriccion, predicate=ONT.nombre)
                        logger.info('nombre: '+ nombre)
                        restricciones_busqueda['nombre'] = nombre
                    elif gm.value(subject=restriccion, predicate=RDF.type) == ONT.restriccion_de_marca:
                        marca = gm.value(subject=restriccion, predicate=ONT.marca)
                        logger.info('marca: '+ marca)
                        restricciones_busqueda['marca'] = marca
                    elif gm.value(subject=restriccion, predicate=RDF.type) == ONT.restriccion_de_peso:
                        peso = gm.value(subject=restriccion, predicate=ONT.peso)
                        logger.info('peso: '+ peso)
                        restricciones_busqueda['marca'] = peso
                    elif gm.value(subject=restriccion, predicate=RDF.type) == ONT.restriccion_de_precio:
                        precio_max = gm.value(subject=restriccion, predicate=ONT.precio_max)
                        logger.info('precio_max: '+ precio_max)
                        restricciones_busqueda['precio_max'] = precio_max
                    gr = build_message(Graph(),
                                       ACL['inform-done'],
                                       sender=AgentBuscador.uri,
                                       msgcnt=mss_cnt,
                                       receiver=msgdic['sender'], )
    mss_cnt += 1

    logger.info('Respondemos a la peticion')

    return gr.serialize(format='xml')


def tidyup():
    """
    Acciones previas a parar el agente
    """
    global cola1
    cola1.put(0)


def agentbehavior1(cola):
    """
    Un comportamiento del agente
    :return:
    """
    # Registramos el agente
    gr = register_message()

    pass


if __name__ == '__main__':
    # Ponemos en marcha los behaviors
    ab1 = Process(target=agentbehavior1, args=(cola1,))
    ab1.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    ab1.join()
    logger.info('The End')