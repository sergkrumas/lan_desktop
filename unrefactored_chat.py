



from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtNetwork import *

from PyQt5 import uic
import sys
import time

import cbor2

MaxBufferSize = 1024000

TransferTimeout = 30 * 1000
PongTimeout = 60 * 1000
PingInterval = 5 * 1000


BROADCASTINTERVAL = 2000
BROADCASTPORT = 45000

def prepare_data_to_write(data_obj):
    data = cbor2.dumps(data_obj)
    data_length = len(data)
    data_to_sent = data_length.to_bytes(4, 'big') + data
    return data_to_sent



class Connection(QObject):


    class DataType:
        PlainText = 0
        Ping = 1
        Pong = 2
        Greeting = 3
        Undefined = 4
    Q_ENUMS(DataType)

    # 
    # Protocol is defined as follows, using the CBOR Data Definition Language:
    # 
    # protocol    = [
    #    greeting,        ; must start with a greeting command
    #    * command        ; zero or more regular commands after
    # ]
    # command     = plaintext / ping / pong / greeting
    # plaintext   = { 0 => text }
    # ping        = { 1 => null }
    # pong        = { 2 => null }
    # greeting    = { 3 => text }
    # 

    readyForUse = pyqtSignal()
    newMessage = pyqtSignal(str, str)

    def deleteLater(self):
        if self.isGreetingMessageSent:
            self.socket.waitForBytesWritten(2000)
        super().deleteLater()

    class states():
        readSize = 0
        readData = 1        

    def __init__(self, parent, client_socket=None):
        super().__init__()

        self.socket = client_socket

        self.greetingMessage = 888
        self.username = 'unknown'
        self.pingTimer = QTimer()
        self.pongTime = QElapsedTimer()
        self.buffer = ''

        self.pingTimer.setInterval(PingInterval)
        self.currentDataType = self.DataType.Undefined
        self.isGreetingMessageSent = False

        self.socket.readyRead.connect(self.processReadyRead)
        self.socket.disconnected.connect(self.pingTimer.stop)
        self.pingTimer.timeout.connect(self.sendPing)
        self.socket.connected.connect(self.sendGreetingMessage)

        self.socket_buffer = bytes()
        self.readState = self.states.readSize
        self.SIZE_INT_SIZE = 4
        self.data_size = 0

    def name(self):
        return self.username

    def setGreetingMessage(self, message):
        self.greetingMessage = message

    def sendMessage(self, message):
        if not message:
            return False
        self.socket.write(prepare_data_to_write({self.DataType.PlainText: message}))
        return True

    def processReadyRead(self,):

        def slice_data(data, length):
            return data[:length], data[length:]

        # print('try read')

        self.socket_buffer = self.socket_buffer + self.socket.read(2**10)

        if self.readState == self.states.readSize:
            if len(self.socket_buffer) >= self.SIZE_INT_SIZE:
                data, self.socket_buffer = slice_data(self.socket_buffer, self.SIZE_INT_SIZE)
                self.data_size = int.from_bytes(data, 'big')
                self.readState = self.states.readData
                # print('size read', self.data_size)
            else:
                pass
                # print('not enough data to read the data size')

        # здесь обязательно, чтобы было if, и не было else if
        # это нужно для того, чтобы сразу прочитать данные,
        # если они уже есть и не ставить сообщение в очередь через emit
        if self.readState == self.states.readData:
            if self.data_size < 0:
                raise Exception('Fuck!')
            if len(self.socket_buffer) >= self.data_size:
                data, self.socket_buffer = slice_data(self.socket_buffer, self.data_size)
                try:
                    parsed_data = cbor2.loads(data)
                    # print(parsed_data)

                    self.currentDataType, value = list(parsed_data.items())[0]
                    if self.currentDataType == self.DataType.Greeting:

                        addr = self.socket.peerAddress().toString()
                        port = self.socket.peerPort()

                        self.username = f'{value}@{addr}:{port}'

                        if not self.socket.isValid():
                            self.socket.abort()
                            return

                        if not self.isGreetingMessageSent:
                            self.sendGreetingMessage()

                        self.pingTimer.start()
                        self.pongTime.start()
                        self.readyForUse.emit()

                    elif self.currentDataType == self.DataType.PlainText:
                        self.newMessage.emit(self.username, value)

                    elif self.currentDataType == self.DataType.Ping:
                        self.socket.write(prepare_data_to_write({self.DataType.Pong: ''}))

                    elif self.currentDataType == self.DataType.Pong:
                        self.pongTime.restart()

                    self.data_size = 0
                    self.readState = self.states.readSize

                except Exception as e:
                    print(e, 'aborting...')
                    socket.abort()

            else:
                pass
                # print('not enough data to read cbor data')

    def sendPing(self):
        if self.pongTime.elapsed() > PongTimeout:
            # self.abort()
            return

        self.socket.write(
            prepare_data_to_write({self.DataType.Ping: ''})
        )

    def sendGreetingMessage(self):
        self.socket.write(
            prepare_data_to_write({self.DataType.Greeting: self.greetingMessage})
        )
        self.isGreetingMessageSent = True




