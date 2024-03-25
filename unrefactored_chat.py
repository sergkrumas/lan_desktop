



from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtNetwork import *

from PyQt5 import uic
import sys
import time

import cbor2
import platform


from _utils import (fit_rect_into_rect, )



MaxBufferSize = 1024000

PongTimeout = 260 * 1000
PingInterval = 5 * 1000

PingInterval = 1 * 1000


BROADCASTINTERVAL = 2000
BROADCASTPORT = 45000


viewer = None

INT_SIZE = 4
TCP_MESSAGE_HEADER_SIZE = INT_SIZE*3


def make_capture_frame(capture_index):
    desktop = QDesktopWidget()
    MAX = 1000000000
    left = MAX
    right = -MAX
    top = MAX
    bottom = -MAX
    for i in range(0, desktop.screenCount()):
        if capture_index != -1:
            if i != capture_index:
                continue
        r = desktop.screenGeometry(screen=i)
        left = min(r.left(), left)
        right = max(r.right(), right)
        top = min(r.top(), top)
        bottom = max(r.bottom(), bottom)
    capture_rect = QRect(QPoint(left, top), QPoint(right+1, bottom+1))

    # print(capture_rect)
    qimage = QImage(
        capture_rect.width(),
        capture_rect.height(),
        QImage.Format_RGB32
    )
    qimage.fill(Qt.black)

    painter = QPainter()
    painter.begin(qimage)
    screens = QGuiApplication.screens()
    if capture_index == -1:
        for n, screen in enumerate(screens):
            p = screen.grabWindow(0)
            source_rect = QRect(QPoint(0, 0), screen.geometry().size())
            painter.drawPixmap(screen.geometry(), p, source_rect)
    else:
        for n, screen in enumerate(screens):
            if capture_index == n:
                painter.drawPixmap(QPoint(0, 0), screen.grabWindow(0))
                break
    painter.end()

    return qimage, capture_rect






def prepare_data_to_write(serial_data=None, binary_data=None):
    if serial_data is not None:
        serial_binary = cbor2.dumps(serial_data)
        serial_length = len(serial_binary)
    else:
        serial_binary = b''
        serial_length = 0

    if binary_data is not None:
        bin_binary = binary_data
        bin_length = len(binary_data)
    else:
        bin_binary = b''
        bin_length = 0
    total_data_length = serial_length + bin_length
    header = total_data_length.to_bytes(INT_SIZE, 'big') + serial_length.to_bytes(INT_SIZE, 'big') + bin_length.to_bytes(INT_SIZE, 'big')
    data_to_sent = header + serial_binary + bin_binary
    return data_to_sent

def prepare_screenshot_to_transfer(capture_index):
    image, capture_rect = make_capture_frame(capture_index)

    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "jpg")

    capture_rect_tuple = [capture_rect.left(), capture_rect.top(), capture_rect.right(), capture_rect.bottom()]

    return prepare_data_to_write(
            serial_data=capture_rect_tuple,
            binary_data=byte_array.data(),
    )


class Viewer(QWidget):

    def __init__(self):
        super().__init__()
        self.image_to_show = None

    def paintEvent(self, event):
        painter = QPainter()
        painter.begin(self)
        if self.image_to_show is not None:
            source_rect = self.image_to_show.rect()
            dest_rect = fit_rect_into_rect(source_rect, self.rect())
            painter.drawImage(dest_rect, self.image_to_show, source_rect)
        painter.end()

    def closeEvent(self, event):
        global viewer
        viewer = None

def show_screenshot_in_window(image):

    global viewer
    if viewer is None:
        viewer = Viewer()
        viewer.resize(1200, 900)
        viewer.move(10, 10)
        viewer.show()

    viewer.image_to_show = image
    viewer.update()



