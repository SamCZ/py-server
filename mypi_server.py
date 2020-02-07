# Embedded file name: mypi_server.py
# Size of source mod 2**32: 6432 bytes
# Decompiled by https://python-decompiler.com
import socket, sys
import RPi.GPIO as GPIO
import json, threading, configparser, os, time, requests
from threading import Thread
print('MyPi TCP Server v1.6')
path = os.path.dirname(os.path.abspath(__file__)) + '/mypi.cfg'
print('Loading configuration file: ' + path)
config = configparser.ConfigParser()
config.read(path)
BUFFER_SIZE = 256
TCP_IP = '0.0.0.0'
PASSWORD = config.get('CONNECTION', 'PASSWORD')
PASSWORD = PASSWORD.strip('"')
TCP_PORT = config.getint('CONNECTION', 'TCP_PORT')
USE_DDNS = config.getint('DDNS', 'USE_MYPI_DDNS')
YOUR_EMAIL = config.get('DDNS', 'YOUR_EMAIL')
YOUR_EMAIL = YOUR_EMAIL.strip('"')
DEVICE_NAME = config.get('DDNS', 'DEVICE_NAME')
DEVICE_NAME = DEVICE_NAME.strip('"')
INIT_LEVEL = config.getint('GPIO', 'INIT_LEVEL')
DELAY = config.getfloat('GPIO', 'DELAY')
MAX_OUTPUT_PINS = 8
OUTPUTS = []
INPUTS = []
MODES = []
for x in range(1, MAX_OUTPUT_PINS + 1):
    outs = 'OUT' + str(x)
    ins = 'IN' + str(x)
    modes = outs + '-MODE'
    OUTPUTS.append(config.getint('GPIO', outs))
    INPUTS.append(config.getint('GPIO', ins))
    mode = config.get('GPIO', modes)
    mode = mode.strip('"')
    MODES.append(mode)

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BOARD)
connectionsList = []
print('Init GPIO Output pins')
for pin in OUTPUTS:
    GPIO.setup(pin, (GPIO.OUT), initial=INIT_LEVEL)

print('Init GPIO Input pins')
for pin in INPUTS:
    GPIO.setup(pin, (GPIO.IN), pull_up_down=(GPIO.PUD_UP))

def flip(socket, x):
    GPIO.output(OUTPUTS[x], not GPIO.input(OUTPUTS[x]))
    requests.get("https://dee.systems/api/status.php?type=pinadd&machine_id=1&pin=" + str(OUTPUTS[x]) + "&pin_value=" + str(GPIO.input(OUTPUTS[x])))
    print('Pin %d: level=%d' % (OUTPUTS[x], GPIO.input(OUTPUTS[x])))
    updateAllClients(socket)


def flipOutput(socket, index):
    flip(socket, index)
    if MODES[index] == 'M':
        time.sleep(DELAY)
        flip(socket, index)


def getInputs():
    status = []
    for x in range(0, MAX_OUTPUT_PINS):
        status.append(GPIO.input(OUTPUTS[x]))

    return status


def sendResponse(connection, ctx, status):
    response = {}
    response['ctx'] = ctx
    response['status'] = status
    connection.send(bytes(json.dumps(response), 'UTF-8'))


def updateAllClients(socket):
    global connectionsList
    status = getInputs()
    if socket == '':
        for currentConn in connectionsList:
            sendResponse(currentConn, 'update', status)

    else:
        sendResponse(socket, 'update', status)
        for currentConn in connectionsList:
            if currentConn != socket:
                sendResponse(currentConn, 'update', status)


def checkInputs():
    delay = 0.1
    for x in range(0, MAX_OUTPUT_PINS):
        if GPIO.input(INPUTS[x]) == 0:
            threading.Thread(target=flipOutput, args=('', x)).start()
            delay = 0.2

    threading.Timer(delay, checkInputs).start()


def updateDNS(email, name):
    print('Updating MyPi DDNS Server')
    delay = 1800.0
    try:
        jsonInfo = {'email':email, 
         'name':name}
        params = json.dumps(jsonInfo).encode('utf8')
        try:
            response = requests.post('http://54.214.248.70/mypi/reg.php', data={'json': params})
            status = json.loads(response.text)
            print('MyPi DDNS:', status['status'])
        except requests.exceptions.RequestException as e:
            try:
                delay = 10.0
                print('MyPi DDNS / Internet Connection is down, trying in %dSec' % delay)
            finally:
                e = None
                del e

    except ValueError:
        print('Error:', ValueError)

    time.sleep(delay)
    updateDNS(email, name)


class DNSUpdateThread(Thread):

    def __init__(self, email, name):
        Thread.__init__(self)
        self.email = email
        self.name = name

    def run(self):
        updateDNS(self.email, self.name)


class ClientThread(threading.Thread):

    def __init__(self, ip, port, clientsocket):
        threading.Thread.__init__(self)
        self.ip = ip
        self.port = port
        self.socket = clientsocket
        print('Connected to: ' + ip)

    def run(self):
        global BUFFER_SIZE
        auth = False
        sendResponse(self.socket, 'sendcode', '')
        while 1:
            data = self.socket.recv(BUFFER_SIZE)
            if not data:
                break
            info = data.decode('UTF-8')
            list = info.split()
            cmd = list[0]
            val = list[1]
            if cmd == 'password':
                if val == PASSWORD:
                    auth = True
                    sendResponse(self.socket, 'password', getInputs())
                    connectionsList.append(self.socket)
                else:
                    sendResponse(self.socket, 'password', 'codenotok')
                    self.socket.shutdown(0)
            if auth:
                pass
            if cmd == 'update':
                index = int(val)
                if index < MAX_OUTPUT_PINS:
                    threading.Thread(target=flipOutput, args=(self.socket, index)).start()
                if cmd == 'get':
                    if val == 'status':
                        sendResponse(self.socket, 'update', status)

        if self.socket in connectionsList:
            connectionsList.remove(self.socket)
        print(self.ip + ' Disconnected...')


tcpsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
tcpsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
tcpsock.bind((TCP_IP, TCP_PORT))
checkInputs()
print('Listening for incoming connections on Port ' + str(TCP_PORT))
if USE_DDNS:
    if len(YOUR_EMAIL) == 0:
        print('DDNS is enabled but YOUR_EMAIL is empty, please set your email address.')
    elif len(DEVICE_NAME) == 0:
        print('DDNS is enabled but DEVICE_NAME is empty, please set a device name.')
    else:
        thread = DNSUpdateThread(YOUR_EMAIL, DEVICE_NAME)
        thread.start()
while True:
    tcpsock.listen(5)
    clientsock, (TCP_IP, TCP_PORT) = tcpsock.accept()
    newthread = ClientThread(TCP_IP, TCP_PORT, clientsock)
    newthread.start()