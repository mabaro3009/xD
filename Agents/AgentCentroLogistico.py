# -*- coding: utf-8 -*-
"""
filename: SimplePersonalAgent
Antes de ejecutar hay que añadir la raiz del proyecto a la variable PYTHONPATH
Ejemplo de agente que busca en el directorio y llama al agente obtenido
Created on 09/02/2014
@author: javier
"""

from __future__ import print_function

import random
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
    port = 9003
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
AgentCentroLogistico = Agent('AgentCentroLogistico',
                       agn.AgentCentroLogistico,
                       'http://%s:%d/comm' % (hostname, port),
                       'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))

# Global dsgraph triplestore
dsgraph = Graph()

lote = []
compras_sin_asignar = []
compras_asignadas = []


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
    reg_obj = agn[AgentCentroLogistico.name + '-search']
    gmess.add((reg_obj, RDF.type, DSO.Search))
    gmess.add((reg_obj, DSO.AgentType, type))

    msg = build_message(gmess, perf=ACL.request,
                        sender=AgentCentroLogistico.uri,
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
                        sender=AgentCentroLogistico.uri,
                        receiver=ragn_uri,
                        msgcnt=get_count(),
                        content=msgResult)
    gr = send_message(msg, addr)
    logger.info('Recibimos respuesta a la peticion al servicio de informacion')

    return gr


@app.route("/", methods=['GET', 'POST'])
def pagina_princiapl():
    if request.method == 'GET':
        return render_template('centro_logistico_principal.html')
    else:
        if request.form['submit'] == 'Dar de alta producto':
            return redirect(url_for('alta'))
        elif request.form['submit'] == 'Crear Lote':
            return redirect(url_for('crear_lote'))

@app.route("/alta", methods=['GET', 'POST'])
def alta():
    if request.method == 'GET':
        return render_template('alta_producto.html')
    else:
        if request.form['submit'] == 'Dar de alta':
            id = str(random.randint(1, 1000000000))
            nombre = request.form['nombre']
            marca = request.form['marca']
            precio = request.form['precio']
            peso = request.form['peso']
            proc = 'centro'

            producto = ONT['Producto_' + id]

            msgResult = ONT['Registrar_' + str(get_count())]

            gr = Graph()
            gr.add((msgResult, RDF.type, ONT.Registrar_centro))

            gr.add((producto, RDF.type, ONT.Producto))
            gr.add((producto, ONT.nombre, Literal(nombre, datatype=XSD.string)))
            gr.add((producto, ONT.marca, Literal(marca, datatype=XSD.string)))
            gr.add((producto, ONT.precio, Literal(precio, datatype=XSD.float)))
            gr.add((producto, ONT.peso, Literal(peso, datatype=XSD.float)))
            gr.add((producto, ONT.id, Literal(id, datatype=XSD.integer)))
            gr.add((producto, ONT.proc, Literal(proc, datatype=XSD.string)))
            gr.add((msgResult, ONT.Producto, producto))
            AgentLog = get_agent_info(agn.AgentLogistico, DirectoryAgent, AgentCentroLogistico, get_count())

            infoagent_search_message(AgentLog.address, AgentLog.uri, gr, msgResult)

            prod = {'pnombre': request.form['nombre'], 'pmarca': request.form['marca'],
                    'pprecio': request.form['precio'], 'ppeso': request.form['peso']}

            return render_template('alta_producto.html', producto=prod)


@app.route("/crear_lote", methods=['GET', 'POST'])
def crear_lote():
    if request.method == 'GET':
        msgResult = ONT['getProductos_' + str(get_count())]

        gr = Graph()
        gr.add((msgResult, RDF.type, ONT.GetProductos))

        AgentLog = get_agent_info(agn.AgentLogistico, DirectoryAgent, AgentCentroLogistico, get_count())

        gr2 = infoagent_search_message(AgentLog.address, AgentLog.uri, gr, msgResult)

        index = 0
        subject_pos = {}
        for s, p, o in gr2:
            if s not in subject_pos:
                subject_pos[s] = index
                compras_sin_asignar.append({})
                index += 1
            if s in subject_pos:
                subject_dict = compras_sin_asignar[subject_pos[s]]
                if p == RDF.type:
                    subject_dict['url'] = s
                elif p == ONT.direccion:
                    subject_dict['direccion'] = o
                elif p == ONT.id_lote:
                    subject_dict['id_lote'] = o
                elif p == ONT.id_compra:
                    subject_dict['id_compra'] = o
                elif p == ONT.peso:
                    subject_dict['peso'] = o
                elif p == ONT.total:
                    subject_dict['total'] = o
                elif p == ONT.prioridad:
                    subject_dict['prioridad'] = o
                    compras_sin_asignar[subject_pos[s]] = subject_dict
                    global id_lote
                    id_lote = str(random.randint(1, 1000000000))

        return render_template('crear_lote.html', productos=compras_sin_asignar)

    else:
        if request.form['submit'] == 'Al lote!':
            idd = int(request.form["id_compra"])
            ii = -1
            for i in range(0, len(compras_sin_asignar)):
                logger.info(compras_sin_asignar[i]["id_compra"])
                if int(compras_sin_asignar[i]["id_compra"]) == idd:
                    ii = i
            compras_sin_asignar[ii]["id_lote"] = id_lote
            compras_asignadas.append(compras_sin_asignar[ii])
            del compras_sin_asignar[ii]
            if len(compras_sin_asignar) == 0:
                return render_template('crear_lote.html',
                                       productos_lote=compras_asignadas)
            return render_template('crear_lote.html', productos=compras_sin_asignar, productos_lote=compras_asignadas)

        if request.form['submit'] == 'Enviar Lote':
            for compra in compras_asignadas:

                compra_asignada = ONT['Compra_Asignada_' + compra['id_compra']]

                msgResult = ONT['Asignar_compra_' + str(get_count())]

                gr = Graph()
                gr.add((msgResult, RDF.type, ONT.Asignar_compra))

                gr.add((compra_asignada, RDF.type, ONT.Compra))
                gr.add((compra_asignada, ONT.id_lote, Literal(id_lote, datatype=XSD.string)))
                gr.add((compra_asignada, ONT.id_compra, Literal(compra['id_compra'], datatype=XSD.string)))
                gr.add((msgResult, ONT.Compra_asignada, compra_asignada))
                AgentLog = get_agent_info(agn.AgentLogistico, DirectoryAgent, AgentCentroLogistico, get_count())

                infoagent_search_message(AgentLog.address, AgentLog.uri, gr, msgResult)


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