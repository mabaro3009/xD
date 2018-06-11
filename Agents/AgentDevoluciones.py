# -*- coding: utf-8 -*-
"""
filename: SimpleInfoAgent
Antes de ejecutar hay que añadir la raiz del proyecto a la variable PYTHONPATH
Agente que se registra como agente de hoteles y espera peticiones
@author: javier
"""
from __future__ import print_function

import sys
from multiprocessing import Process, Queue
import socket
import argparse

from flask import Flask, request
from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import FOAF, RDF, XSD

from AgentUtil.OntoNamespaces import ACL, DSO
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.ACLMessages import build_message, send_message, get_message_properties, register_agent, get_agent_info
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
    port = 9023
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
AgentDevoluciones = Agent('AgentDevoluciones',
                          agn.AgentDevoluciones,
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
    global mss_cnt
    if not mss_cnt:
        mss_cnt = 0
    mss_cnt += 1
    return mss_cnt


def register_message():
    """
    Envia un mensaje de registro al servicio de registro
    usando una performativa Request y una accion Register del
    servicio de directorio
    :param gmess:
    :return:
    """

    logger.info('Nos registramos')

    gr = register_agent(AgentDevoluciones, DirectoryAgent, AgentDevoluciones.uri, get_count())
    return gr


def infoagent_search_message(addr, ragn_uri, gmess, msgResult):
    """
    Envia una accion a un agente de informacion
    """
    logger.info('Hacemos una peticion al servicio de informacion')

    msg = build_message(gmess, perf=ACL.request,
                        sender=AgentDevoluciones.uri,
                        receiver=ragn_uri,
                        msgcnt=get_count(),
                        content=msgResult)
    gr = send_message(msg, addr)
    logger.info('Recibimos respuesta a la peticion al servicio de informacion')

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
        gr = build_message(Graph(), ACL['not-understood'], sender=AgentDevoluciones.uri, msgcnt=mss_cnt)
    else:
        # Obtenemos la performativa
        perf = msgdic['performative']

        if perf != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            gr = build_message(Graph(), ACL['not-understood'], sender=AgentDevoluciones.uri, msgcnt=mss_cnt)
        else:
            # Extraemos el objeto del contenido que ha de ser una accion de la ontologia de acciones del agente
            # de registro

            # Averiguamos el tipo de la accion
            content = msgdic['content']
            accion = gm.value(subject=content, predicate=RDF.type)
            logger.info(accion)

            if accion == ONT.ProductoDevuelto:
               # gr = contactarCobrador(gm)
                msgResult = ONT['pago_dev_' + str(get_count())]
                AgentCobr = get_agent_info(agn.AgentCobrador, DirectoryAgent, AgentDevoluciones, get_count())
                gr = infoagent_search_message(AgentCobr.address, AgentCobr.uri, gm, msgResult)

    mss_cnt += 1

    logger.info('Respondemos a la peticion')

    return gr.serialize(format='xml')


def contactarCobrador(gm):
    index = 0
    subject_pos = {}
    lista = []
    procedencia = ""
    usuario = ""
    targeta = ""
    id = ""
    precio = 0.0
    for s, p, o in gm:
        if s not in subject_pos:
            subject_pos[s] = index
            lista.append({})
            index += 1
        if s in subject_pos:
            subject_dict = lista[subject_pos[s]]
            if p == RDF.type:
                subject_dict['url'] = s
            elif p == ONT.id:
                id = subject_dict['id'] = o
            elif p == ONT.proc:
                subject_dict['proc'] = o
                procedencia = subject_dict['proc']
            elif p == ONT.precio:
                precio = subject_dict['precio'] = o
            elif p == ONT.targeta:
                targeta = subject_dict['targeta'] = o
            elif p == ONT.usuario:
                usuario = subject_dict['usuario'] = o
                lista[subject_pos[s]] = subject_dict


    msgResult = ONT['cobro2_' + str(get_count())]
    gr = Graph()
    body_prod_dev = ONT['id_Dev_' + id]
    gr.add((msgResult, RDF.type, ONT.ProductoDevuelto))
    gr.add((body_prod_dev, RDF.type, ONT.Producto_devuelto))
    gr.add((body_prod_dev, ONT.id, Literal(id, datatype=XSD.integer)))
    gr.add((body_prod_dev, ONT.proc, Literal(procedencia, datatype=XSD.string)))
    gr.add((body_prod_dev, ONT.precio, Literal(precio, datatype=XSD.float)))
    gr.add((body_prod_dev, ONT.targeta, Literal(targeta, datatype=XSD.string)))
    gr.add((body_prod_dev, ONT.usuario, Literal(usuario, datatype=XSD.string)))
    gr.add((msgResult, ONT.DevolverProducto, URIRef(body_prod_dev)))
    AgentCobr = get_agent_info(agn.AgentCobrador, DirectoryAgent, AgentDevoluciones, get_count())
    logger.info(AgentCobr.address)
    logger.info(AgentCobr.uri)
    logger.info(msgResult)
    logger.info(id)
    logger.info(procedencia)
    logger.info(precio)
    logger.info(targeta)
    logger.info(usuario)
    logger.info(AgentDevoluciones.uri)


    gr2 = infoagent_search_message(AgentCobr.address, AgentCobr.uri, gr, msgResult)


    return gm


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