clients_connections = []

class MessageServer(QTcpServer):

    def __init__(self, parent, new_connection_handler):
        super().__init__(parent)

        self.newConnection.connect(lambda: self.new_user_connected(self))
        self.listen(QHostAddress.Any)
        if self.isListening():
            print('Server listening at port', self.serverPort())

        self.new_connection_handler = new_connection_handler

    def new_user_connected(self, server):
        print('!!!! new user has knocked to server')

        client_socket = server.nextPendingConnection()
        connection = Connection(None, client_socket=client_socket)

        self.new_connection_handler(connection)

        clients_connections.append(connection)


class Client(QObject):

    newMessage = pyqtSignal(str, str)
    newParticipant = pyqtSignal(str)
    participantLeft = pyqtSignal(str)

    def __init__(self, *args):
        super().__init__(*args)

        self.peers = dict()
        self.peerManager = PeerManager(self)

        self.server = MessageServer(self, self.newConnection)
        self.peerManager.setServerPort(self.server.serverPort())
        self.peerManager.startBroadcasting()

        self.peerManager.newConnection.connect(self.newConnection)


    def sendMessage(self, message):
        if not message:
            return

        for addr, connection in self.peers.items():
            connection.sendMessage(message)

    def nickName(self):

        user_name = self.peerManager.userName()
        host_info = QHostInfo.localHostName()
        server_port = str(self.server.serverPort())
        return f'{user_name}@{host_info}:{server_port}'

    def hasConnection(self, senderIp, senderPort = -1):
        if senderPort == -1:
            return senderIp in self.peers.keys()

        if not senderIp in self.peers.keys():
            return False

        items = self.peers.items()
        for addr, connection in items:
            if addr == senderIp:
                if connection.socket.peerPort() == senderPort:
                    return True
        return False

    def newConnection(self, connection):
        connection.setGreetingMessage(self.peerManager.userName())
        connection.sendGreetingMessage()

        connection.socket.errorOccurred.connect(self.connectionError)
        connection.socket.disconnected.connect(self.disconnected)
        connection.readyForUse.connect(self.readyForUse)

    def connectionError(self, socketError):
        socket = self.sender()

        errors = {
            QAbstractSocket.HostNotFoundError:
                "The host was not found. Please check the host name and port settings.",
            QAbstractSocket.ConnectionRefusedError:
                "The connection was refused by the peer. Make sure the server is running,"
                "and check that the host name and port settings are correct.",
            QAbstractSocket.RemoteHostClosedError:
                None,
        }
        default_error_msg = "The following error occurred on client socket: %s." % socket.errorString()
        msg = errors.get(socketError, default_error_msg)

        print('socket error', msg)
        self.removeConnection(socket)

    def disconnected(self):
        socket = self.sender()
        print('disconnected', socket.peerAddress().toString())
        self.removeConnection(socket)

    def readyForUse(self):
        connection = self.sender()
        socket = connection.socket
        if self.hasConnection(socket.peerAddress(), senderPort=socket.peerPort()):
            return

        connection.newMessage.connect(self.newMessage)

        self.peers[socket.peerAddress()] = connection
        nick = connection.name()
        if nick:
            self.newParticipant.emit(nick)

    def removeConnection(self, socket):
        if socket.peerAddress() in self.peers.keys():
            connection = self.peers.pop(socket.peerAddress())
            nick = connection.name()
            self.participantLeft.emit(nick)
            connection.deleteLater()





