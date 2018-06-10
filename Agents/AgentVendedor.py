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
    port = 9008
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
AgentVendedor = Agent('AgentVendedor',
                  agn.AgentVendedor,
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

    gr = register_agent(AgentVendedor, DirectoryAgent, AgentVendedor.uri, get_count())
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
        gr = build_message(Graph(), ACL['not-understood'], sender=AgentVendedor.uri, msgcnt=mss_cnt)
    else:
        # Obtenemos la performativa
        perf = msgdic['performative']

        if perf != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            gr = build_message(Graph(), ACL['not-understood'], sender=AgentVendedor.uri, msgcnt=mss_cnt)
        else:
            # Extraemos el objeto del contenido que ha de ser una accion de la ontologia de acciones del agente
            # de registro

            # Averiguamos el tipo de la accion
            content = msgdic['content']
            accion = gm.value(subject=content, predicate=RDF.type)
            logger.info(accion)

            if accion == ONT.Comprar:
                gr = registrarCompra(gm)

            elif accion == ONT.Comprar_producto:
                gr = registrarProductoComprado(gm)

            elif accion == ONT.Busqueda:
                restricciones = gm.objects(content, ONT.Restringe)
                restricciones_busqueda = {}
                for restriccion in restricciones: #nomes hi entrara 1 cop
                    if gm.value(subject=restriccion, predicate=RDF.type) == ONT.productos_usuario:
                        usuario = gm.value(subject=restriccion, predicate=ONT.nombre)
                        restricciones_busqueda['nombre'] = usuario

                    gr = search(**restricciones_busqueda)

    mss_cnt += 1

    logger.info('Respondemos a la peticion')

    return gr.serialize(format='xml')


def search(nombre=None, marca=None, precio_max=sys.float_info.max):
    graph = Graph()
    ontologyFile = open('../Data/productos_comprados.rdf')
    graph.parse(ontologyFile, format='turtle')
    first = second = 0
    query = """
        prefix rdf:<http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        prefix xsd:<http://www.w3.org/2001/XMLSchema#>
        prefix default:<http://www.ontologia.com/ECSDI-ontologia.owl#>
        prefix owl:<http://www.w3.org/2002/07/owl#>
        SELECT DISTINCT ?producto ?nombre ?marca ?precio ?id ?proc ?targeta ?te_feedback
        where {
            { ?producto rdf:type default:Producto_Comprado }  .
            ?producto default:nombre ?nombre .
            ?producto default:marca ?marca .
            ?producto default:precio ?precio .
            ?producto default:id ?id .
            ?producto default:proc ?proc .
            ?producto default:targeta ?targeta .
            ?producto default:te_feedback ?te_feedback .
            FILTER("""


    query += """str(?usuario) = """"'" + str(nombre) + "'"""" )}
                    order by desc(UCASE(str(?precio)))"""

    logger.info(nombre)
    logger.info(query)
    graph_query = graph.query(query)
    result = Graph()
    result.bind('ONT', ONT)
    product_count = 0
    logger.info("comenco a imprimir coses que trobo:")
    for row in graph_query:
        nombre = row.nombre
        marca = row.marca
        precio = row.precio
        id = row.id
        proc = row.proc
        targeta = row.targeta
        te_feedback = row.te_feedback
        subject = row.producto
        logger.info(nombre)
        logger.info(proc)
        logger.info(te_feedback)
        logger.info(targeta)
        product_count += 1
        result.add((subject, RDF.type, ONT.Producto))
        result.add((subject, ONT.marca, Literal(marca, datatype=XSD.string)))
        result.add((subject, ONT.precio, Literal(precio, datatype=XSD.float)))
        result.add((subject, ONT.nombre, Literal(nombre, datatype=XSD.string)))
        result.add((subject, ONT.id, Literal(id, datatype=XSD.integer)))
        result.add((subject, ONT.id, Literal(targeta, datatype=XSD.string)))
        result.add((subject, ONT.id, Literal(te_feedback, datatype=XSD.bool)))
        result.add((subject, ONT.proc, Literal(proc, datatype=XSD.string)))
    return result




def registrarCompra(gm):
    ontologia = open('../Data/compras.rdf')
    gr = Graph()
    gr.parse(ontologia, format="turtle")
    compra = gm.subjects(RDF.type, ONT.Compra)
    compra = compra.next()

    for s, p, o in gm:
        if s == compra:
            gr.add((s, p, o))

    gr.serialize(destination='../Data/compras.rdf', format='turtle')
    return gm

def registrarProductoComprado(gm):
    ontologia = open('../Data/productos_comprados.rdf')
    gr = Graph()
    gr.parse(ontologia, format="turtle")
    producto = gm.subjects(RDF.type, ONT.Producto_comprado)
    producto = producto.next()

    for s, p, o in gm:
        if s == producto:
            gr.add((s, p, o))

    gr.serialize(destination='../Data/productos_comprados.rdf', format='turtle')
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
