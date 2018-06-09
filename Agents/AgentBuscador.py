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
from rdflib import Graph, Namespace, Literal
from rdflib.namespace import FOAF, RDF, XSD

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
        gr = build_message(Graph(), ACL['not-understood'], sender=AgentBuscador.uri, msgcnt=mss_cnt)
    else:
        # Obtenemos la performativa
        perf = msgdic['performative']

        if perf != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            gr = build_message(Graph(), ACL['not-understood'], sender=AgentBuscador.uri, msgcnt=mss_cnt)
        else:
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
                    elif gm.value(subject=restriccion, predicate=RDF.type) == ONT.restriccion_de_precio:
                        precio_max = gm.value(subject=restriccion, predicate=ONT.precio_max)
                        logger.info('precio_max: '+ precio_max)
                        restricciones_busqueda['precio_max'] = precio_max

                    gr = search(**restricciones_busqueda)

    mss_cnt += 1

    logger.info('Respondemos a la peticion')

    return gr.serialize(format='xml')

def search(nombre=None, marca=None, precio_max=sys.float_info.max):
    graph = Graph()
    ontologyFile = open('../Data/product.rdf')
    graph.parse(ontologyFile, format='turtle')
    first = second = 0
    query = """
        prefix rdf:<http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        prefix xsd:<http://www.w3.org/2001/XMLSchema#>
        prefix default:<http://www.owl-ontologies.com/ECSDI-ontologia.owl#>
        prefix owl:<http://www.w3.org/2002/07/owl#>
        SELECT DISTINCT ?producto ?nombre ?marca ?precio ?peso
        where {
            { ?producto rdf:type default:Producto } UNION { ?producto rdf:type default:Producto_externo } .
            ?producto default:nombre ?nombre .
            ?producto default:marca ?marca .
            ?producto default:precio ?precio .
            ?producto default:peso ?peso .
            FILTER("""

    if nombre is not None:
        query += """str(?nombre) = '""" + nombre + """'"""
        first = 1

    if marca is not None:
        if first == 1:
            query += """ && """
        query += """str(?marca) = '""" + marca + """'"""
        second = 1

    if first == 1 or second == 1 or precio_max != sys.float_info.max:
        if first == 1 or second == 1:
            query += """ && """
        query += """
                ?precio <= """ + str(precio_max) + """  )}
                order by desc(UCASE(str(?precio)))"""


    graph_query = graph.query(query)
    result = Graph()
    result.bind('ONT', ONT)
    product_count = 0
    for row in graph_query:
        nombre = row.nombre
        marca = row.marca
        precio = row.precio
        logger.info(nombre)
        logger.info(marca)
        logger.info(precio)
        peso = row.peso
        subject = row.producto
        product_count += 1
        result.add((subject, RDF.type, ONT.Producto))
        result.add((subject, ONT.marca, Literal(marca, datatype=XSD.string)))
        result.add((subject, ONT.precio, Literal(precio, datatype=XSD.float)))
        result.add((subject, ONT.peso, Literal(peso, datatype=XSD.float)))
        result.add((subject, ONT.nombre, Literal(nombre, datatype=XSD.string)))
    return result


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