connections_to_servers = []

class PeerManager(QObject):

    newConnection = pyqtSignal(Connection)


    def __init__(self, client):
        super().__init__()

        self.client = client

        self.broadcastAddresses = []
        self.ipAddresses = []

        self.broadcastSocket = QUdpSocket()

        self.broadcastTimer = QTimer()
        self.username = ''
        self.serverPort = 0

        envVariables = ["USERNAME", "USER", "USERDOMAIN", "HOSTNAME", "DOMAINNAME"]
        for varname in envVariables:
            self.username = qEnvironmentVariable(varname)
            if self.username:
                break

        if not self.username:
            self.username = "unknown"

        self.updateAddresses()

        self.broadcastSocket.bind(QHostAddress.Any, BROADCASTPORT, QUdpSocket.ShareAddress | QUdpSocket.ReuseAddressHint)
        self.broadcastSocket.readyRead.connect(self.readBroadcastDatagram)

        self.broadcastTimer.setInterval(BROADCASTINTERVAL);
        self.broadcastTimer.timeout.connect(self.sendBroadcastDatagram)

        self.socket_buffer = bytes()
        self.readState = self.states.readSize
        self.SIZE_INT_SIZE = 4
        self.data_size = 0

    def setServerPort(self, port):
        self.serverPort = port

    def userName(self):
        return self.username 

    def startBroadcasting(self):
        self.broadcastTimer.start()

    def isLocalHostAddress(self, address):
        for localAddress in self.ipAddresses:
            if address.isEqual(localAddress):
                return True
        return False

    class states():
        readSize = 0
        readData = 1

    def parse_datagram(self):

        def slice_data(data, length):
            return data[:length], data[length:]

        # print('try read')

        # while len(self.socket_buffer) > 0:

        if True:

            if self.readState == self.states.readSize:
                if len(self.socket_buffer) >= self.SIZE_INT_SIZE:
                    data, self.socket_buffer = slice_data(self.socket_buffer, self.SIZE_INT_SIZE)
                    self.data_size = int.from_bytes(data, 'big')
                    self.readState = self.states.readData
                    # print('size read is', self.data_size)
                else:
                    pass
                    # print('not enough data to read the data size')

            # здесь обязательно, чтобы было if, и не было else if
            # это нужно для того, чтобы сразу прочитать данные,
            # если они уже есть и не ставить сообщение в очередь через emit
            if self.readState == self.states.readData:
                if self.data_size < 0:
                    raise Exception('Fuck!')
                if len(self.socket_buffer) >= self.data_size:
                    data, self.socket_buffer = slice_data(self.socket_buffer, self.data_size)
                    try:
                        parsed_data = cbor2.loads(data)
                        # print('data read')
                        self.data_size = 0
                        self.readState = self.states.readSize
                        return parsed_data
                    except Exception as e:
                        print(e, 'aborting...')
                        socket.abort()

                    print(parsed_data)

                else:
                    pass
                    # print('not enough data to read cbor data')

        return None

    def sendBroadcastDatagram(self):

        data_obj = [self.username, self.serverPort]
        datagram = prepare_data_to_write(data_obj)

        validBroadcastAddresses = True

        for address in self.broadcastAddresses[:]:
            if self.broadcastSocket.writeDatagram(datagram, address, BROADCASTPORT) == -1:
                validBroadcastAddresses = False

        if not validBroadcastAddresses:
            self.updateAddresses()

        # print('sendBroadcastDatagram ', datagram, self.username, self.serverPort, self.broadcastSocket.peerPort(), self.broadcastSocket.localPort())

    def readBroadcastDatagram(self):

        while self.broadcastSocket.hasPendingDatagrams():

            datagram = QByteArray()
            datagram.resize(self.broadcastSocket.pendingDatagramSize())
            datagram, senderIp, senderPort = self.broadcastSocket.readDatagram(datagram.size() )

            self.socket_buffer = datagram
            # print('socket_buffer', self.socket_buffer)
            parsed_data = self.parse_datagram()

            if parsed_data is None:
                continue

            senderServerPort = parsed_data[1]

            if self.isLocalHostAddress(senderIp) and senderServerPort == self.serverPort:
                continue

            if not self.client.hasConnection(senderIp):
                print('!!! new peer', senderServerPort, senderIp.toString())

                socket = QTcpSocket()
                socket.connectToHost(senderIp, senderServerPort)
                socket.waitForConnected()

                connection = Connection(self, client_socket=socket)

                global connections_to_servers
                connections_to_servers.append(connection)
                self.newConnection.emit(connection)



    def updateAddresses(self):
        self.broadcastAddresses.clear()
        self.ipAddresses.clear()
        interfaces = QNetworkInterface.allInterfaces()
        for interface in interfaces:
            entries = interface.addressEntries()
            for entry in entries:
                broadcastAddress = entry.broadcast()
                if broadcastAddress != QHostAddress.Null and entry.ip() != QHostAddress.LocalHost:
                    self.broadcastAddresses.append(broadcastAddress)
                    self.ipAddresses.append(entry.ip())