class Connection(QObject):


    class DataType:
        PlainText = 0
        Ping = 1
        Pong = 2
        Greeting = 3
        Undefined = 4

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

        self.content_data_size = 0
        self.cbor2_data_size = 0
        self.binary_data_size = 0

    def name(self):
        return self.username

    def setGreetingMessage(self, message):
        self.greetingMessage = message

    def sendMessage(self, message):
        if not message:
            return False
        self.socket.write(prepare_data_to_write(serial_data={self.DataType.PlainText: message}))
        return True

    def processReadyRead(self,):

        def retrieve_data(length):
            data = self.socket_buffer
            requested_data = data[:length]
            left_data = data[length:]
            self.socket_buffer = left_data
            return requested_data

        # print('try read')

        self.socket_buffer = self.socket_buffer + self.socket.read(max(2**10, self.content_data_size))

        if self.readState == self.states.readSize:
            if len(self.socket_buffer) >= TCP_MESSAGE_HEADER_SIZE:
                self.content_data_size = int.from_bytes(retrieve_data(INT_SIZE), 'big')
                self.cbor2_data_size = int.from_bytes(retrieve_data(INT_SIZE), 'big')
                self.binary_data_size = int.from_bytes(retrieve_data(INT_SIZE), 'big')
                self.readState = self.states.readData
                print('content_data_size', self.content_data_size)
                # print('size read', self.content_data_size)
            else:
                pass
                # print('not enough data to read the data size')

        # здесь обязательно, чтобы было if, и не было else if
        # это нужно для того, чтобы сразу прочитать данные,
        # если они уже есть и не ставить сообщение в очередь через emit
        if self.readState == self.states.readData:
            if self.content_data_size < 0:
                raise Exception('Fuck!')

            if len(self.socket_buffer) >= self.content_data_size:
                cbor2_data = retrieve_data(self.cbor2_data_size)
                binary_data = retrieve_data(self.binary_data_size)

                try:
                    if cbor2_data:
                        parsed_data = cbor2.loads(cbor2_data)

                        if isinstance(parsed_data, dict):
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
                                self.socket.write(prepare_data_to_write(serial_data={self.DataType.Pong: ''}))

                            elif self.currentDataType == self.DataType.Pong:
                                self.pongTime.restart()
                        else:
                            print(parsed_data)

                    if binary_data:

                        input_byte_array = QByteArray(binary_data)
                        image = QImage()
                        image.loadFromData(input_byte_array, "jpg");
                        print(f'recieved image, {image.size()}')
                        # filename = f'{time.time()}.jpg'
                        # image.save(filename)

                        show_screenshot_in_window(image)

                except Exception as e:
                    raise
                    print(e, 'aborting...')
                    socket.abort()



                self.content_data_size = 0
                self.readState = self.states.readSize

            else:
                print('not enough data to read', len(self.socket_buffer), self.content_data_size)

    def sendPing(self):
        if self.pongTime.elapsed() > PongTimeout:
            # self.abort()
            return

        if chat_dialog.remote_control_chb.isChecked():
            capture_index = chat_dialog.retrieve_capture_index()
            data = prepare_screenshot_to_transfer(capture_index)
            print(f'sending screenshot... message size: {len(data)}')
            self.socket.write(data)
        else:
            print('send ping')
            self.socket.write(prepare_data_to_write(serial_data={self.DataType.Ping: ''}))

    def sendGreetingMessage(self):
        self.socket.write(
            prepare_data_to_write(serial_data={self.DataType.Greeting: self.greetingMessage})
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


        def prepare_data_to_write(data_obj):
            data = cbor2.dumps(data_obj)
            data_length = len(data)
            data_to_sent = data_length.to_bytes(4, 'big') + data
            return data_to_sent

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

        # uic.loadUi('chatdialog.ui', self) # Load the .ui file


        self.setGeometry(0, 0, 1000, 349)
        self.setWindowTitle('Chat')

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(9, 9, 9, 9)
        main_layout.setSpacing(6)

        layout_h = QHBoxLayout()
        layout_h.setContentsMargins(0, 0, 0, 0)
        layout_h.setSpacing(6)
        main_layout.addLayout(layout_h)

        self.textEdit = QTextEdit()
        self.textEdit.setFocusPolicy(Qt.NoFocus)

        self.listWidget = QListWidget()
        self.listWidget.setMaximumSize(400, 2000)
        self.listWidget.setFocusPolicy(Qt.NoFocus)

        self.remote_control_chb = QCheckBox('Allow Remote Control')

        hor_layout = QHBoxLayout()
        hor_layout.addWidget(self.remote_control_chb)

        self.capture_combobox = QComboBox()

        desktop = QDesktopWidget()
        self.capture_combobox.addItem('Все', -1)
        for i in range(0, desktop.screenCount()):
            self.capture_combobox.addItem(f'Монитор {i+1}', i)
        # по дефолту выдаём содержимое первого монитора
        self.capture_combobox.setCurrentIndex(1)


        hor_layout.addWidget(self.capture_combobox)
        main_layout.addLayout(hor_layout)

        if platform.system() == 'Linux':
            self.remote_control_chb.setChecked(True)

        if True:
            splitter = QSplitter(Qt.Horizontal)
            splitter.addWidget(self.textEdit)
            splitter.addWidget(self.listWidget)
            layout_h.addWidget(splitter)
        else:
            layout_h.addWidget(self.textEdit)
            layout_h.addWidget(self.listWidget)

        layout_h2 = QHBoxLayout()
        layout_h2.setContentsMargins(0, 0, 0, 0)
        layout_h2.setSpacing(6)
        main_layout.addLayout(layout_h2)

        self.label = QLabel()
        self.label.setText('Message:')

        self.lineEdit = QLineEdit()
        self.setLayout(main_layout)
        layout_h2.addWidget(self.label)
        layout_h2.addWidget(self.lineEdit)




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

        rect = self.frameGeometry()
        rect.moveCenter(QDesktopWidget().availableGeometry().center())
        self.move(rect.topLeft())

    def retrieve_capture_index(self):
        index = self.capture_combobox.currentIndex()
        data = self.capture_combobox.itemData(index)
        return data

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

    global chat_dialog
    chat_dialog = ChatDialog()
    chat_dialog.show()

    app.exec()

if __name__ == '__main__':
    main()
