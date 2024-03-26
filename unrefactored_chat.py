


import sys
import time
import platform

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtNetwork import *

from PyQt5 import uic

import cbor2
import pyautogui


from _utils import (fit_rect_into_rect, )
from functools import partial


MaxBufferSize = 1024000

PongTimeout = 260 * 1000
PingInterval = 5 * 1000

# PingInterval = 1 * 1000
PingInterval = 500


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
    if capture_index == -1:
        capture_rect = QRect(QPoint(left, top), QPoint(right+1, bottom+1))
    else:
        capture_rect = QRect(QPoint(left, top), QPoint(right, bottom))

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






def prepare_data_to_write(serial_data, binary_attachment_data):
    if serial_data is not None:
        serial_binary = cbor2.dumps(serial_data)
        serial_length = len(serial_binary)
    else:
        serial_binary = b''
        serial_length = 0

    if binary_attachment_data is not None:
        bin_binary = binary_attachment_data
        bin_length = len(binary_attachment_data)
    else:
        bin_binary = b''
        bin_length = 0
    total_data_length = serial_length + bin_length
    header = total_data_length.to_bytes(INT_SIZE, 'big') + serial_length.to_bytes(INT_SIZE, 'big') + bin_length.to_bytes(INT_SIZE, 'big')
    data_to_sent = header + serial_binary + bin_binary

    # print('prepare_data_to_write', serial_data)

    return data_to_sent

def prepare_screenshot_to_transfer(capture_index):
    image, capture_rect = make_capture_frame(capture_index)

    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "jpg")

    capture_rect_tuple = [capture_rect.left(), capture_rect.top(), capture_rect.right(), capture_rect.bottom()]

    return prepare_data_to_write(capture_rect_tuple, byte_array.data())



def quit_app():
    app = QApplication.instance()
    app.quit()




class TransparentWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setWindowFlag(QtFramelessWindowHint)



