# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
#  Author: Sergei Krumas (github.com/sergkrumas)
#
# ##### END GPL LICENSE BLOCK #####



import sys
import os
import time
import platform
import json
from functools import partial
import hashlib
from collections import defaultdict, namedtuple
import builtins
import subprocess
import traceback
import locale
import ctypes
import webbrowser

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtNetwork import *

import cbor2
import pyautogui
from wakeonlan import send_magic_packet



from _utils import (fit_rect_into_rect, build_valid_rectF)
from update import do_update

try:
    from on_windows_startup import (is_app_in_startup, add_to_startup, remove_from_startup)
except:
    is_app_in_startup = None
    add_to_startup = None
    remove_from_startup = None

RegionInfo = namedtuple('RegionInfo', 'setter coords getter')

class Globals():

    DEBUG = True
    ENABLE_PRINT = False
    DEBUG_VIZ = False

    BROADCASTINTERVAL = 2000
    BROADCASTPORT = 45000

    SCREENSHOT_SENDING_INTERVAL = 40 # for 25 FPS

    file_sending_timers = []

    INT_SIZE = 4
    TCP_MESSAGE_HEADER_SIZE = INT_SIZE*3

    VERSION_INFO = "v0.1"
    AUTHOR_INFO = "by Sergei Krumas"

    IMAGE_FORMAT = 'jpg'
    peers_list_filename = f'peers_list_{platform.system()}.list'

    client_keys_logger = None

    last_reading = None
    last_writing = None

    OCCUPATO = False # remote control

    reading_framerate = ''
    writing_framerate = ''

    @classmethod
    def calculate_reading_framerate(cls):
        if cls.last_reading is not None:
            delta = (time.time() - cls.last_reading)*1000
            value = 1000/delta
            cls.reading_framerate = f'{value:.2f} FPS'
        cls.last_reading = time.time()
        return cls.reading_framerate

    @classmethod
    def calculate_writing_framerate(cls):
        if cls.last_writing is not None:
            delta = (time.time() - cls.last_writing)*1000
            value = 1000/delta
            cls.writing_framerate = f'{value:.2f} FPS'
        cls.last_writing = time.time()
        return cls.writing_framerate

    @classmethod
    def read_peers_list(cls):
        data = None
        if os.path.exists(Globals.peers_list_filename):
            with open(Globals.peers_list_filename, 'r', encoding='utf8') as file:
                data = file.read()
        data_dict = dict()
        if not data:
            data_dict = {}
        else:
            data_dict = json.loads(data)
        return data_dict

    @classmethod
    def update_peers_list(cls, addr, port, mac):
        data_dict = cls.read_peers_list()
        data_dict.update({addr: mac})
        data = json.dumps(data_dict)
        with open(Globals.peers_list_filename, 'w+', encoding='utf8') as file:
            file.write(data)

    @staticmethod
    def generate_circle_icon(color):
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.transparent)
        painter = QPainter()
        painter.begin(pixmap)
        painter.setRenderHint(QPainter.HighQualityAntialiasing, True)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(color))
        rect = QRect(0, 0, 14, 14)
        rect.moveCenter(pixmap.rect().center())
        painter.drawEllipse(rect)
        painter.end()
        return QIcon(pixmap)




def print(*args, **kwargs):
    if Globals.ENABLE_PRINT:
        builtins.print(*args, **kwargs)

class DataType:
    Undefined = 0
    PlainText = 1
    Greeting = 2
    InfoStatus = 3

    ScreenData = 10
    MouseData = 11
    KeyboardData = 12
    FileData = 13

    ControlFPS = 20
    ControlUserDefinedCaptureRect = 21
    ControlCaptureScreen = 22
    ControlRequest = 23

class ControlRequest:
    GiveMeControl = 0
    Occupato = 1
    Granted = 2
    Break = 3




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


def make_user_defined_capture_screenshot(capture_rect):
    desktop = QDesktopWidget()
    qimage = QImage(
        capture_rect.width(),
        capture_rect.height(),
        QImage.Format_RGB32
    )
    qimage.fill(Qt.black)

    painter = QPainter()
    painter.begin(qimage)
    screens = QGuiApplication.screens()
    for n, screen in enumerate(screens):
        screen_geometry = screen.geometry()
        if screen_geometry.intersects(capture_rect):
            screen_pixmap = screen.grabWindow(0)
            repos = screen_geometry.topLeft() - capture_rect.topLeft()
            screen_geometry.moveTopLeft(repos)
            source_rect = QRect(QPoint(0, 0), screen.geometry().size())
            painter.drawPixmap(screen_geometry, screen_pixmap, source_rect)
    painter.end()
    return qimage




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
    header = total_data_length.to_bytes(Globals.INT_SIZE, 'big') + serial_length.to_bytes(Globals.INT_SIZE, 'big') + bin_length.to_bytes(Globals.INT_SIZE, 'big')
    data_to_sent = header + serial_binary + bin_binary

    # print('prepare_data_to_write', serial_data)

    return data_to_sent




def prepare_screenshot_to_transfer(connection):

    if connection.capture_index == -2:
        capture_rect = connection.user_defined_capture_rect
        image = make_user_defined_capture_screenshot(capture_rect)
    else:
        screens_count = len(QGuiApplication.screens())
        if connection.capture_index+1 > screens_count:
            connection.capture_index = 0
        image, capture_rect = make_capture_frame(connection.capture_index)

    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    buffer.open(QIODevice.WriteOnly)
    # image.save(buffer, "jpg", quality=20)
    # image.save(buffer, "jpg")
    image.save(buffer, Globals.IMAGE_FORMAT, quality=50)

    capture_rect_tuple = [capture_rect.left(), capture_rect.top(), capture_rect.width(), capture_rect.height()]

    serial_data = {DataType.ScreenData: {
        'rect': capture_rect_tuple,
        'capture_index': connection.capture_index,
        'screens_count': len(QGuiApplication.screens()),
    }}

    return prepare_data_to_write(serial_data, byte_array.data())





def draw_key_log(self, painter):
    font = painter.font()
    font.setPixelSize(20)
    painter.setFont(font)

    pos = self.rect().bottomLeft() + QPoint(20, -20)

    for n, log_entry in enumerate(self.keys_log):
        status, key_value = log_entry
        if status == 'down':
            out = 'Зажата '
        elif status == 'up':
            out = 'Отпущена '
        if key_value is not None:
            if key_value.startswith('Key_'):
                key_name = key_value[4:]
            else:
                key_name = key_value

            msg = out + key_name + f' ({key_value})'
        else:
            msg = out + str(key_value)
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

class TransparentWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.keys_log = []

    def paintEvent(self, event):
        painter = QPainter()
        painter.begin(self)
        painter.fillRect(self.rect(), QColor(50, 50, 50, 200))
        draw_key_log(self, painter)
        painter.end()

    def addToKeysLog(self, status, key_attr_name):
        self.keys_log.insert(0, (status, key_attr_name))
        self.keys_log = self.keys_log[:20]
        self.update()

def show_screencast_keys_window(status, key_name):

    if chat_dialog.show_log_keys_chb.isChecked():
        if Globals.client_keys_logger is None:
            Globals.client_keys_logger = TransparentWidget()
            Globals.client_keys_logger.resize(400, 800)
            Globals.client_keys_logger.show()
            rect = Globals.client_keys_logger.geometry()
            desktop_widget = QDesktopWidget()
            # кладём окно аккурат над кнопкой «Пуск»
            rect.moveBottomLeft(desktop_widget.availableGeometry().bottomLeft())
            Globals.client_keys_logger.setGeometry(rect)

        Globals.client_keys_logger.addToKeysLog(status, key_name)
        Globals.client_keys_logger.update()






