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
    port = 9005
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
AgentLogistico = Agent('AgentLogistico',
                  agn.AgentLogistico,
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

    gr = register_agent(AgentLogistico, DirectoryAgent, AgentLogistico.uri, get_count())
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
        gr = build_message(Graph(), ACL['not-understood'], sender=AgentLogistico.uri, msgcnt=mss_cnt)
    else:
        # Obtenemos la performativa
        perf = msgdic['performative']

        if perf != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            gr = build_message(Graph(), ACL['not-understood'], sender=AgentLogistico.uri, msgcnt=mss_cnt)
        else:
            # Extraemos el objeto del contenido que ha de ser una accion de la ontologia de acciones del agente
            # de registro

            # Averiguamos el tipo de la accion

            content = msgdic['content']
            accion = gm.value(subject=content, predicate=RDF.type)
            # Aqui realizariamos lo que pide la accion
            # Por ahora simplemente retornamos un Inform-done
            if accion == ONT.Registrar:
                gr = registrarProducto(gm)
            elif accion == ONT.Registrar_centro:
                gr = registrarProductoCentro(gm)
            elif accion == ONT.GetProductos:
                gr = getProductos(gm)
            elif accion == ONT.Asignar_compra:
                gr = asignarCompra(gm)
            elif accion == ONT.GetLotes:
                gr = getLotes(gm)

    mss_cnt += 1

    logger.info('Respondemos a la peticion')

    return gr.serialize(format='xml')


def registrarProducto(gm):
    ontologia = open('../Data/product.rdf')
    gr = Graph()
    gr.parse(ontologia, format="turtle")
    producto = gm.subjects(RDF.type, ONT.Producto_externo)
    producto = producto.next()

    for s, p, o in gm:
        if s == producto:
            gr.add((s, p, o))

    gr.serialize(destination='../Data/product.rdf', format='turtle')
    return gm

def registrarProductoCentro(gm):
    ontologia = open('../Data/product.rdf')
    gr = Graph()
    gr.parse(ontologia, format="turtle")
    producto = gm.subjects(RDF.type, ONT.Producto)
    producto = producto.next()

    for s, p, o in gm:
        if s == producto:
            gr.add((s, p, o))

    gr.serialize(destination='../Data/product.rdf', format='turtle')
    return gm


def deleteCompra(id_compra):
    graph = Graph()
    ontologyFile = open('../Data/compras.rdf')
    graph.parse(ontologyFile, format='turtle')
    query = """
                prefix rdf:<http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                prefix xsd:<http://www.w3.org/2001/XMLSchema#>
                prefix default:<http://www.ontologia.com/ECSDI-ontologia.owl#>
                prefix owl:<http://www.w3.org/2002/07/owl#>
                DELETE ?compra ?direccion ?id_compra ?nombre ?peso ?precio ?precio_externo ?prioridad ?targeta ?total ?id_lote ?enviado
                where {
                    { ?compra rdf:type default:Compra }  .
                    ?compra default:direccion ?direccion .
                    ?compra default:id_compra ?id_compra .
                    ?compra default:nombre ?nombre .
                    ?compra default:peso ?peso .
                    ?compra default:precio ?precio .
                    ?compra default:precio_externo ?precio_externo .
                    ?compra default:prioridad ?prioridad .
                    ?compra default:targeta ?targeta .
                    ?compra default:total ?total .
                    ?compra default:id_lote ?id_lote .
                    ?compra default:enviado ?enviado .
                    FILTER("""

    query += """str(?id_compra) = """"'" + str(id_compra) + "'"""" )}
                    order by desc(UCASE(str(?precio)))"""

    return None


def getProductos(gm):
    graph = Graph()
    ontologyFile = open('../Data/compras.rdf')
    graph.parse(ontologyFile, format='turtle')
    query = """
            prefix rdf:<http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            prefix xsd:<http://www.w3.org/2001/XMLSchema#>
            prefix default:<http://www.ontologia.com/ECSDI-ontologia.owl#>
            prefix owl:<http://www.w3.org/2002/07/owl#>
            SELECT DISTINCT ?compra ?direccion ?id_compra ?nombre ?peso ?precio ?precio_externo ?prioridad ?targeta ?total ?id_lote ?enviado
            where {
                { ?compra rdf:type default:Compra }  .
                ?compra default:direccion ?direccion .
                ?compra default:id_compra ?id_compra .
                ?compra default:nombre ?nombre .
                ?compra default:peso ?peso .
                ?compra default:precio ?precio .
                ?compra default:precio_externo ?precio_externo .
                ?compra default:prioridad ?prioridad .
                ?compra default:targeta ?targeta .
                ?compra default:total ?total .
                ?compra default:id_lote ?id_lote .
                ?compra default:enviado ?enviado .
                FILTER("""

    query += """str(?enviado) = 'false' """
    query += """&& str(?id_lote) = '0' )}
                order by desc(UCASE(str(?precio)))"""

    graph_query = graph.query(query)
    result = Graph()
    result.bind('ONT', ONT)
    product_count = 0
    for row in graph_query:
        id_compra = row.id_compra
        id_lote = row.id_lote
        prioridad = row.prioridad
        direccion = row.direccion
        peso = row.peso
        total = row.total
        subject = row.compra
        product_count += 1
        result.add((subject, RDF.type, ONT.Compra))
        result.add((subject, ONT.id_compra, Literal(id_compra, datatype=XSD.integer)))
        result.add((subject, ONT.id_lote, Literal(id_lote, datatype=XSD.integer)))
        result.add((subject, ONT.prioridad, Literal(prioridad, datatype=XSD.integer)))
        result.add((subject, ONT.direccion, Literal(direccion, datatype=XSD.string)))
        result.add((subject, ONT.peso, Literal(peso, datatype=XSD.float)))
        result.add((subject, ONT.total, Literal(total, datatype=XSD.integer)))
    return result

def asignarCompra(gm):
    index = 0
    subject_pos = {}
    lista = []
    id_lote = 0
    id_compra = 0
    for s, p, o in gm:
        if s not in subject_pos:
            subject_pos[s] = index
            lista.append({})
            index += 1
        if s in subject_pos:
            subject_dict = lista[subject_pos[s]]
            if p == RDF.type:
                subject_dict['url'] = s
            elif p == ONT.id_lote:
                subject_dict['id_lote'] = o
                id_lote = subject_dict['id_lote']
            elif p == ONT.id_compra:
                subject_dict['id_compra'] = o
                id_compra = subject_dict['id_compra']
                lista[subject_pos[s]] = subject_dict

    logger.info(id_lote)
    logger.info(id_compra)
    query_compra(id_compra, id_lote)
    deleteCompra(id_compra)
    return gm


def query_compra(id_compra, id_lote):
    graph = Graph()
    ontologyFile = open('../Data/compras.rdf')
    graph.parse(ontologyFile, format='turtle')
    query = """
                prefix rdf:<http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                prefix xsd:<http://www.w3.org/2001/XMLSchema#>
                prefix default:<http://www.ontologia.com/ECSDI-ontologia.owl#>
                prefix owl:<http://www.w3.org/2002/07/owl#>
                SELECT DISTINCT ?compra ?direccion ?id_compra ?nombre ?peso ?precio ?precio_externo ?prioridad ?targeta ?total ?id_lote ?enviado
                where {
                    { ?compra rdf:type default:Compra }  .
                    ?compra default:direccion ?direccion .
                    ?compra default:id_compra ?id_compra .
                    ?compra default:nombre ?nombre .
                    ?compra default:peso ?peso .
                    ?compra default:precio ?precio .
                    ?compra default:precio_externo ?precio_externo .
                    ?compra default:prioridad ?prioridad .
                    ?compra default:targeta ?targeta .
                    ?compra default:total ?total .
                    ?compra default:id_lote ?id_lote .
                    ?compra default:enviado ?enviado .
                    FILTER("""

    query += """str(?id_compra) = """"'" + str(id_compra) + "'"""" )}
                    order by desc(UCASE(str(?precio)))"""
    logger.info(query)
    graph_query = graph.query(query)

    result = Graph()
    result.bind('ONT', ONT)
    product_count = 0
    for row in graph_query:
        logger.info('entro')
        prioridad = row.prioridad
        direccion = row.direccion
        nombre = row.nombre
        peso = row.peso
        precio = row.precio
        precio_externo = row.precio_externo
        targeta = row.targeta
        total = row.total
        enviado = row.enviado
        subject = row.compra
        product_count += 1
        result.add((subject, RDF.type, ONT.Compra))
        result.add((subject, ONT.id_compra, Literal(id_compra, datatype=XSD.integer)))
        result.add((subject, ONT.id_lote, Literal(id_lote, datatype=XSD.integer)))
        result.add((subject, ONT.prioridad, Literal(prioridad, datatype=XSD.integer)))
        result.add((subject, ONT.direccion, Literal(direccion, datatype=XSD.string)))
        result.add((subject, ONT.peso, Literal(peso, datatype=XSD.float)))
        result.add((subject, ONT.total, Literal(total, datatype=XSD.integer)))
        result.add((subject, ONT.nombre, Literal(nombre, datatype=XSD.string)))
        result.add((subject, ONT.precio, Literal(precio, datatype=XSD.float)))
        result.add((subject, ONT.precio_externo, Literal(precio_externo, datatype=XSD.float)))
        result.add((subject, ONT.targeta, Literal(targeta, datatype=XSD.string)))
        result.add((subject, ONT.enviado, Literal(enviado, datatype=XSD.boolean)))

    ontologia = open('../Data/compras_con_lote.rdf')
    gr = Graph()
    gr.parse(ontologia, format="turtle")
    compra = result.subjects(RDF.type, ONT.Compra)
    compra = compra.next()

    for s, p, o in result:
        if s == compra:
            gr.add((s, p, o))

    gr.serialize(destination='../Data/compras_con_lote.rdf', format='turtle')

    return None

def getLotes(gm):
    graph = Graph()
    ontologyFile = open('../Data/compras_con_lote.rdf')
    graph.parse(ontologyFile, format='turtle')
    query = """
                    prefix rdf:<http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                    prefix xsd:<http://www.w3.org/2001/XMLSchema#>
                    prefix default:<http://www.ontologia.com/ECSDI-ontologia.owl#>
                    prefix owl:<http://www.w3.org/2002/07/owl#>
                    SELECT DISTINCT ?compra ?id_lote 
                    where {
                        { ?compra rdf:type default:Compra }  .
                        ?compra default:id_lote ?id_lote .
                        }
                        order by desc(UCASE(str(?id_lote)))"""
    logger.info(query)
    graph_query = graph.query(query)

    result = Graph()
    result.bind('ONT', ONT)
    product_count = 0
    lotes = []
    for row in graph_query:
        logger.info('entro')
        id_lote = row.id_lote
        subject = row.compra
        product_count += 1
        if id_lote not in lotes:
            result.add((subject, RDF.type, ONT.Compra))
            result.add((subject, ONT.id_lote, Literal(id_lote, datatype=XSD.integer)))
            lotes.append(id_lote)
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