class Viewer(QWidget):

    def __init__(self):
        super().__init__()
        self.image_to_show = None
        self.setMouseTracking(True)

        self.mouse_timer = QTimer()
        self.mouse_timer.setInterval(200)
        self.mouse_timer.timeout.connect(self.mouseTimerHandler)
        self.mouse_timer.start()


        self.animation_timer = QTimer()
        self.animation_timer.setInterval(100)
        self.animation_timer.timeout.connect(self.mouseAnimationTimerHandler)


        self.menuBar = QMenuBar(self)

        appMenu = self.menuBar.addMenu('Application')
        exitAction = QAction('Exit', self)
        exitAction.triggered.connect(quit_app)
        appMenu.addAction(exitAction)

        keyboard_send_actions_data = (
            ('Послать Ctrl+Alt+Del', ['ctrl', 'alt', 'del']),
            ('Послать Ctrl+Break', ['ctrl', 'break']),
            ('Послать Insert', ['insert']),
            ('Послать Print Screen', ['printscreen']),
        )
        keyboardMenu = self.menuBar.addMenu('Keyboard')


        def send_hotkey(hotkey_list):
            data_key = 'keyHotkey'
            key_data_dict = {DataType.KeyboardData: {data_key: hotkey_list}}
            self.connection.socket.write(prepare_data_to_write(key_data_dict, None))

        for text, args in keyboard_send_actions_data:
            action = QAction(text, self)
            action.triggered.connect(partial(send_hotkey, args))
            keyboardMenu.addAction(action)

        self.key_attr_names = {getattr(Qt, attrname): attrname for attrname in dir(Qt) if attrname.startswith('Key_')}
        self.keys_log = []

        # скопировано из документации
        self.allowed_pyautogui_args = [' ', '!', '"', '#', '$', '%', '&', "'", '(',
        ')', '*', '+', ',', '-', '.', '/', '0', '1', '2', '3', '4', '5', '6', '7',
        '8', '9', ':', ';', '<', '=', '>', '?', '@', '[', '\\', ']', '^', '_', '`',
        'a', 'b', 'c', 'd', 'e','f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o',
        'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z', '{', '|', '}', '~',
        'accept', 'add', 'alt', 'altleft', 'altright', 'apps', 'backspace',
        'browserback', 'browserfavorites', 'browserforward', 'browserhome',
        'browserrefresh', 'browsersearch', 'browserstop', 'capslock', 'clear',
        'convert', 'ctrl', 'ctrlleft', 'ctrlright', 'decimal', 'del', 'delete',
        'divide', 'down', 'end', 'enter', 'esc', 'escape', 'execute', 'f1', 'f10',
        'f11', 'f12', 'f13', 'f14', 'f15', 'f16', 'f17', 'f18', 'f19', 'f2', 'f20',
        'f21', 'f22', 'f23', 'f24', 'f3', 'f4', 'f5', 'f6', 'f7', 'f8', 'f9',
        'final', 'fn', 'hanguel', 'hangul', 'hanja', 'help', 'home', 'insert', 'junja',
        'kana', 'kanji', 'launchapp1', 'launchapp2', 'launchmail',
        'launchmediaselect', 'left', 'modechange', 'multiply', 'nexttrack',
        'nonconvert', 'num0', 'num1', 'num2', 'num3', 'num4', 'num5', 'num6',
        'num7', 'num8', 'num9', 'numlock', 'pagedown', 'pageup', 'pause', 'pgdn',
        'pgup', 'playpause', 'prevtrack', 'print', 'printscreen', 'prntscrn',
        'prtsc', 'prtscr', 'return', 'right', 'scrolllock', 'select', 'separator',
        'shift', 'shiftleft', 'shiftright', 'sleep', 'space', 'stop', 'subtract', 'tab',
        'up', 'volumedown', 'volumemute', 'volumeup', 'win', 'winleft', 'winright', 'yen',
        'command', 'option', 'optionleft', 'optionright']

        self.key_translate_error_duration = .4
        self.key_translate_error_timestamp = time.time() - self.key_translate_error_duration

    def isKeyTranslationErrorVisible(self):
        if time.time() - self.key_translate_error_timestamp < self.key_translate_error_duration:
            return True
        else:
            return False

    def keyTranslationErrorOpacity(self):
        value = 1.0 - (time.time() - self.key_translate_error_timestamp)/self.key_translate_error_duration
        value = min(1.0, value)
        value = max(0.0, value)
        return value

    def triggerKeyTranslationError(self):
        self.key_translate_error_timestamp = time.time()

    def translateQtKeyEventDataToPyautoguiArgumentValue(self, event):
        key = event.key()
        attr_name = self.key_attr_names.get(key)
        attr_name = attr_name[4:]
        attr_name = attr_name.lower()

        if attr_name in self.allowed_pyautogui_args:
            return attr_name
        elif event.text() in self.allowed_pyautogui_args:
            return event.text()
        elif event.key() == Qt.Key_Meta:
            return 'win'
        else:
            return None

    def addToKeysLog(self, status, key_attr_name):
        self.keys_log.insert(0, (status, key_attr_name))
        self.keys_log = self.keys_log[:20]
        self.update()

    def paintEvent(self, event):
        painter = QPainter()
        painter.begin(self)

        if self.image_to_show is not None:
            image_rect = self.image_to_show.rect()
            viewport_rect = self.get_viewport_rect()

            mapped_cursor_pos = self.mapFromGlobal(QCursor().pos())
            if viewport_rect.contains(mapped_cursor_pos):
                painter.setOpacity(1.0)
            else:
                painter.setOpacity(0.95)

            painter.drawImage(viewport_rect, self.image_to_show, image_rect)

        if self.isKeyTranslationErrorVisible():
            self.animation_timer.start()
            painter.setOpacity(self.keyTranslationErrorOpacity())

            r = viewport_rect
            painter.setBrush(Qt.NoBrush)
            MAX_COUNT = 50
            for i in range(MAX_COUNT):
                opacity = 255-int(i/MAX_COUNT*255)
                color = QColor(230, 50, 50, opacity)
                painter.setPen(QPen(color))
                painter.drawRect(r)
                r = r.adjusted(1, 1, -1, -1)
            painter.setOpacity(1.0)

        else:
            self.animation_timer.stop()

        font = painter.font()
        font.setPixelSize(20)
        painter.setFont(font)

        pos = self.rect().bottomLeft() + QPoint(20, -20)

        for n, log_entry in enumerate(self.keys_log):
            status, key_attr_name = log_entry
            if status == 'down':
                out = 'Зажата '
            elif status == 'up':
                out = 'Отпущена '
            if key_attr_name is not None:
                msg = out + key_attr_name[4:] + f' ({key_attr_name})'
            else:
                msg = out + str(key_attr_name)
            r = painter.boundingRect(QRect(), Qt.AlignLeft, msg)
            if n == 0:
                factor = 0
            else:
                factor = 1
            pos += QPoint(0, factor*-r.height())
            r.moveBottomLeft(pos)

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(Qt.black))
            painter.setOpacity(0.8)
            painter.drawRect(r)
            painter.setPen(Qt.white)
            painter.setOpacity(1.0)
            painter.drawText(pos, msg)

        painter.end()

    def get_viewport_rect(self):
        image_rect = self.image_to_show.rect()

        self_rect = self.rect()
        self_rect.setTop(self.menuBar.rect().height())

        return fit_rect_into_rect(image_rect, self_rect)

    def closeEvent(self, event):
        global viewer
        viewer = None

    def mouseTimerHandler(self):
        # передавать данные из mouseMoveEvent нельзя,
        # потому что он слишком часто триггерится и заваливает данными ведомое приложение,
        # по крайней мере на приложуха в виртуалке Linux захлёбывается
        if self.isViewportReadyAndCursorInsideViewport():
            x, y = self.mapViewportToClient()
            mouse_data_dict = {DataType.MouseData: {'mousePos': [x, y]}}
            self.connection.socket.write(prepare_data_to_write(mouse_data_dict, None))

    def mouseAnimationTimerHandler(self):
        self.update()

    def mapViewportToClient(self):
        mapped_cursor_pos = self.mapFromGlobal(QCursor().pos())
        viewport_rect = self.get_viewport_rect()
        x = mapped_cursor_pos.x()
        y = mapped_cursor_pos.y()

        # mapping from viewport to client capture rect
        viewport_pos = mapped_cursor_pos - viewport_rect.topLeft()
        norm_x = viewport_pos.x() / viewport_rect.width()
        norm_y = viewport_pos.y() / viewport_rect.height()
        # print(viewport_pos, norm_x, norm_y)
        x = int(norm_x*self.image_to_show.width())
        y = int(norm_y*self.image_to_show.height())
        return x, y

    def isViewportReadyAndCursorInsideViewport(self):
        if self.image_to_show is not None:
            mapped_cursor_pos = self.mapFromGlobal(QCursor().pos())
            viewport_rect = self.get_viewport_rect()
            if viewport_rect.contains(mapped_cursor_pos):
                return True
        return False

    def mouseMoveEvent(self, event):
        self.update()

    def mousePressEvent(self, event):
        if self.isViewportReadyAndCursorInsideViewport():
            if event.button() == Qt.LeftButton:
                data_key = 'mouseDownLeft'
            elif event.button() == Qt.RightButton:
                data_key = 'mouseDownRight'
            elif event.button() == Qt.MiddleButton:
                data_key = 'mouseDownMiddle'
            mouse_data_dict = {DataType.MouseData: {data_key: None}}
            self.connection.socket.write(prepare_data_to_write(mouse_data_dict, None))

    def mouseReleaseEvent(self, event):
        if self.isViewportReadyAndCursorInsideViewport():
            if event.button() == Qt.LeftButton:
                data_key = 'mouseUpLeft'
            elif event.button() == Qt.RightButton:
                data_key = 'mouseUpRight'
            elif event.button() == Qt.MiddleButton:
                data_key = 'mouseUpMiddle'
            mouse_data_dict = {DataType.MouseData: {data_key: None}}
            self.connection.socket.write(prepare_data_to_write(mouse_data_dict, None))

    def wheelEvent(self, event):
        scroll_value = event.angleDelta().y()/240
        data_key = 'mouseWheel'
        mouse_data_dict = {DataType.MouseData: {data_key: scroll_value}}
        self.connection.socket.write(prepare_data_to_write(mouse_data_dict, None))

    def sendKeyData(self, event, data_key):
        pyautogui_arg = self.translateQtKeyEventDataToPyautoguiArgumentValue(event)
        if pyautogui_arg:
            key_data_dict = {DataType.KeyboardData: {data_key: pyautogui_arg}}
            print(key_data_dict)
            self.connection.socket.write(prepare_data_to_write(key_data_dict, None))
        else:
            self.triggerKeyTranslationError()

    def keyPressEvent(self, event):
        key_name_attr = self.key_attr_names.get(event.key(), None)
        self.addToKeysLog('down', key_name_attr)
        self.sendKeyData(event, 'keyDown')

    def keyReleaseEvent(self, event):
        key_name_attr = self.key_attr_names.get(event.key(), None)
        self.addToKeysLog('up', key_name_attr)
        self.sendKeyData(event, 'keyUp')