class Portal(QWidget):

    def __init__(self, parent):
        super().__init__(parent)

        self.update_timestamp = time.time()

        self.connection = None
        self.image_to_show = None

        self.is_grayed = False
        self.activated = False

        self.editing_mode = False
        self.show_log_keys = False

        self.disconnect = False
        self.before_client_screen_capture_rect = QRect()

        self.receiving_capture_index = 0

        self.canvas_scale_x = 1.0
        self.canvas_scale_y = 1.0

        self.key_translate_error_duration = .4
        self.key_translate_error_timestamp = time.time() - self.key_translate_error_duration


        self.input_POINT1 = None
        self.input_POINT2 = None
        self.user_defined_capture_rect = None

        self.user_input_started = False
        self.is_rect_defined = False
        self.is_rect_being_redefined = False

        self.undermouse_region_rect = None
        self.undermouse_region_info = None
        self.region_num = 0

        self.setMouseTracking(True)

        self.mouse_timer = QTimer()
        self.mouse_timer.setInterval(200)
        self.mouse_timer.timeout.connect(self.mouseTimerHandler)
        self.mouse_timer.start()

        self.animation_timer = QTimer()
        self.animation_timer.setInterval(100)
        self.animation_timer.timeout.connect(self.mouseAnimationTimerHandler)

        self.update_timer = QTimer()
        self.update_timer.setInterval(1000)
        self.update_timer.timeout.connect(self.update)
        self.update_timer.start()

        self.menuBar = QMenuBar(self)
        self.canvas_origin = QPoint(0, self.menuBar.height())

        keyboard_send_actions_data = (
            ('Послать Ctrl+Alt+Del', ['ctrl', 'alt', 'del']),
            ('Послать Ctrl+Break', ['ctrl', 'break']),
            ('Послать Insert', ['insert']),
            ('Послать Print Screen', ['printscreen']),
            ('Послать Alt+PrintScreen', ['alt', 'printscreen']),
            ('Послать Shift+Tab', ['shift', 'tab']),
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

        def toggle_(obj, attr_name):
            setattr(obj, attr_name, not getattr(obj, attr_name))
            self.update()

        viewMenu = self.menuBar.addMenu('View')
        action = QAction('Show keys log over viewport', self)
        action.setCheckable(True)
        action.setChecked(self.show_log_keys)
        action.triggered.connect(partial(toggle_, self, 'show_log_keys'))
        viewMenu.addAction(action)

        viewMenu.addSeparator()

        def send_contol_fps(value):
            if self.connection:
                self.connection.sendControlFPS(value)
                chat_dialog.appendSystemMessage(f'FPS is set to {value}')

        for fps_value in [25, 20, 15, 10, 5, 1, 0.5]:
            set_fps_action = QAction(f'Set FPS to {fps_value}', self)
            set_fps_action.triggered.connect(partial(send_contol_fps, fps_value))
            viewMenu.addAction(set_fps_action)

        viewMenu.addSeparator()
        reset_userdefined_capture = QAction('Reset user-defined capture region', self)
        reset_userdefined_capture.triggered.connect(self.reset_userdefined_capture)
        viewMenu.addAction(reset_userdefined_capture)

        fit_capture_to_portal = QAction('Fit capture to portal', self)
        fit_capture_to_portal.triggered.connect(self.fit_capture_to_portal)
        viewMenu.addAction(fit_capture_to_portal)

        self.monitorsMenu = self.menuBar.addMenu('Monitors')

        toggle_editing_mode = QAction('Editing Mode', self)
        toggle_editing_mode.setCheckable(True)
        toggle_editing_mode.setChecked(self.editing_mode)
        toggle_editing_mode.triggered.connect(partial(toggle_, self, 'editing_mode'))
        self.menuBar.addAction(toggle_editing_mode)

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

    def update_monitors_submenu(self, screens_count):
        if not self.monitorsMenu.isVisible():
            self.monitorsMenuUpdateTimestamp = time.time()
            self.monitorsMenu.clear()
            if screens_count == 0:
                return
            for i in range(-1, screens_count):
                if i == -1:
                    name = 'Capture all monitors'
                else:
                    number = i+1
                    name = f'Capture monitor #{number}'
                action = QAction(name, self)
                action.triggered.connect(partial(self.connection.sendControlCaptureScreen, i))
                self.monitorsMenu.addAction(action)

    def reset_userdefined_capture(self):
        reset_rect = QRect()
        self.connection.sendControlUserDefinedCaptureRect(reset_rect)

    def fit_capture_to_portal(self):
        if self.user_defined_capture_rect:
            self.fit_rect_to_widget_gabarit(self.get_viewport_rect(sub=True))
        else:
            self.fit_rect_to_widget_gabarit(self.get_viewport_rect())

    def fit_rect_to_widget_gabarit(self, viewport_mapped_rect):
        content_pos = viewport_mapped_rect.center() - self.canvas_origin

        viewport_center_pos = self.rect().center()
        working_area_rect = self.rect()

        self.canvas_origin = - content_pos + viewport_center_pos

        content_rect = viewport_mapped_rect

        fitted_rect = fit_rect_into_rect(content_rect, working_area_rect, float_mode=True)
        self.doScaleCanvas(0, False, False, False,
            pivot=viewport_center_pos,
            factor_x=fitted_rect.width()/content_rect.width(),
            factor_y=fitted_rect.height()/content_rect.height(),
        )
        self.update()

    def doScaleCanvas(self, scroll_value, ctrl, shift, no_mod,
                pivot=None, factor_x=None, factor_y=None, precalculate=False, canvas_origin=None, canvas_scale_x=None, canvas_scale_y=None):

        if pivot is None:
            pivot = self.mapFromGlobal(QCursor().pos())

        scale_speed = 10.0
        if scroll_value > 0:
            factor = scale_speed/(scale_speed-1)
        else:
            factor = (scale_speed-1)/scale_speed

        if factor_x is None:
            factor_x = factor

        if factor_y is None:
            factor_y = factor

        if ctrl:
            factor_x = factor
            factor_y = 1.0
        elif shift:
            factor_x = 1.0
            factor_y = factor

        _canvas_origin = canvas_origin if canvas_origin is not None else self.canvas_origin
        _canvas_scale_x = canvas_scale_x if canvas_scale_x is not None else self.canvas_scale_x
        _canvas_scale_y = canvas_scale_y if canvas_scale_y is not None else self.canvas_scale_y

        _canvas_scale_x *= factor_x
        _canvas_scale_y *= factor_y

        _canvas_origin -= pivot
        _canvas_origin = QPointF(_canvas_origin.x()*factor_x, _canvas_origin.y()*factor_y)
        _canvas_origin += pivot

        if precalculate:
            return _canvas_scale_x, _canvas_scale_y, _canvas_origin

        self.canvas_origin  = _canvas_origin
        self.canvas_scale_x = _canvas_scale_x
        self.canvas_scale_y = _canvas_scale_y

        self.update()

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

        SCANCODES_TO_ASCII = {
            16: 'Q',
            17: 'W',
            18: 'E',
            19: 'R',
            20: 'T',
            21: 'Y',
            22: 'U',
            23: 'I',
            24: 'O',
            25: 'P',
            30: 'A',
            31: 'S',
            32: 'D',
            33: 'F',
            34: 'G',
            35: 'H',
            36: 'J',
            37: 'K',
            38: 'L',
            44: 'Z',
            45: 'X',
            46: 'C',
            47: 'V',
            48: 'B',
            49: 'N',
            50: 'M',
            26: '[',
            27: ']',
            39: ';',
            40: '\'',
            43: '\\',
            51: ',',
            52: '.',
            53: '/',
        }
        ascii_text = SCANCODES_TO_ASCII.get(event.nativeScanCode(), None)
        chat_dialog.appendSystemMessage(ascii_text)
        key = event.key()
        attr_name = self.key_attr_names.get(key)
        if attr_name is None:
            if ascii_text is not None:
                return ascii_text.lower() #для поддержки русской раскладки и прочих отличных от дефолтной латинской
            return None
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

    def gray_received_image(self):
        if not self.is_grayed:


            # image = self.image_to_show.scaled(300, 300, Qt.KeepAspectRatio)
            # sizeImage = image.size()
            # width = sizeImage.width()
            # height = sizeImage.height()
            # for f1 in range(width):
            #     for f2 in range(height):
            #         color = image.pixel(f1, f2)
            #         gray = (qRed(color) + qGreen(color) + qBlue(color))/3
            #         gray = int(gray)
            #         image.setPixel(f1, f2, qRgb(gray, gray, gray))
            # self.image_to_show = image

            self.image_to_show = self.image_to_show.convertToFormat(QImage.Format_Grayscale16)



            self.is_grayed = True

    def drawMessageInCenter(self, painter, text):
        painter.save()
        align = Qt.AlignHCenter | Qt.AlignVCenter
        rect = painter.boundingRect(self.rect(), align, text)
        rect.adjust(-50, -50, 50, 50)

        color = QColor(200, 50, 50, 220)
        painter.setBrush(color)
        painter.setPen(QPen(Qt.red, 2))
        painter.drawRect(rect)
        painter.restore()
        painter.drawText(rect, align, text)


    def paintEvent(self, event):
        painter = QPainter()
        painter.begin(self)
        painter.setRenderHint(QPainter.HighQualityAntialiasing, True)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        painter.fillRect(self.rect(), Qt.black)

        if self.activated:
            WAIT_FOR_SCREENSHOT_SECONDS = 3 #seconds
            if time.time() - self.update_timestamp > WAIT_FOR_SCREENSHOT_SECONDS:
                self.disconnect = True
                self.gray_received_image()

            if self.image_to_show is not None:
                image_rect = self.image_to_show.rect()
                viewport_rect = self.get_viewport_rect()

                mapped_cursor_pos = self.mapFromGlobal(QCursor().pos())
                if viewport_rect.contains(mapped_cursor_pos):
                    painter.setOpacity(1.0)
                else:
                    painter.setOpacity(0.95)

                painter.drawImage(viewport_rect, self.image_to_show, image_rect)

                if self.user_defined_image_to_show:
                    client_screen_rect = self.user_defined_capture_rect.toRect()
                    sub_viewport_rect = self.get_viewport_rect(sub=True)
                    painter.drawImage(sub_viewport_rect,
                        self.user_defined_image_to_show,
                        self.user_defined_image_to_show.rect()
                    )
                    painter.setPen(Qt.red)
                    painter.drawRect(sub_viewport_rect)

            if self.disconnect:

                delta = int(time.time() - self.update_timestamp)
                text = f'Ведомый компьютер недоступен уже {delta} секунд.\nСкорее всего, связь потеряна.'
                self.drawMessageInCenter(painter, text)

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

            if self.show_log_keys:
                draw_key_log(self, painter)

            text = Globals.reading_framerate
            if not self.disconnect:
                if self.receiving_capture_index == -1:
                    text += '\nAll monitors'
                else:
                    number = self.receiving_capture_index + 1
                    text += f'\nMonitor number: {number}'

            align = Qt.AlignRight | Qt.AlignTop
            align  = 0
            rect = painter.boundingRect(QRect(), align, text)
            rect.moveTopRight(self.rect().topRight() + QPoint(-10, 10))

            painter.fillRect(rect, QColor(50, 50, 50, 150))

            painter.setPen(QPen(Qt.white))
            painter.drawText(rect, align, text)

        else:
            painter.fillRect(self.rect(), QColor(20, 20, 20, 255))
            self.drawMessageInCenter(painter, 'Portal is off')

        if self.editing_mode:
            painter.setPen(QPen(QColor(255, 50, 50), 3, Qt.DotLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))


            cursor_pos = self.mapFromGlobal(QCursor().pos())
            self.draw_vertical_horizontal_lines(painter, cursor_pos)
            self.draw_user_defined_capture_zone_info(painter)

        painter.end()

    def draw_user_defined_capture_zone_info(self, painter):
        if self.user_defined_capture_rect:
            painter.save()
            crr = self.user_defined_capture_rect.toRect()
            client_screen_rect = self.mapFromCanvasToClientScreen(crr)
            csr = client_screen_rect
            text = f'canvas rect: {crr.width()}x{crr.height()}\nclient screen rect: {csr.width()}x{csr.height()}'
            text += '\nEnter or Return - set user-defined capture region to remote computer and leave portal editing mode'
            align = Qt.AlignLeft | Qt.AlignBottom
            r = painter.boundingRect(QRect(), align, text)
            r.moveBottomLeft(self.mapToViewport(crr.bottomRight()).toPoint() + QPoint(5, -5))
            painter.drawText(r, align, text)
            painter.restore()

    def mapFromCanvasToClientScreen(self, canvas_rect):
        offset = self.monitor_capture_rect.topLeft()
        out = QRect(
            canvas_rect.topLeft() + offset,
            canvas_rect.bottomRight() + offset,
        )
        return out

    def draw_vertical_horizontal_lines(self, painter, cursor_pos):
        painter.save()
        line_pen = QPen(QColor(127, 127, 127, 172), 2, Qt.DashLine)
        painter.setCompositionMode(QPainter.RasterOp_SourceXorDestination)

        if self.is_input_points_set():
            painter.setPen(line_pen)
            input_POINT1 = self.mapToViewport(self.input_POINT1)
            input_POINT2 = self.mapToViewport(self.input_POINT2)
            left = input_POINT1.x()
            top = input_POINT1.y()
            right = input_POINT2.x()
            bottom = input_POINT2.y()
            # vertical left
            painter.drawLine(QPointF(left, 0), QPointF(left, self.height()))
            # horizontal top
            painter.drawLine(QPointF(0, top), QPointF(self.width(), top))
            # vertical right
            painter.drawLine(QPointF(right, 0), QPointF(right, self.height()))
            # horizontal bottom
            painter.drawLine(QPointF(0, bottom), QPointF(self.width(), bottom))
            if self.undermouse_region_rect and Globals.DEBUG_VIZ:
                painter.setBrush(QBrush(Qt.green, Qt.DiagCrossPattern))
                painter.drawRect(self.undermouse_region_rect)
        else:
            painter.setPen(line_pen)
            pos_x = cursor_pos.x()
            pos_y = cursor_pos.y()
            painter.drawLine(pos_x, 0, pos_x, self.height())
            painter.drawLine(0, pos_y, self.width(), pos_y)
        painter.restore()

    def get_viewport_rect(self, sub=False):

        if sub:
            image_rect = self.user_defined_image_to_show.rect()
        else:
            image_rect = self.image_to_show.rect()

        if self.canvas_scale_x == 0.0 or self.canvas_scale_y == 0.0:
            self.canvas_scale_x = 1.0
            self.canvas_scale_y = 1.0

        image_rect.setWidth(int(image_rect.width()*self.canvas_scale_x))
        image_rect.setHeight(int(image_rect.height()*self.canvas_scale_y))

        canvas_origin = QPointF(self.canvas_origin).toPoint()
        if sub:
            delta = (self.monitor_capture_rect.topLeft() - self.user_defined_capture_rect.toRect().topLeft())
            delta.setX(int(delta.x()*self.canvas_scale_x))
            delta.setY(int(delta.y()*self.canvas_scale_y))
            canvas_origin -= delta
        image_rect.moveTopLeft(canvas_origin)

        return image_rect

    def mouseTimerHandler(self):
        if not self.editing_mode:
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

        x = int(norm_x*self.monitor_capture_rect.width()) + self.monitor_capture_rect.left()
        y = int(norm_y*self.monitor_capture_rect.height()) + self.monitor_capture_rect.top()

        return x, y

    def define_regions_rects_and_set_cursor(self, write_data=True):

        if not self.user_defined_capture_rect:
            self.setCursor(Qt.ArrowCursor)
            return

        # --------------------------------- #
        # 1         |2          |3          #
        #           |           |           #
        # ----------x-----------x---------- #
        # 4         |5 (sel)    |6          #
        #           |           |           #
        # ----------x-----------x---------- #
        # 7         |8          |9          #
        #           |           |           #
        # --------------------------------- #

        touching_move_data = {
            1: ("setTopLeft",       "xy",   "topLeft"       ),
            2: ("setTop",           "y",    "top"           ),
            3: ("setTopRight",      "xy",   "topRight"      ),
            4: ("setLeft",          "x",    "left"          ),
            5: (None,               None,   None            ),
            6: ("setRight",         "x",    "right"         ),
            7: ("setBottomLeft",    "xy",   "bottomLeft"    ),
            8: ("setBottom",        "y",    "bottom"        ),
            9: ("setBottomRight",   "xy",   "bottomRight"   ),
        }
        regions_cursors = {
            1: QCursor(Qt.SizeFDiagCursor),
            2: QCursor(Qt.SizeVerCursor),
            3: QCursor(Qt.SizeBDiagCursor),
            4: QCursor(Qt.SizeHorCursor),
            5: QCursor(Qt.CrossCursor),
            6: QCursor(Qt.SizeHorCursor),
            7: QCursor(Qt.SizeBDiagCursor),
            8: QCursor(Qt.SizeVerCursor),
            9: QCursor(Qt.SizeFDiagCursor)
        }

        crr = self.mapToViewportRectF(self.user_defined_capture_rect)
        # amr = self._all_monitors_rect
        amr = self.rect()
        regions = {
            1: QRectF(QPointF(0, 0), crr.topLeft()),
            2: QRectF(QPointF(crr.left(), 0), crr.topRight()),
            3: QRectF(QPointF(crr.right(), 0), QPointF(amr.right(), crr.top())),
            4: QRectF(QPointF(0, crr.top()), crr.bottomLeft()),
            5: crr,
            6: QRectF(crr.topRight(), QPointF(amr.right(), crr.bottom())),
            7: QRectF(QPointF(0, crr.bottom()), QPointF(crr.left(), amr.bottom())),
            8: QRectF(crr.bottomLeft(), QPointF(crr.right(), amr.bottom())),
            9: QRectF(crr.bottomRight(), amr.bottomRight())
        }
        cursor_pos = self.mapFromGlobal(QCursor().pos())
        for number, rect in regions.items():
            if rect.contains(cursor_pos):
                self.undermouse_region_rect = rect
                self.region_num = number
                if write_data:
                    self.setCursor(regions_cursors[number])
                # чтобы не глитчили курсоры
                # на пограничных зонах прекращаем цикл
                break
        if write_data:
            if self.region_num == 5:
                self.undermouse_region_info = None
            else:
                data = touching_move_data[self.region_num]
                self.undermouse_region_info = RegionInfo(*data)

    def mapToViewportRectF(self, rect):
        rect = QRectF(
            self.mapToViewport(rect.topLeft()),
            self.mapToViewport(rect.bottomRight())
        )
        return rect

    def get_region_info(self):
        self.define_regions_rects_and_set_cursor()
        self.update()

    def isViewportReadyAndCursorInsideViewport(self):
        if self.image_to_show is not None and self.isActiveWindow():
            mapped_cursor_pos = self.mapFromGlobal(QCursor().pos())
            viewport_rect = self.get_viewport_rect()
            if viewport_rect.contains(mapped_cursor_pos):
                return True
        return False

    def is_point_set(self, p):
        return p is not None

    def get_first_set_point(self, points, default):
        for point in points:
            if self.is_point_set(point):
                return point
        return default

    def is_input_points_set(self):
        return self.is_point_set(self.input_POINT1) and self.is_point_set(self.input_POINT2)

    def build_input_rectF(self, cursor_pos):
        ip1 = self.get_first_set_point([self.input_POINT1], cursor_pos)
        ip2 = self.get_first_set_point([self.input_POINT2, self.input_POINT1], cursor_pos)
        return build_valid_rectF(ip1, ip2)

    def mapToCanvas(self, viewport_pos):
        delta = QPointF(viewport_pos - self.canvas_origin)
        canvas_pos = QPointF(delta.x()/self.canvas_scale_x, delta.y()/self.canvas_scale_y)
        return canvas_pos

    def mapToViewport(self, canvas_pos):
        scaled_rel_pos = QPointF(canvas_pos.x()*self.canvas_scale_x, canvas_pos.y()*self.canvas_scale_y)
        viewport_pos = self.canvas_origin + scaled_rel_pos
        return viewport_pos

    def move_capture_rect(self, delta):
        self.user_defined_capture_rect.moveCenter(self.current_capture_zone_center + delta)
        self.input_POINT1 = self.user_defined_capture_rect.topLeft()
        self.input_POINT2 = self.user_defined_capture_rect.bottomRight()

    def mouseMoveEvent(self, event):
        alt = event.modifiers() & Qt.AltModifier

        if not self.editing_mode:
            self.setCursor(Qt.ArrowCursor)

        if self.editing_mode:
            self.get_region_info()
            if event.buttons() == Qt.LeftButton:

                if self.drag_capture_zone:
                    delta = QPoint(event.pos() - self.ocp)
                    delta = QPointF(delta.x()/self.canvas_scale_x, delta.y()/self.canvas_scale_y)
                    self.move_capture_rect(delta.toPoint())

                else:
                    if not self.is_rect_defined:
                        # для первичного задания области захвата
                        event_pos = self.mapToCanvas(event.pos())
                        if not self.is_point_set(self.input_POINT1):
                            self.user_input_started = True
                            self.input_POINT1 = event_pos
                        else:
                            modifiers = event.modifiers()
                            if modifiers == Qt.NoModifier:
                                self.input_POINT2 = event_pos
                            else:
                                delta = self.input_POINT1 - event_pos
                                if modifiers & Qt.ControlModifier:
                                    delta.setX(delta.x() // 10 * 10 + 1)
                                    delta.setY(delta.y() // 10 * 10 + 1)
                                if modifiers & Qt.ShiftModifier:
                                    delta = self.equilateral_delta(delta)
                                self.input_POINT2 = self.input_POINT1 - delta

                    elif self.undermouse_region_info and not self.drag_inside_capture_zone:
                        # для изменения области захвата после первичного задания
                        self.is_rect_being_redefined = True
                        delta = self.mapToCanvas(QPointF(event.pos())) - self.start_cursor_position
                        set_func_attr = self.undermouse_region_info.setter
                        data_id = self.undermouse_region_info.coords
                        get_func_attr = self.undermouse_region_info.getter
                        get_func = getattr(self.user_defined_capture_rect, get_func_attr)
                        set_func = getattr(self.user_defined_capture_rect, set_func_attr)
                        if self.capture_redefine_start_value is None:
                            self.capture_redefine_start_value = get_func()
                        if data_id == "x":
                            set_func(self.capture_redefine_start_value + delta.x())
                        if data_id == "y":
                            set_func(self.capture_redefine_start_value + delta.y())
                        if data_id == "xy":
                            set_func(self.capture_redefine_start_value + delta)

                        # необходимо для нормальной работы
                        self.user_defined_capture_rect = build_valid_rectF(
                            self.user_defined_capture_rect.topLeft(), self.user_defined_capture_rect.bottomRight()
                        )

                        self.input_POINT1 = self.user_defined_capture_rect.topLeft()
                        self.input_POINT2 = self.user_defined_capture_rect.bottomRight()

            if event.buttons() == Qt.MiddleButton:
                delta = QPoint(event.pos() - self.ocp)
                self.canvas_origin = self.start_canvas_origin + delta

        self.update()

    def mousePressEvent(self, event):
        self.setFocus(Qt.MouseFocusReason)

        if self.editing_mode:
            if event.button() == Qt.LeftButton:

                isCaptureZone = self.user_defined_capture_rect is not None
                if isCaptureZone:
                    self.current_capture_zone_center = self.user_defined_capture_rect.center()
                    self.ocp = event.pos()
                    self.drag_capture_zone = True
                    return
                else:
                    self.drag_capture_zone = False

                self.start_cursor_position = self.mapToCanvas(QPointF(event.pos()))
                self.capture_redefine_start_value = None
                self.get_region_info()
                if self.undermouse_region_info is None:
                    self.drag_inside_capture_zone = True
                    if self.user_defined_capture_rect:
                        self.elementsMousePressEvent(event)
                else:
                    self.drag_inside_capture_zone = False

            if event.button() == Qt.MiddleButton:
                self.start_canvas_origin = QPointF(self.canvas_origin)
                self.ocp = event.pos()
                self.update()

        elif self.isViewportReadyAndCursorInsideViewport():
            data_key = 'mouseDown'
            if event.button() == Qt.LeftButton:
                mouse_button = 'left'
            elif event.button() == Qt.RightButton:
                mouse_button = 'right'
            elif event.button() == Qt.MiddleButton:
                mouse_button = 'middle'
            mouse_data_dict = {DataType.MouseData: {data_key: mouse_button}}
            self.connection.socket.write(prepare_data_to_write(mouse_data_dict, None))

    def mouseReleaseEvent(self, event):
        alt = event.modifiers() & Qt.AltModifier
        if self.editing_mode:
            if event.button() == Qt.LeftButton:

                if self.drag_capture_zone:
                    self.drag_capture_zone = False
                else:
                    if self.drag_inside_capture_zone:
                        self.drag_inside_capture_zone = False
                        if self.is_rect_defined:
                            pass
                    if self.user_input_started:
                        if not self.is_input_points_set():
                            # это должно помочь от крашей
                            self.user_input_started = False
                            self.input_POINT1 = None
                            self.input_POINT2 = None
                            return
                        self.is_rect_defined = True
                        self.user_defined_capture_rect = build_valid_rectF(self.input_POINT1, self.input_POINT2)
                        self.is_rect_being_redefined = False
                    self.get_region_info() # здесь только для установки курсора



        elif self.isViewportReadyAndCursorInsideViewport():
            data_key = 'mouseUp'
            if event.button() == Qt.LeftButton:
                mouse_button = 'left'
            elif event.button() == Qt.RightButton:
                mouse_button = 'right'
            elif event.button() == Qt.MiddleButton:
                mouse_button = 'middle'
            mouse_data_dict = {DataType.MouseData: {data_key: mouse_button}}
            self.connection.socket.write(prepare_data_to_write(mouse_data_dict, None))

    def wheelEvent(self, event):
        scroll_value = event.angleDelta().y()/240
        if self.editing_mode:
            ctrl = event.modifiers() & Qt.ControlModifier
            shift = event.modifiers() & Qt.ShiftModifier
            alt = event.modifiers() & Qt.AltModifier
            no_mod = event.modifiers() == Qt.NoModifier
            self.doScaleCanvas(scroll_value, ctrl, shift, no_mod)
        else:
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
        if self.editing_mode:
            pass
        else:
            key_name_attr = self.key_attr_names.get(event.key(), None)
            self.addToKeysLog('down', key_name_attr)
            self.sendKeyData(event, 'keyDown')

    def keyReleaseEvent(self, event):
        if self.editing_mode:
            if event.key() in [Qt.Key_Enter, Qt.Key_Return]:
                if self.user_defined_capture_rect is not None:
                    rect = self.mapFromCanvasToClientScreen(self.user_defined_capture_rect.toRect())
                    self.connection.sendControlUserDefinedCaptureRect(rect)
                    self.editing_mode = False
                else:
                    chat_dialog.appendSystemMessage('You haven\'t defined the capture area!')
        else:
            key_name_attr = self.key_attr_names.get(event.key(), None)
            self.addToKeysLog('up', key_name_attr)
            self.sendKeyData(event, 'keyUp')

    def close_portal(self):
        self.connection = None
        self.user_defined_image_to_show = None
        self.image_to_show = None
        self.activated = False
        self.is_grayed = False
        self.update_monitors_submenu(0)

def show_in_portal(image, capture_index, screens_count, client_screen_capture_rect, connection):

    portal = chat_dialog.portal_widget
    portal.connection = connection
    portal.update_timestamp = time.time()

    if capture_index == -2:
        portal.user_defined_image_to_show = image
        portal.gray_received_image()
    else:
        portal.image_to_show = image
        portal.user_defined_image_to_show = None
        portal.monitor_capture_rect = client_screen_capture_rect
        portal.is_grayed = False

    portal.receiving_capture_index = capture_index
    portal.update_monitors_submenu(screens_count)

    portal.activated = True
    portal.update()


    if portal.before_client_screen_capture_rect != client_screen_capture_rect:
        portal.before_client_screen_capture_rect = client_screen_capture_rect
        portal.fit_capture_to_portal()



class SendFileTimer(QTimer):
    def __init__(self, filepath):
        super().__init__()
        Globals.file_sending_timers.append(self)
        self.CHUNK_SIZE = 200000
        self.fileobj = open(filepath, 'rb')
        self.fileobj.seek(0, 2) # move the cursor to the end of the file
        self.filesize = self.fileobj.tell()
        self.fileobj.seek(0, 0)
        self.filename = os.path.basename(filepath)
        self.setInterval(200)
        self.md5_hash = self.generate_md5(filepath)
        self.timeout.connect(self.sendFileChunk)
        self.start()

    @staticmethod
    def generate_md5(filepath):
        hash_md5 = hashlib.md5()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        md5_str = hash_md5.hexdigest()
        return md5_str

    def sendFileChunk(self):
        filechunk = self.fileobj.read(self.CHUNK_SIZE)

        if filechunk:
            chunk_info = {
                'md5_hash': self.md5_hash,
                'total_size': self.filesize,
                'filename': self.filename,
                'chunk_size': len(filechunk),
            }
            serial_data = {DataType.FileData: chunk_info}
            binary_data = filechunk


            for conn in chat_dialog.client.get_peers_connections():
                msg = f'Отправляется часть файла {self.filename}' + \
                            f' размером {len(filechunk)} байт' + \
                            f' на адрес {conn.socket.peerAddress().toString()}'
                chat_dialog.appendSystemMessage(msg)

                conn.socket.write(prepare_data_to_write(serial_data, binary_data))

        else:
            self.stop()
            if self in Globals.file_sending_timers:
                Globals.file_sending_timers.remove(self)

def send_files(paths):
    for path in paths:
        SendFileTimer(path)

receiving_files = defaultdict(int)
receiving_files_objs = defaultdict(None)

def write_file_chunk_data(file_chunk_info, binary_data, peer_address_string):

    md5_hash = file_chunk_info['md5_hash']
    total_size = file_chunk_info['total_size']
    filename = file_chunk_info['filename']
    chunk_size = file_chunk_info['chunk_size']

    chat_dialog.appendSystemMessage(f'От {peer_address_string} получена часть файла {filename}, размер которой {chunk_size}')

    global receiving_files
    if md5_hash not in receiving_files:
        receiving_files_objs[md5_hash] = open(md5_hash, 'wb')

    file_obj = receiving_files_objs[md5_hash]

    receiving_files[md5_hash] += chunk_size

    file_obj.write(binary_data)

    if receiving_files[md5_hash] >= total_size:
        receiving_files.pop(md5_hash)
        receiving_files_objs.pop(md5_hash)
        file_obj.close()

        rename_success = False
        # Linux на виртуалке не успевает к этому времени закончить операции с файлом
        # и приходится пробовать несколько раз
        while not rename_success:
            try:
                os.rename(md5_hash, filename)
                rename_success = True
            except:
                pass
            time.sleep(1)

        chat_dialog.appendSystemMessage(f'От {peer_address_string} получен весь файл {filename}, размер которого {total_size}', bold=True)





class Connection(QObject):

    readyForUse = pyqtSignal()
    newMessage = pyqtSignal(str, str)

    def deleteLater(self):
        # сокет уже удалён к этому времени и это только даёт эксепшен при закрытии приложения
        # if self.isGreetingMessageSent:
        #     if self.socket.isValid():
        #         self.socket.waitForBytesWritten(2000)
        super().deleteLater()

    class states():
        readSize = 0
        readData = 1

    def __init__(self, parent, client_socket=None):
        super().__init__()

        self.socket = client_socket

        self.greetingMessage = 888
        self.username = 'unknown'
        self.screenshotTimer = QTimer()

        self.buffer = ''

        self.screenshotTimer.setInterval(Globals.SCREENSHOT_SENDING_INTERVAL)
        self.currentDataType = DataType.Undefined
        self.isGreetingMessageSent = False

        self.socket.readyRead.connect(self.processReadyRead)
        self.socket.disconnected.connect(self.screenshotTimer.stop)
        self.screenshotTimer.timeout.connect(self.sendScreenshot)
        self.socket.connected.connect(self.sendGreetingMessage)

        self.socket_buffer = bytes()
        self.readState = self.states.readSize

        self.content_data_size = 0
        self.cbor2_data_size = 0
        self.binary_data_size = 0

        # -2 - user defined capture region
        # -1 - all monitors
        #  0 - first monitor
        #  1 - second monitor
        #  2 - third monitor etc
        self.capture_index = 0
        self.user_defined_capture_rect = None
        self.before_user_defined_capture_index = None

        self.status = ''

        self.control_connection = False

    def remove_occupato_flag_if_needed(self):
        if self.control_connection:
            Globals.OCCUPATO = False

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

        self.socket_buffer = self.socket_buffer + self.socket.read(200000)

        self.data_full_to_read = True

        # while len(self.socket_buffer) > Globals.TCP_MESSAGE_HEADER_SIZE and self.data_full_to_read:
        if True:
            if self.readState == self.states.readSize:
                if len(self.socket_buffer) >= Globals.TCP_MESSAGE_HEADER_SIZE:
                    self.content_data_size = int.from_bytes(retrieve_data(Globals.INT_SIZE), 'big')
                    self.cbor2_data_size = int.from_bytes(retrieve_data(Globals.INT_SIZE), 'big')
                    self.binary_data_size = int.from_bytes(retrieve_data(Globals.INT_SIZE), 'big')
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

                        screen_info = None
                        file_chunk_info = None

                        if cbor2_data:
                            parsed_data = cbor2.loads(cbor2_data)

                            if isinstance(parsed_data, dict):
                                self.currentDataType, value = list(parsed_data.items())[0]
                                if self.currentDataType == DataType.Greeting:

                                    msg = value['msg']
                                    mac = value['mac']
                                    status = value['status']

                                    addr = self.socket.peerAddress().toString()
                                    port = self.socket.peerPort()

                                    Globals.update_peers_list(addr, port, mac)

                                    self.username = f'{msg}@{addr}:{port} // {mac}'

                                    if not self.isGreetingMessageSent:
                                        self.sendGreetingMessage()

                                    self.readyForUse.emit()

                                    # status update
                                    self.status = status
                                    chat_dialog.newParticipant(self.name(), self)

                                elif self.currentDataType == DataType.ControlRequest:

                                    if value == ControlRequest.GiveMeControl:
                                        if Globals.OCCUPATO:
                                            self.sendControlRequestAnswer(ControlRequest.Occupato)
                                        else:
                                            self.control_connection = True
                                            Globals.OCCUPATO = True
                                            self.sendControlRequestAnswer(ControlRequest.Granted)
                                            self.screenshotTimer.start()

                                    elif value == ControlRequest.Granted:
                                        chat_dialog.prepare_portal()

                                    elif value == ControlRequest.Occupato:
                                        chat_dialog.appendSystemMessage('Error: remote host occupato!')

                                    elif value == ControlRequest.Break:
                                        if self.control_connection:
                                            Globals.OCCUPATO = False
                                            self.control_connection = False
                                            self.screenshotTimer.stop()
                                            self.sendControlRequestAnswer(ControlRequest.Break)
                                        else:
                                            chat_dialog.portal_off()

                                elif self.currentDataType == DataType.InfoStatus:
                                    new_status = value
                                    chat_dialog.appendSystemMessage(f'Peer changed status from {self.status} to {new_status}')
                                    self.status = new_status
                                    chat_dialog.newParticipant(self.name(), self)

                                elif self.currentDataType == DataType.PlainText:
                                    self.newMessage.emit(self.username, value)

                                elif self.currentDataType == DataType.MouseData:

                                    if self.control_connection:
                                        mouse_data = value
                                        item = list(mouse_data.items())[0]
                                        mouse_type = item[0]
                                        mouse_value = item[1]

                                        mouse_button = mouse_value
                                        if mouse_type == 'mousePos':
                                            x, y = mouse_value
                                            try:
                                                pyautogui.moveTo(x, y)
                                            except:
                                                pass

                                        elif mouse_type == 'mouseDown':
                                            pyautogui.mouseDown(button=mouse_button)
                                        elif mouse_type == 'mouseUp':
                                            pyautogui.mouseUp(button=mouse_button)
                                            show_screencast_keys_window('up', mouse_button)

                                        elif mouse_type == 'mouseWheel':
                                            if mouse_value > 0:
                                                pyautogui.scroll(1)
                                                show_screencast_keys_window('up', "wheel up")
                                            else:
                                                pyautogui.scroll(-1)
                                                show_screencast_keys_window('up', "wheel down")

                                        print(mouse_data)

                                elif self.currentDataType == DataType.KeyboardData:

                                    if self.control_connection:
                                        keyboard_data = value
                                        item = list(keyboard_data.items())[0]
                                        event_type = item[0]
                                        key_value = item[1]

                                        if event_type == 'keyDown':
                                            pyautogui.keyDown(key_value)
                                        elif event_type == 'keyUp':
                                            pyautogui.keyUp(key_value)
                                            show_screencast_keys_window('up', key_value)
                                        elif event_type == 'keyHotkey':
                                            pyautogui.hotkey(key_value)
                                            show_screencast_keys_window('up', "+".join(key_value))

                                elif self.currentDataType == DataType.FileData:
                                    file_chunk_info = value


                                elif self.currentDataType == DataType.ControlFPS:
                                    if self.control_connection:
                                        fps = value['fps']
                                        chat_dialog.appendSystemMessage(f'Remote host wants {fps} FPS')
                                        self.screenshotTimer.setInterval(int(1000/fps))

                                elif self.currentDataType == DataType.ControlUserDefinedCaptureRect:

                                    if self.control_connection:
                                        if self.capture_index != -2:
                                            self.before_user_defined_capture_index = self.capture_index
                                        rect = value['rect']
                                        rect = QRect(*rect)
                                        if rect.isNull():
                                            self.capture_index = self.before_user_defined_capture_index
                                            self.user_defined_capture_rect = None
                                            chat_dialog.appendSystemMessage(f'Remote host wants to reset user-defined capture rect')
                                        else:
                                            self.capture_index = -2
                                            self.user_defined_capture_rect = rect
                                            chat_dialog.appendSystemMessage(f'Remote host wants to set user-defined capture rect {rect}')

                                elif self.currentDataType == DataType.ScreenData:
                                    screen_info = value

                                elif self.currentDataType == DataType.ControlCaptureScreen:
                                    if self.control_connection:
                                        capture_index = value
                                        count = len(QGuiApplication.screens())
                                        if capture_index > count-1:
                                            chat_dialog.appendSystemMessage(f'Remote host wants to capture screen number {capture_index+1}, BUT THERE ARE ONLY {count} SCREENS!')
                                        else:
                                            self.capture_index = capture_index
                                            chat_dialog.appendSystemMessage(f'Remote host wants to capture screen number {capture_index+1}')

                                else:
                                    chat_dialog.appendSystemMessage(f'Пришла какая-то непонятная хуйня {parsed_data}')


                            else:
                                chat_dialog.appendSystemMessage(f'Пришла какая-то непонятная хуйня, да и ещё без заголовка {parsed_data}')

                        if binary_data:

                            if screen_info:
                                input_byte_array = QByteArray(binary_data)
                                capture_image = QImage()
                                capture_image.loadFromData(input_byte_array, Globals.IMAGE_FORMAT);
                                print(f'received image, {len(binary_data)}, {capture_image.size()}')

                                capture_rect_tuple = screen_info.get('rect', None)
                                capture_index = screen_info.get('capture_index', None)
                                screens_count = screen_info.get('screens_count', None)

                                show_in_portal(capture_image, capture_index, screens_count, QRect(*capture_rect_tuple), self)


                                value = Globals.calculate_reading_framerate()
                                text = f'reading image framerate: {value}'
                                chat_dialog.framerate_label.setText(text)



                            elif file_chunk_info:
                                write_file_chunk_data(file_chunk_info, binary_data, self.socket.peerAddress().toString())


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

        if self.data_full_to_read and len(self.socket_buffer) > Globals.TCP_MESSAGE_HEADER_SIZE:
            self.socket.readyRead.emit()

    def sendScreenshot(self):

        if chat_dialog.remote_control_chb.isChecked() and self.control_connection:
            data = prepare_screenshot_to_transfer(self)
            print(f'sending screenshot... message size: {len(data)}')
            self.socket.write(data)
            self.socket.flush()


            value = Globals.calculate_writing_framerate()
            text = f'sending picture framerate: {value}'
            chat_dialog.framerate_label.setText(text)

    def sendGreetingMessage(self):
        peer_address_string = self.socket.peerAddress().toString()
        local_address_string = self.socket.localAddress().toString()

        mac_address = find_mac_for_local_socket_addr(local_address_string)
        msg = f'i\'m {local_address_string} sending greetings message to {peer_address_string}'

        chat_dialog.appendSystemMessage(msg)
        status = chat_dialog.retrieve_status()
        self.socket.write(
            prepare_data_to_write({DataType.Greeting: {'msg': self.greetingMessage, 'mac': mac_address, 'status': status}}, None)
        )
        self.isGreetingMessageSent = True

    def sendControlFPS(self, value):
        data = prepare_data_to_write({DataType.ControlFPS: {'fps': value}}, None)
        self.socket.write(data)

    def sendControlUserDefinedCaptureRect(self, rect_value):
        rect_tuple = (rect_value.left(), rect_value.top(), rect_value.width(), rect_value.height())
        data = prepare_data_to_write({DataType.ControlUserDefinedCaptureRect: {'rect': rect_tuple}}, None)
        self.socket.write(data)

    def sendControlCaptureScreen(self, capture_index):
        data = prepare_data_to_write({DataType.ControlCaptureScreen: capture_index}, None)
        self.socket.write(data)

    def sendStatus(self, status):
        data = prepare_data_to_write({DataType.InfoStatus: status}, None)
        self.socket.write(data)

    def requestControlPortal(self):
        data = prepare_data_to_write({DataType.ControlRequest: ControlRequest.GiveMeControl}, None)
        self.socket.write(data)

    def sendControlRequestAnswer(self, value):
        data = prepare_data_to_write({DataType.ControlRequest: value}, None)
        self.socket.write(data)

def find_mac_for_local_socket_addr(local_address_string):
    for ip_addr, mac in retrieve_ip_mac_pairs():
        if local_address_string.endswith(ip_addr):
            return mac
    return 'Fuck! This is a disaster! MAC not found!'


def retrieve_ip_mac_pairs():
    ip_mac_pairs = []
    interfaces = QNetworkInterface.allInterfaces()
    for interface in interfaces:
        entries = interface.addressEntries()

        current_ip = None
        for entry in entries:
            broadcastAddress = entry.broadcast()
            if broadcastAddress != QHostAddress.Null and entry.ip() != QHostAddress.LocalHost:
                current_ip = entry.ip()

        if not interface.flags() & QNetworkInterface.IsLoopBack:
            ip_mac_pairs.append((current_ip.toString(), interface.hardwareAddress()))

    return ip_mac_pairs



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

        socket_info_to_chat('new user has knocked', client_socket)

        self.new_connection_handler(connection)

        clients_connections.append(connection)


class Client(QObject):

    newMessage = pyqtSignal(str, str)
    newParticipant = pyqtSignal(str, object)
    participantLeft = pyqtSignal(str)

    def __init__(self, *args):
        super().__init__(*args)

        self.peers = dict()
        self.peerManager = PeerManager(self)

        self.server = MessageServer(self, self.newConnection)
        self.peerManager.setServerPort(self.server.serverPort())
        self.peerManager.startBroadcasting()

        self.peerManager.newConnection.connect(self.newConnection)


    def get_peers_connections(self):
        return [item[1] for item in self.peers.items()]

    def sendStatusToPeers(self, status):
        for addr, connection in self.peers.items():
            connection.sendStatus(status)

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
            self.newParticipant.emit(nick, connection)

    def removeConnection(self, socket):
        if socket.peerAddress() in self.peers.keys():
            connection = self.peers.pop(socket.peerAddress())
            nick = connection.name()
            self.participantLeft.emit(nick)
            connection.remove_occupato_flag_if_needed()
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

        self.broadcastSocket.bind(QHostAddress.Any, Globals.BROADCASTPORT, QUdpSocket.ShareAddress | QUdpSocket.ReuseAddressHint)
        self.broadcastSocket.readyRead.connect(self.readBroadcastDatagram)

        self.broadcastTimer.setInterval(Globals.BROADCASTINTERVAL);
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
            if self.broadcastSocket.writeDatagram(datagram, address, Globals.BROADCASTPORT) == -1:
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
                socket_info_to_chat('new peer added', socket)


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


def socket_info_to_chat(intro, socket):
    send_size = socket.socketOption(QAbstractSocket.SendBufferSizeSocketOption)
    receive_size = socket.socketOption(QAbstractSocket.ReceiveBufferSizeSocketOption)
    buffer_size = socket.readBufferSize()

    msg1 = f'1 {intro}, receive buffer {receive_size} bytes, send buffer {send_size} bytes, buffer size {buffer_size}'

    socket.setSocketOption(QAbstractSocket.SendBufferSizeSocketOption, 200000)
    socket.setSocketOption(QAbstractSocket.ReceiveBufferSizeSocketOption, 200000)

    socket.setSocketOption(QAbstractSocket.LowDelayOption, 1)
    socket.setReadBufferSize(157000)

    # Immediate = 64
    Network_control = 224
    socket.setSocketOption(QAbstractSocket.TypeOfServiceOption, Network_control)

    send_size = socket.socketOption(QAbstractSocket.SendBufferSizeSocketOption)
    receive_size = socket.socketOption(QAbstractSocket.ReceiveBufferSizeSocketOption)
    buffer_size = socket.readBufferSize()

    msg2 = f'2 {intro}, receive buffer {receive_size} bytes, send buffer {send_size} bytes, buffer size {buffer_size}'

    local_address_string = socket.localAddress().toString()
    peer_address_string = socket.peerAddress().toString()
    msg3 = f'socket local address {local_address_string}, socket peer address {peer_address_string}'

    msg = '\n'.join((msg1, msg2, msg3))
    chat_dialog.appendSystemMessage(msg)


class ChatDialog(QDialog):

    def handle_windows_startup_chbx(self, status):
        if status:
            add_to_startup(*self.STARTUP_CONFIG)
        else:
            remove_from_startup(self.STARTUP_CONFIG[0])

    def go_to_app_page(self):
        webbrowser.open("https://github.com/sergkrumas/lan_desktop")

    def __init__(self, parent=None, *args, **kwargs):
        super().__init__()

        self.client = Client(self)

        self.STARTUP_CONFIG = (
            'lan_desktop_explorer_launcher',
            os.path.join(os.path.dirname(__file__), "lan_desktop.py")
        )

        self.disconnect_data = None

        self.myNickName = ''
        self.tableFormat = QTextTableFormat()

        self.show_log_keys = False

        self.setWindowTitle('Chat')

        self.menuBar = QMenuBar(self)
        self.menuBar.setMinimumSize(300, self.menuBar.height())
        appMenu = self.menuBar.addMenu('Application')

        updateAppAction = QAction('Update', self)
        updateAppAction.triggered.connect(self.update_app)
        appMenu.addAction(updateAppAction)

        if is_app_in_startup is not None:
            winautorun_toggle = QAction('Run on Windows start', self)
            winautorun_toggle.setCheckable(True)
            winautorun_toggle.setChecked(is_app_in_startup(self.STARTUP_CONFIG[0]))
            winautorun_toggle.triggered.connect(self.handle_windows_startup_chbx)
            appMenu.addAction(winautorun_toggle)

        aboutMenu = self.menuBar.addMenu('About')

        about_action = QAction('Application page on Github', self)
        about_action.triggered.connect(self.go_to_app_page)
        aboutMenu.addAction(about_action)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(9, 9, 9, 9)

        main_layout.addSpacing(self.menuBar.height())

        layout_h = QHBoxLayout()
        layout_h.setContentsMargins(0, 0, 0, 0)
        layout_h.setSpacing(6)
        main_layout.addLayout(layout_h)

        self.textEdit = QTextEdit()
        self.textEdit.setFocusPolicy(Qt.NoFocus)

        self.listWidget = QListWidget()
        self.listWidget.setFocusPolicy(Qt.NoFocus)

        self.textEdit.setMinimumSize(350, 400)
        self.listWidget.setMinimumSize(350, 400)

        hor_layout = QHBoxLayout()

        self.remote_control_chb = QCheckBox('Allow Remote Control')
        hor_layout.addWidget(self.remote_control_chb)

        self.ENABLE_PRINT = QCheckBox('Console output')
        hor_layout.addWidget(self.ENABLE_PRINT)
        def trigger_console_output_chb():
            Globals.ENABLE_PRINT = self.ENABLE_PRINT.isChecked()
        self.ENABLE_PRINT.stateChanged.connect(trigger_console_output_chb)
        self.ENABLE_PRINT.setChecked(False)

        self.show_log_keys_chb = QCheckBox('Show keys log')
        hor_layout.addWidget(self.show_log_keys_chb)
        def trigger_show_log_keys_chb():
            self.show_log_keys = not self.show_log_keys
            if not self.show_log_keys:
                if Globals.client_keys_logger is not None:
                    Globals.client_keys_logger.hide()

        self.show_log_keys_chb.setChecked(self.show_log_keys)
        self.show_log_keys_chb.stateChanged.connect(trigger_show_log_keys_chb)


        main_layout.addLayout(hor_layout)

        self.framerate_label = QLabel()
        self.framerate_label.setText('frame rate label')
        self.framerate_label.setFixedHeight(80)

        hor_layout4 = QHBoxLayout()
        hor_layout4.setContentsMargins(0, 0, 0, 0)
        hor_layout4.setSpacing(0)
        hor_layout4.addWidget(self.framerate_label, 1)
        main_layout.addLayout(hor_layout4)

        self.wakeOnLanButton = QPushButton('Send WakeOnLan magic packet to peer')
        self.wakeOnLanButton.clicked.connect(self.do_wake_on_lan)
        hor_layout.addWidget(self.wakeOnLanButton)

        self.testButton = QPushButton('Test')
        self.testButton.clicked.connect(self.testButtonHandler)
        hor_layout.addWidget(self.testButton)

        self.openPortalBtn = QPushButton('Open Portal')
        self.openPortalBtn.clicked.connect(self.portalButtonHandler)
        hor_layout.addWidget(self.openPortalBtn)

        self.portal_widget = Portal(self)
        self.portal_widget.resize(1200, 1000)

        settings = get_settings()
        allow_remote_control = str_to_bool( get_settings().value('allow_remote_control', bool_to_str(False)) )
        self.remote_control_chb.setChecked(allow_remote_control)

        splt = QSplitter(Qt.Horizontal)
        splt.addWidget(self.textEdit)
        splt.addWidget(self.portal_widget)
        self.portal_widget.resize(0, self.portal_widget.height())
        splt.addWidget(self.listWidget)
        layout_h.addWidget(splt)
        self.splt = splt

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

        self.setAcceptDrops(True)

        self.textEdit.setReadOnly(True)
        self.lineEdit.setFocusPolicy(Qt.StrongFocus)

        for w in [self.textEdit,
                    self.listWidget,
                    self.openPortalBtn,
                    self.wakeOnLanButton,
                    self.testButton,
                    self.remote_control_chb,
                    self.ENABLE_PRINT,
                    self.show_log_keys_chb,
                ]:
            w.setFocusPolicy(Qt.NoFocus)

        self.lineEdit.returnPressed.connect(self.returnPressed)
        self.client.newMessage.connect(self.appendMessage)
        self.client.newParticipant.connect(self.newParticipant)
        self.client.participantLeft.connect(self.participantLeft)

        self.myNickName = self.client.nickName()
        self.newParticipant(self.myNickName, None)

        self.tableFormat.setBorder(0);
        QTimer.singleShot(10 * 1000, self.showInformation)

        for ip, mac in Globals.read_peers_list().items():
            item = QListWidgetItem(Globals.gray_icon, f' {ip} // {mac}')
            self.listWidget.addItem(item)

        self.resize(1200, 800)

        self.split_sizes = []

        rect = self.frameGeometry()
        rect.moveCenter(QDesktopWidget().availableGeometry().center())
        self.move(rect.topLeft())

        app = QApplication.instance()
        app.screenAdded.connect(self.screenCountChanged)
        app.screenRemoved.connect(self.screenCountChanged)

        self.remote_control_chb.stateChanged.connect(self.remote_control_state_changed)

        self.setWindowFlags(Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)

    def prepare_portal(self):
        self.splt.setSizes([300, 400, 300])
        # self.disconnect_data = None
        self.openPortalBtn.setText("Close Portal")
        self.update()

    def portal_off(self):
        sizes = self.splt.sizes()
        self.splt.setSizes([sizes[0], 0, sizes[2]])
        self.openPortalBtn.setText("Open Portal")
        self.framerate_label.setText('')
        self.disconnect_data = None
        self.portal_widget.close_portal()
        self.update()

    def portalButtonHandler(self):

        if self.disconnect_data is not None:
            connection = self.disconnect_data
            connection.sendControlRequestAnswer(ControlRequest.Break)
            self.disconnect_data = None
            self.portal_off()
            return

        item = self.listWidget.currentItem()
        if not item:
            self.appendSystemMessage('Не выбран пир в списке для подключения!')
        else:
            item_text = item.text()
            splitter = " // "
            if splitter not in item_text:
                self.appendSystemMessage('Невозможно подключиться к самому себе, ты шо, ёбобо?')
                return

            item_text = item_text[item_text.index(':'):item_text.index('/')-1]

            if item_text.rfind(":") > item_text.rfind("."):
                # убираем порт из адреса, если он присутствует
                item_text = item_text[:item_text.rfind(":")]

            ip_adress_ipv6 = item_text.strip()
            # builtins.print(f'selected address {ip_adress_ipv6}')
            connection = None
            for peerAddress, peerConn in self.client.peers.items():
                if peerAddress.toString() == ip_adress_ipv6:
                    connection = peerConn
                    break
            if connection is None:
                self.appendSystemMessage('Не найден в списке активных пиров!')
            else:
                connection.requestControlPortal()
                self.disconnect_data = connection

    def retrieve_status(self):
        if self.remote_control_chb.isChecked():
            status = 'follower'
        else:
            status = 'leader'
        return status

    def remote_control_state_changed(self):
        get_settings().setValue('allow_remote_control', bool_to_str(self.remote_control_chb.isChecked()))
        self.client.sendStatusToPeers(self.retrieve_status())

    def screenCountChanged(self, screen):
        app = QApplication.instance()
        count = len(app.screens())
        self.appendSystemMessage(f'Screens count changed: now it is {count}')

    def testButtonHandler(self):
        sizes = self.splt.sizes()
        self.appendSystemMessage(str(sizes))
        if sizes[1] == 0:
            sizes = self.split_sizes[:]
        else:
            self.split_sizes = sizes[:]
            sizes[1] = 0
        self.splt.setSizes(sizes)

    def print_to_chat(self, *args):
        self.appendSystemMessage(*args)
        # для того, чтобы успело что-то отобразиться
        app = QApplication.instance()
        app.processEvents()

    def reboot_app(self):
        subprocess.Popen([sys.executable, *sys.argv])
        sys.exit()

    def update_app(self):
        ret = QMessageBox.question(None,
            "Вопрос", "Download update from repository ans install?",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Close,
        )
        if ret == QMessageBox.Yes:
            do_update(self.print_to_chat)
            for n in [3, 2, 1]:
                self.print_to_chat(f'reboot in {n}')
                time.sleep(1)
            self.reboot_app()

    def do_wake_on_lan(self):
        item = self.listWidget.currentItem()
        if item:
            item_text = item.text()
            splitter = " // "
            if splitter in item_text:
                mac = item_text.split()[-1]
                mac = mac.strip().lower()
                send_magic_packet(mac, ip_address='192.168.0.255')
                self.appendSystemMessage(f'WakeOnLAN: packet sent to {mac}')
                return
        self.appendSystemMessage(f'WakeOnLAN: no any peer selected')

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

    def appendSystemMessage(self, message, bold=False):
        if bold:
            old_font = self.textEdit.currentFont()
            font = self.textEdit.currentFont()
            font.setWeight(2300)
            self.textEdit.setCurrentFont(font)

        color = self.textEdit.textColor()
        self.textEdit.setTextColor(Qt.green)
        self.textEdit.append("! System: %s" % message)
        self.textEdit.setTextColor(color)

        if bold:
            self.textEdit.setCurrentFont(old_font)

    def returnPressed(self):
        text = self.lineEdit.text()
        if not text:
            return

        if text.startswith('/'):
            color = self.textEdit.textColor()
            self.textEdit.setTextColor(Qt.red)
            self.textEdit.append("! Unknown command: %s" % text)
            self.textEdit.setTextColor(color)
        else:
            self.client.sendMessage(text)
            self.appendMessage(self.myNickName, text)

        self.lineEdit.clear()

    def newParticipant(self, nick, connection):
        if not nick:
            return

        icon = Globals.green_icon
        if connection is not None:
            socket = connection.socket
            if socket is not None:
                # removing [inactive] item
                items_to_delete = []
                peer_addr = socket.peerAddress().toString()

                for n in range(self.listWidget.count()):
                    item = self.listWidget.item(n)
                    if peer_addr in item.text():
                        items_to_delete.append(item)

                for item in items_to_delete:
                    self.listWidget.takeItem(self.listWidget.row(item))
                if connection.status == 'leader':
                    icon = Globals.red_icon


        color = self.textEdit.textColor()
        self.textEdit.setTextColor(Qt.gray)
        self.textEdit.append("* %s has joined" % nick)
        self.textEdit.setTextColor(color)
        item = QListWidgetItem(icon, nick)
        self.listWidget.addItem(item)

    def participantLeft(self, nick):
        if not nick:
            return
        items = self.listWidget.findItems(nick, Qt.MatchExactly)
        item = items[0]

        if not items:
            return
        self.listWidget.takeItem(self.listWidget.row(item))

        item = QListWidgetItem(Globals.gray_icon, item.text())
        self.listWidget.addItem(item)

        color = self.textEdit.textColor()
        self.textEdit.setTextColor(Qt.gray)
        self.textEdit.append("* %s has left" % nick)
        self.textEdit.setTextColor(color)

    def showInformation(self):
        return
        # if self.listWidget.count() == 1:
        #     QMessageBox.information(self, "Chat", "Launch several instances of this program on your local network and start chatting!")
    def closeEvent(self, event):
        # не совсем корректно, но пока так оставлю
        self.quit_app()

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.quit_app()

    def quit_app(self):
        app = QApplication.instance()
        app.quit()

    def dragEnterEvent(self, event):
        mime_data = event.mimeData()
        if mime_data.hasUrls() or mime_data.hasImage():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        mime_data = event.mimeData()
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.CopyAction)
            event.accept()
            paths = []
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    path = str(url.toLocalFile())
                    paths.append(path)
                else:
                    pass

            send_files(paths)

            self.update()
        else:
            event.ignore()





def show_system_tray(app, icon):
    sti = QSystemTrayIcon(app)
    sti.setIcon(icon)
    sti.setToolTip(f"LAN-DESKTOP {Globals.VERSION_INFO} {Globals.AUTHOR_INFO}")
    app.setProperty("stray_icon", sti)
    @pyqtSlot()
    def on_trayicon_activated(reason):
        if reason == QSystemTrayIcon.Trigger: # левая кнопка мыши
            pass
        if reason == QSystemTrayIcon.Context: # правая кнопка мыши
            menu = QMenu()
            menu.addSeparator()
            quit = menu.addAction('Quit')
            action = menu.exec_(QCursor().pos())
            if action == quit:
                app = QApplication.instance()
                app.quit()
    sti.activated.connect(on_trayicon_activated)
    sti.show()
    return sti


def get_crashlog_filepath():
    return os.path.join(os.path.dirname(__file__), "crash.log")


def excepthook(exc_type, exc_value, exc_tb):
    # пишем инфу о краше
    if isinstance(exc_tb, str):
        traceback_lines = exc_tb
    else:
        traceback_lines = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    if platform.system() == 'Windows':
        locale.setlocale(locale.LC_ALL, "russian")
    datetime_string = time.strftime("%A, %d %B %Y %X").capitalize()
    dt = "{0} {1} {0}".format(" "*15, datetime_string)
    dt_framed = "{0}\n{1}\n{0}\n".format("-"*len(dt), dt)
    with open(get_crashlog_filepath(), "a+", encoding="utf8") as crash_log:
        crash_log.write("\n"*10)
        crash_log.write(dt_framed)
        crash_log.write("\n")
        crash_log.write(traceback_lines)
    builtins.print("*** excepthook info ***")
    builtins.print(traceback_lines)
    app = QApplication.instance()
    if app:
        stray_icon = app.property("stray_icon")
        if stray_icon:
            stray_icon.hide()
    sys.exit()

def init_settings(app):

    QCoreApplication.setOrganizationName("Sergei Krumas");
    QCoreApplication.setOrganizationDomain("sergei-krumas.com");
    QCoreApplication.setApplicationName("LAN-DESKTOP");

    filepath = os.path.join(os.path.dirname(__file__), f'lan_desktop.{platform.system()}.settings')
    Globals.settings = QSettings(filepath, QSettings.IniFormat)

def get_settings():
    return Globals.settings

def bool_to_str(x):
    return str(int(x))

def str_to_bool(x):
    return bool(int(x))

def main():

    args = sys.argv
    os.chdir(os.path.dirname(__file__))
    sys.excepthook = excepthook

    app = QApplication(args)

    init_settings(app)

    Globals.gray_icon = Globals.generate_circle_icon(Qt.gray)
    Globals.green_icon = Globals.generate_circle_icon(Qt.green)
    Globals.red_icon = Globals.generate_circle_icon(QColor(200, 0, 0))

    if platform.system() == 'Windows':
        appid = 'sergei_krumas.LAN_DESKTOP.client.1'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(appid)

    path_icon = os.path.abspath(os.path.join(os.path.dirname(__file__), "icon.png"))
    icon = QIcon(path_icon)
    app.setWindowIcon(icon)

    global chat_dialog
    chat_dialog = ChatDialog()
    chat_dialog.show()

    stray_icon = show_system_tray(app, icon)

    app.exec()

    # после закрытия апликухи
    stray_icon = app.property("stray_icon")
    if stray_icon:
        stray_icon.hide()

    sys.exit()

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        excepthook(type(e), e, traceback.format_exc())