class ChatDialog(QDialog):

    def __init__(self, parent=None, *args, **kwargs):
        super().__init__()

        self.client = Client(self)

        self.myNickName = ''
        self.tableFormat = QTextTableFormat()

        uic.loadUi('chatdialog.ui', self) # Load the .ui file

        self.lineEdit.setFocusPolicy(Qt.StrongFocus)
        self.textEdit.setFocusPolicy(Qt.NoFocus)
        self.textEdit.setReadOnly(True)
        self.listWidget.setFocusPolicy(Qt.NoFocus)

        self.lineEdit.returnPressed.connect(self.returnPressed)
        self.client.newMessage.connect(self.appendMessage)
        self.client.newParticipant.connect(self.newParticipant)
        self.client.participantLeft.connect(self.participantLeft)

        self.myNickName = self.client.nickName()
        self.newParticipant(self.myNickName)

        self.tableFormat.setBorder(0);
        QTimer.singleShot(10 * 1000, self.showInformation)

    def appendMessage(self, _from, message):
        if (not _from) or (not message):
            return

        cursor = QTextCursor(self.textEdit.textCursor())
        cursor.movePosition(QTextCursor.End)
        table = cursor.insertTable(1, 2, self.tableFormat);
        table.cellAt(0, 0).firstCursorPosition().insertText('<' + _from + "> ")
        table.cellAt(0, 1).firstCursorPosition().insertText(message)
        bar = self.textEdit.verticalScrollBar()
        bar.setValue(bar.maximum())

    def returnPressed(self):
        text = self.lineEdit.text()
        if not text:
            return

        if text.startswith('/'):
            color = self.textEdit.textColor()
            self.textEdit.setTextColor(Qt.red)
            self.textEdit.append("! Unknown command: %s" % text.left(text.indexOf(' ')) )
            self.textEdit.setTextColor(color)
        else:
            self.client.sendMessage(text)
            self.appendMessage(self.myNickName, text)

        self.lineEdit.clear()

    def newParticipant(self, nick):
        if not nick:
            return

        color = self.textEdit.textColor()
        self.textEdit.setTextColor(Qt.gray)
        self.textEdit.append("* %s has joined" % nick)
        self.textEdit.setTextColor(color)
        self.listWidget.addItem(nick)

    def participantLeft(self, nick):
        if not nick:
            return
        items = self.listWidget.findItems(nick, Qt.MatchExactly)

        if not items:
            return
        self.listWidget.takeItem(self.listWidget.row(items[0]))

        color = self.textEdit.textColor()
        self.textEdit.setTextColor(Qt.gray)
        self.textEdit.append("* %s has left" % nick)
        self.textEdit.setTextColor(color)

    def showInformation(self):
        return
        # if self.listWidget.count() == 1:
        #     QMessageBox.information(self, "Chat", "Launch several instances of this program on your local network and start chatting!")


def main():
    app = QApplication(sys.argv)

    dialog = ChatDialog()
    dialog.show()

    app.exec()

if __name__ == '__main__':
    main()
