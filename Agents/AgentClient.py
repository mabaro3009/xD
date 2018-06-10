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

#Carrito de la compra
carrito_compra = []


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
        logger.info(request.form['submit'])
        if request.form['submit'] == 'Buscar':
            logger.info("Petición de búsqueda enviada")

            msgResult = ONT['Busqueda' + str(get_count())]

            gr = Graph()
            gr.add((msgResult, RDF.type, ONT.Busqueda))

            nombre = request.form['nombre']
            marca = request.form['marca']
            precio_max = request.form['precio_max']


            if nombre:
                body_nombre = ONT['restriccion_de_nombre' + str(get_count())]
                gr.add((body_nombre, RDF.type, ONT.restriccion_de_nombre))
                gr.add((body_nombre, ONT.nombre, Literal(nombre, datatype=XSD.string)))
                gr.add((msgResult, ONT.Restringe, URIRef(body_nombre)))

            if marca:
                body_marca = ONT['restriccion_de_marca' + str(get_count())]
                gr.add((body_marca, RDF.type, ONT.restriccion_de_marca))
                gr.add((body_marca, ONT.marca, Literal(marca, datatype=XSD.string)))
                gr.add((msgResult, ONT.Restringe, URIRef(body_marca)))



            if precio_max:
                body_precio = ONT['restriccion_de_precio' + str(get_count())]
                gr.add((body_precio, RDF.type, ONT.restriccion_de_precio))
                gr.add((body_precio, ONT.precio_max, Literal(precio_max, datatype=XSD.float)))
                gr.add((msgResult, ONT.Restringe, URIRef(body_precio)))

            grAgentBuscador = get_agent_info(agn.AgentBuscador, DirectoryAgent, AgentClient, get_count())

            gr2 = infoagent_search_message(grAgentBuscador.address, grAgentBuscador.uri, gr, msgResult)

            index = 0
            subject_pos = {}
            lista = []
            for s, p, o in gr2:
                if s not in subject_pos:
                    subject_pos[s] = index
                    lista.append({})
                    index += 1
                if s in subject_pos:
                    subject_dict = lista[subject_pos[s]]
                    if p == RDF.type:
                        subject_dict['url'] = s
                    elif p == ONT.marca:
                        subject_dict['marca'] = o
                    elif p == ONT.precio:
                        subject_dict['precio'] = o
                    elif p == ONT.nombre:
                        subject_dict['nombre'] = o
                    elif p == ONT.id:
                        subject_dict['id'] = o
                    elif p == ONT.proc:
                        subject_dict['proc'] = o
                    elif p == ONT.peso:
                        subject_dict['peso'] = o
                        lista[subject_pos[s]] = subject_dict

            total = calcula_precio_carrito()
            return render_template('buscar.html', productos=lista, productos_carrito = carrito_compra, total = total)

        elif request.form['submit'] == 'Al carrito!':
            item = {}
            item["id"] = request.form["id"]
            item["marca"] = request.form["marca"]
            item["precio"] = request.form["precio"]
            item["nombre"] = request.form["nombre"]
            logger.info(item["id"])
            carrito_compra.append(item)
            total = calcula_precio_carrito()
            return render_template('buscar.html', productos_carrito = carrito_compra, total = total)

        elif request.form['submit'] == 'Eliminar':
            idd = request.form["id"]
            ii = -1
            for i in range(0, len(carrito_compra)):
                if carrito_compra[i]["id"] == idd:
                    ii = i
            del carrito_compra[ii]
            total = calcula_precio_carrito()
            return render_template('buscar.html', productos_carrito = carrito_compra, total = total)

        elif request.form['submit'] == 'Comprar':
            print("comprar")
            total = calcula_precio_carrito()
            return render_template('datos_cliente.html', productos_carrito = carrito_compra, total = total)

        elif request.form['submit'] == 'Confirmar compra':
            direccion = str(request.form["direccion"])
            nombre = str(request.form["nombre"])
            targeta = str(request.form["targeta"])

            if nombre == "" or targeta == "" or direccion == "":
                total = calcula_precio_carrito()
                error = "Faltan campos por llenar. Por favor, no dejes ningun campo en blanco"
                return render_template('datos_cliente.html', productos_carrito=carrito_compra, total=total, error=error)

            datos = {}

            prioridad = int(request.form["prioridad"])
            if prioridad == 1:
                datos["envio"] = 0
                datos["llegada"] = "7 y 10 dias laborables"
            elif prioridad == 2:
                datos["envio"] = 4.95
                datos["llegada"] = "3 y 6 dias laborables"
            elif prioridad == 3:
                datos["envio"] = 15
                datos["llegada"] = "1 y 2 dias laborables"
            total = calcula_precio_carrito()
            datos["precio"] = round(total/1.21, 2)
            datos["iva"] = round(total - total / 1.21, 2)
            datos["total"] = total + datos["envio"]
            datos["nombre"] = nombre
            datos["targeta"] = targeta
            datos["direccion"] = direccion


            for producto in carrito_compra:
                gr = Graph()
                id_compra = str(random.randint(1, 1000000000))
                compra = ONT['Compra_' + id_compra]

                msgResult = ONT['Comprar_' + str(get_count())]
                gr.add((msgResult, RDF.type, ONT.Comprar))
                gr.add((compra, RDF.type, ONT.Compra))
                gr.add((compra, ONT.nombre, Literal(producto['nombre'], datatype=XSD.string)))
                gr.add((compra, ONT.marca, Literal(producto['marca'], datatype=XSD.string)))
                gr.add((compra, ONT.precio, Literal(producto['precio'], datatype=XSD.float)))
                gr.add((compra, ONT.id, Literal(producto['id'], datatype=XSD.integer)))
                gr.add((compra, ONT.id_compra, Literal(id_compra, datatype=XSD.integer)))
                gr.add((msgResult, ONT.Compra, compra))

                AgentVen = get_agent_info(agn.AgentVendedor, DirectoryAgent, AgentClient, get_count())

                infoagent_search_message(AgentVen.address, AgentVen.uri, gr, msgResult)

            return render_template('factura.html', productos_carrito=carrito_compra, datos=datos)

        elif request.form['submit'] == 'Realizar otra compra':
            return render_template('buscar.html')


        #TODO: aquí envia els productes comprats al agente vendedor perquè aquest faci el qu ahgi de fer. No va aqui obviament, despres dels returns



def calcula_precio_carrito():
    total = 0
    for i in range(0, len(carrito_compra)):
        total += float(carrito_compra[i]["precio"])
    return total




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