def show_capture_window(image, capture_rect, connection):

    global viewer
    if viewer is None:
        viewer = Viewer()
        viewer.resize(capture_rect.width(), capture_rect.height())
        viewer.move(10, 10)
        viewer.show()

    viewer.image_to_show = image
    viewer.capture_rect = capture_rect
    viewer.connection = connection
    address = connection.socket.peerAddress().toString()
    title = f'Viewport for {address}'
    viewer.setWindowTitle(title)
    viewer.update()

class DataType:
    PlainText = 0
    Ping = 1
    Pong = 2
    Greeting = 3
    Undefined = 4
    MouseData = 5
    KeyboardData = 6




class Connection(QObject):

    readyForUse = pyqtSignal()
    newMessage = pyqtSignal(str, str)

    def deleteLater(self):
        if self.isGreetingMessageSent:
            if self.socket.isValid():
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
        self.currentDataType = DataType.Undefined
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
        self.socket.write(prepare_data_to_write({DataType.PlainText: message}, None))
        return True

    def processReadyRead(self):

        def retrieve_data(length):
            data = self.socket_buffer
            requested_data = data[:length]
            left_data = data[length:]
            self.socket_buffer = left_data
            return requested_data

        self.socket_buffer = self.socket_buffer + self.socket.read(max(2**10, self.content_data_size))

        self.data_full_to_read = True

        # while len(self.socket_buffer) > TCP_MESSAGE_HEADER_SIZE and self.data_full_to_read:
        if True:
            if self.readState == self.states.readSize:
                if len(self.socket_buffer) >= TCP_MESSAGE_HEADER_SIZE:
                    self.content_data_size = int.from_bytes(retrieve_data(INT_SIZE), 'big')
                    self.cbor2_data_size = int.from_bytes(retrieve_data(INT_SIZE), 'big')
                    self.binary_data_size = int.from_bytes(retrieve_data(INT_SIZE), 'big')
                    self.readState = self.states.readData
                    print('content_data_size', self.content_data_size, 'socket_buffer_size', len(self.socket_buffer))
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

                        capture_rect_coords = None

                        if cbor2_data:
                            parsed_data = cbor2.loads(cbor2_data)

                            if isinstance(parsed_data, dict):
                                self.currentDataType, value = list(parsed_data.items())[0]
                                if self.currentDataType == DataType.Greeting:

                                    addr = self.socket.peerAddress().toString()
                                    port = self.socket.peerPort()

                                    self.username = f'{value}@{addr}:{port}'

                                    if not self.isGreetingMessageSent:
                                        self.sendGreetingMessage()

                                    self.pingTimer.start()
                                    self.pongTime.start()
                                    self.readyForUse.emit()

                                elif self.currentDataType == DataType.PlainText:
                                    self.newMessage.emit(self.username, value)

                                elif self.currentDataType == DataType.Ping:
                                    self.socket.write(prepare_data_to_write({DataType.Pong: ''}, None))

                                elif self.currentDataType == DataType.Pong:
                                    self.pongTime.restart()

                                elif self.currentDataType == DataType.MouseData:

                                    mouse_data = value
                                    item = list(mouse_data.items())[0]
                                    mouse_type = item[0]
                                    mouse_value = item[1]

                                    if mouse_type == 'mousePos':
                                        x, y = mouse_value
                                        pyautogui.moveTo(x, y)

                                    elif mouse_type == 'mouseDownLeft':
                                        pyautogui.mouseDown(button='left')
                                    elif mouse_type == 'mouseUpLeft':
                                        pyautogui.mouseUp(button='left')

                                    elif mouse_type == 'mouseDownRight':
                                        pyautogui.mouseDown(button='right')
                                    elif mouse_type == 'mouseUpRight':
                                        pyautogui.mouseUp(button='right')

                                    elif mouse_type == 'mouseDownMiddle':
                                        pyautogui.mouseDown(button='middle')
                                    elif mouse_type == 'mouseUpMiddle':
                                        pyautogui.mouseUp(button='middle')

                                    elif mouse_type == 'mouseWheel':
                                        if mouse_value > 0:
                                            pyautogui.scroll(1)
                                        else:
                                            pyautogui.scroll(-1)

                                    print(mouse_data)

                                elif self.currentDataType == DataType.KeyboardData:
                                    keyboard_data = value
                                    item = list(keyboard_data.items())[0]
                                    event_type = item[0]
                                    key_value = item[1]

                                    if event_type == 'keyDown':
                                        pyautogui.keyDown(key_value)
                                    elif event_type == 'keyUp':
                                        pyautogui.keyUp(key_value)
                                    elif event_type == 'keyHotkey':
                                        pyautogui.hotkey(key_value)



                            else:
                                print(parsed_data)
                                capture_rect_coords = parsed_data

                        if binary_data:

                            input_byte_array = QByteArray(binary_data)
                            capture_image = QImage()
                            capture_image.loadFromData(input_byte_array, "jpg");
                            print(f'recieved image, {capture_image.size()}')

                            show_capture_window(capture_image, QRect(*capture_rect_coords), self)

                    except Exception as e:
                        raise
                        print(e, 'aborting...')
                        socket.abort()

                        if not self.socket.isValid():
                            self.socket.abort()
                            return


                    self.content_data_size = 0
                    self.readState = self.states.readSize

                else:
                    self.data_full_to_read = False
                    print('not enough data to read', len(self.socket_buffer), self.content_data_size)

        if self.data_full_to_read and len(self.socket_buffer) > TCP_MESSAGE_HEADER_SIZE:
            self.socket.readyRead.emit()

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
            self.socket.write(prepare_data_to_write({DataType.Ping: ''}, None))

    def sendGreetingMessage(self):
        self.socket.write(
            prepare_data_to_write({DataType.Greeting: self.greetingMessage}, None)
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


    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Escape:
            quit_app()


def main():
    app = QApplication(sys.argv)

    global chat_dialog
    chat_dialog = ChatDialog()
    chat_dialog.show()

    app.exec()

if __name__ == '__main__':
    main()
