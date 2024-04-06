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
from collections import defaultdict
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



from _resizable_frameless_modificated import ResizableWidgetWindow

from _utils import (fit_rect_into_rect, )
from update import do_update

try:
    from on_windows_startup import (is_app_in_startup, add_to_startup, remove_from_startup)
except:
    is_app_in_startup = None
    add_to_startup = None
    remove_from_startup = None


class Globals():

    DEBUG = True
    ENABLE_PRINT = False

    BROADCASTINTERVAL = 2000
    BROADCASTPORT = 45000


    VERSION_INFO = "v0.1"
    AUTHOR_INFO = "by Sergei Krumas"


    IMAGE_FORMAT = 'jpg'
    peers_list_filename = f'peers_list_{platform.system()}.list'


    last_reading = None
    last_writing = None

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


def print(*args, **kwargs):
    if Globals.ENABLE_PRINT:
        builtins.print(*args, **kwargs)


PingInterval = 40


keys_log_viewer = None
capture_zone_widget_window = None

INT_SIZE = 4
TCP_MESSAGE_HEADER_SIZE = INT_SIZE*3
DEBUG_STRING_SIZE = 50


def read_peers_list():
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

def update_peers_list(addr, port, mac):
    data_dict = read_peers_list()
    data_dict.update({addr: mac})
    data = json.dumps(data_dict)
    with open(Globals.peers_list_filename, 'w+', encoding='utf8') as file:
        file.write(data)

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


    if serial_data:
        debug_string = str(serial_data)

    debug_string += "*"*(DEBUG_STRING_SIZE-len(debug_string))
    debug_string = debug_string[:DEBUG_STRING_SIZE]
    debug_string = debug_string.encode('utf8')

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
    data_to_sent = debug_string + header + serial_binary + bin_binary

    # print('prepare_data_to_write', serial_data)

    return data_to_sent




def prepare_screenshot_to_transfer(capture_index):

    if capture_index == -2:
        capture_rect = capture_zone_widget_window.geometry()
        image = make_user_defined_capture_screenshot(capture_rect)
    else:
        image, capture_rect = make_capture_frame(capture_index)

    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    buffer.open(QIODevice.WriteOnly)
    # image.save(buffer, "jpg", quality=20)
    # image.save(buffer, "jpg")
    image.save(buffer, Globals.IMAGE_FORMAT, quality=50)


    capture_rect_tuple = [capture_rect.left(), capture_rect.top(), capture_rect.width(), capture_rect.height()]

    return prepare_data_to_write(capture_rect_tuple, byte_array.data())


def show_user_defined_capture_widget():
    global capture_zone_widget_window
    if capture_zone_widget_window is None:
        capture_zone_widget_window = ResizableWidgetWindow()
        capture_zone_widget_window.show()
        capture_zone_widget_window.resize(240, 160)
    capture_zone_widget_window.show()

def hide_user_defined_capture_widget():
    global capture_zone_widget_window
    if capture_zone_widget_window is not None:
        capture_zone_widget_window.hide()




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
        global keys_log_viewer
        if keys_log_viewer is None:
            keys_log_viewer = TransparentWidget()
            keys_log_viewer.resize(400, 800)
            keys_log_viewer.show()
            rect = keys_log_viewer.geometry()
            desktop_widget = QDesktopWidget()
            # кладём окно аккурат над кнопкой «Пуск»
            rect.moveBottomLeft(desktop_widget.availableGeometry().bottomLeft())
            keys_log_viewer.setGeometry(rect)

        keys_log_viewer.addToKeysLog(status, key_name)
        keys_log_viewer.update()






class Portal(QWidget):

    def __init__(self, parent):
        super().__init__(parent)

        self.update_timestamp = time.time()

        self.image_to_show = None
        self.setMouseTracking(True)

        self.mouse_timer = QTimer()
        self.mouse_timer.setInterval(200)
        self.mouse_timer.timeout.connect(self.mouseTimerHandler)
        self.mouse_timer.start()


        self.animation_timer = QTimer()
        self.animation_timer.setInterval(100)
        self.animation_timer.timeout.connect(self.mouseAnimationTimerHandler)

        self.show_log_keys = False

        self.update_timer = QTimer()
        self.update_timer.setInterval(1000)
        self.update_timer.timeout.connect(self.update)
        self.update_timer.start()

        self.menuBar = QMenuBar(self)

        self.is_grayed = False
        self.activated = False

        self.editing_mode = False

        self.canvas_origin = QPoint(600, 500)
        self.canvas_scale_x = 1.0
        self.canvas_scale_y = 1.0

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

        self.key_translate_error_duration = .4
        self.key_translate_error_timestamp = time.time() - self.key_translate_error_duration

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

            self.image_to_show = self.image_to_show.convertToFormat(QImage.Format_Mono)



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


        if self.activated:
            SPAN = 2 #seconds
            if time.time() - self.update_timestamp > SPAN:
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

            if self.is_grayed:

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
            painter.drawText(self.rect(), Qt.AlignRight | Qt.AlignTop, text)

        else:
            painter.fillRect(self.rect(), QColor(20, 20, 20, 255))
            self.drawMessageInCenter(painter, 'Портал неактивен')

        if self.editing_mode:

            painter.setPen(QPen(QColor(255, 50, 50), 3, Qt.DotLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))


        painter.end()

    def get_viewport_rect(self):
        image_rect = self.image_to_show.rect()

        image_rect.setWidth(int(image_rect.width()*self.canvas_scale_x))
        image_rect.setHeight(int(image_rect.height()*self.canvas_scale_y))
        canvas_origin = QPointF(self.canvas_origin).toPoint()
        image_rect.moveCenter(canvas_origin)

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

        x = int(norm_x*self.capture_rect.width()) + self.capture_rect.left()
        y = int(norm_y*self.capture_rect.height()) + self.capture_rect.top()

        return x, y

    def isViewportReadyAndCursorInsideViewport(self):
        if self.image_to_show is not None and self.isActiveWindow():
            mapped_cursor_pos = self.mapFromGlobal(QCursor().pos())
            viewport_rect = self.get_viewport_rect()
            if viewport_rect.contains(mapped_cursor_pos):
                return True
        return False

    def mouseMoveEvent(self, event):
        if self.editing_mode:
            if event.buttons() == Qt.LeftButton:
                delta = QPoint(event.pos() - self.ocp)
                self.canvas_origin = self.start_canvas_origin + delta
                chat_dialog.appendSystemMessage('move')

        self.update()

    def mousePressEvent(self, event):
        self.setFocus(Qt.MouseFocusReason)

        if self.editing_mode:
            if event.button() == Qt.LeftButton:
                self.start_canvas_origin = QPointF(self.canvas_origin)
                self.ocp = event.pos()
                chat_dialog.appendSystemMessage('press')                
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
        if self.editing_mode:
            pass

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
            pass
        else:
            key_name_attr = self.key_attr_names.get(event.key(), None)
            self.addToKeysLog('up', key_name_attr)
            self.sendKeyData(event, 'keyUp')

def show_capture_window(image, capture_rect, connection):

    portal = chat_dialog.portal_widget

    portal.image_to_show = image
    portal.capture_rect = capture_rect
    portal.connection = connection
    address = connection.socket.peerAddress().toString()
    title = f'Viewport for {address}'
    portal.update_timestamp = time.time()
    portal.is_grayed = False
    portal.activated = True
    portal.update()

class DataType:
    PlainText = 0
    Ping = 1
    Pong = 2
    Greeting = 3
    Undefined = 4
    MouseData = 5
    KeyboardData = 6
    FileData = 7


send_timers = []

class SendTimer(QTimer):
    def __init__(self, filepath):
        super().__init__()
        send_timers.append(self)
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
            if self in send_timers:
                send_timers.remove(self)

def send_files(paths):
    for path in paths:
        SendTimer(path)

recieving_files = defaultdict(int)
recieving_files_objs = defaultdict(None)

def write_file_chunk_data(file_chunk_info, binary_data, peer_address_string):

    md5_hash = file_chunk_info['md5_hash']
    total_size = file_chunk_info['total_size']
    filename = file_chunk_info['filename']
    chunk_size = file_chunk_info['chunk_size']

    chat_dialog.appendSystemMessage(f'От {peer_address_string} получена часть файла {filename}, размер которой {chunk_size}')

    global recieving_files
    if md5_hash not in recieving_files:
        recieving_files_objs[md5_hash] = open(md5_hash, 'wb')

    file_obj = recieving_files_objs[md5_hash]

    recieving_files[md5_hash] += chunk_size

    file_obj.write(binary_data)

    if recieving_files[md5_hash] >= total_size:
        recieving_files.pop(md5_hash)
        recieving_files_objs.pop(md5_hash)
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

        self.socket_buffer = self.socket_buffer + self.socket.read(200000)

        self.data_full_to_read = True

        # while len(self.socket_buffer) > TCP_MESSAGE_HEADER_SIZE and self.data_full_to_read:
        if True:
            if self.readState == self.states.readSize:
                if len(self.socket_buffer) >= TCP_MESSAGE_HEADER_SIZE:
                    self.debug_string = retrieve_data(DEBUG_STRING_SIZE)
                    self.content_data_size = int.from_bytes(retrieve_data(INT_SIZE), 'big')
                    self.cbor2_data_size = int.from_bytes(retrieve_data(INT_SIZE), 'big')
                    self.binary_data_size = int.from_bytes(retrieve_data(INT_SIZE), 'big')
                    self.readState = self.states.readData
                    print('content_data_size', self.content_data_size, 'socket_buffer_size', len(self.socket_buffer), self.debug_string)
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
                        file_chunk_info = None

                        if cbor2_data:
                            parsed_data = cbor2.loads(cbor2_data)

                            if isinstance(parsed_data, dict):
                                self.currentDataType, value = list(parsed_data.items())[0]
                                if self.currentDataType == DataType.Greeting:

                                    msg = value['msg']
                                    mac = value['mac']

                                    addr = self.socket.peerAddress().toString()
                                    port = self.socket.peerPort()

                                    update_peers_list(addr, port, mac)

                                    self.username = f'{msg}@{addr}:{port} // {mac}'

                                    if not self.isGreetingMessageSent:
                                        self.sendGreetingMessage()

                                    self.pingTimer.start()
                                    self.pongTime.start()
                                    self.readyForUse.emit()

                                elif self.currentDataType == DataType.PlainText:
                                    self.newMessage.emit(self.username, value)

                                # elif self.currentDataType == DataType.Ping:
                                #     self.socket.write(prepare_data_to_write({DataType.Pong: ''}, None))

                                elif self.currentDataType == DataType.Pong:
                                    self.pongTime.restart()

                                elif self.currentDataType == DataType.MouseData:

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

                                else:
                                    self.newMessage.emit('System', 'пришла какая-то непонятная хуйня')

                            else:
                                print(parsed_data)
                                capture_rect_coords = parsed_data

                        if binary_data:

                            if capture_rect_coords:
                                input_byte_array = QByteArray(binary_data)
                                capture_image = QImage()
                                capture_image.loadFromData(input_byte_array, Globals.IMAGE_FORMAT);
                                print(f'recieved image, {len(binary_data)}, {capture_image.size()}')

                                show_capture_window(capture_image, QRect(*capture_rect_coords), self)


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

        if self.data_full_to_read and len(self.socket_buffer) > TCP_MESSAGE_HEADER_SIZE:
            self.socket.readyRead.emit()

    def sendPing(self):

        if chat_dialog.remote_control_chb.isChecked():
            capture_index = chat_dialog.retrieve_capture_index()
            data = prepare_screenshot_to_transfer(capture_index)
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
        self.socket.write(
            prepare_data_to_write({DataType.Greeting: {'msg': self.greetingMessage, 'mac': mac_address}}, None)
        )
        self.isGreetingMessageSent = True


def find_mac_for_local_socket_addr(local_address_string):
    for ip_addr, mac in retreive_ip_mac_pairs():
        if local_address_string.endswith(ip_addr):
            return mac
    return 'Fuck! This is a disaster! MAC not found!'


def retreive_ip_mac_pairs():
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
            self.newParticipant.emit(nick, socket)

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
                global keys_log_viewer
                if keys_log_viewer is not None:
                    keys_log_viewer.hide()

        self.show_log_keys_chb.setChecked(self.show_log_keys)
        self.show_log_keys_chb.stateChanged.connect(trigger_show_log_keys_chb)


        self.capture_combobox = QComboBox()

        nameLb  = QLabel("Capture region:", self)
        desktop = QDesktopWidget()
        self.capture_combobox.addItem('User-defined region', -2)
        hor_layout.addWidget(nameLb)
        nameLb.setBuddy(self.capture_combobox)

        self.capture_combobox.addItem('All monitors', -1)
        for i in range(0, desktop.screenCount()):
            self.capture_combobox.addItem(f'Monitor {i+1}', i)
        # по дефолту выдаём содержимое первого монитора
        self.capture_combobox.setCurrentIndex(1)


        def capture_combobox_handler():
            if self.retrieve_capture_index() == -2 and self.remote_control_chb:
                show_user_defined_capture_widget()
            else:
                hide_user_defined_capture_widget()

        self.capture_combobox.currentIndexChanged.connect(capture_combobox_handler)

        hor_layout.addWidget(self.capture_combobox, Qt.AlignLeft)
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

        self.portal_widget = Portal(self)
        self.portal_widget.resize(1200, 1000)

        if platform.system() == 'Linux':
            self.remote_control_chb.setChecked(True)

        if True:
            splt = QSplitter(Qt.Horizontal)
            splt.addWidget(self.textEdit)
            splt.addWidget(self.portal_widget)
            splt.addWidget(self.listWidget)
            layout_h.addWidget(splt)
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

        self.setAcceptDrops(True)

        self.lineEdit.setFocusPolicy(Qt.StrongFocus)
        self.textEdit.setFocusPolicy(Qt.NoFocus)
        self.textEdit.setReadOnly(True)
        self.listWidget.setFocusPolicy(Qt.NoFocus)

        self.lineEdit.returnPressed.connect(self.returnPressed)
        self.client.newMessage.connect(self.appendMessage)
        self.client.newParticipant.connect(self.newParticipant)
        self.client.participantLeft.connect(self.participantLeft)

        self.myNickName = self.client.nickName()
        self.newParticipant(self.myNickName, None)

        self.tableFormat.setBorder(0);
        QTimer.singleShot(10 * 1000, self.showInformation)

        for ip, mac in read_peers_list().items():
            self.listWidget.addItem(f'[inactive] {ip} // {mac}')

        self.resize(1920, 1080)

        rect = self.frameGeometry()
        rect.moveCenter(QDesktopWidget().availableGeometry().center())
        self.move(rect.topLeft())

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

    def newParticipant(self, nick, socket):
        if not nick:
            return


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


        color = self.textEdit.textColor()
        self.textEdit.setTextColor(Qt.gray)
        self.textEdit.append("* %s has joined" % nick)
        self.textEdit.setTextColor(color)
        self.listWidget.addItem(nick)

    def participantLeft(self, nick):
        if not nick:
            return
        items = self.listWidget.findItems(nick, Qt.MatchExactly)
        item = items[0]

        if not items:
            return
        self.listWidget.takeItem(self.listWidget.row(item))
        inactive_item_text = f'[inactive] {item.text()}'
        self.listWidget.addItem(inactive_item_text)

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
    locale.setlocale(locale.LC_ALL, "russian")
    datetime_string = time.strftime("%A, %d %B %Y %X").capitalize()
    dt = "{0} {1} {0}".format(" "*15, datetime_string)
    dt_framed = "{0}\n{1}\n{0}\n".format("-"*len(dt), dt)
    with open(get_crashlog_filepath(), "a+", encoding="utf8") as crash_log:
        crash_log.write("\n"*10)
        crash_log.write(dt_framed)
        crash_log.write("\n")
        crash_log.write(traceback_lines)
    print("*** excepthook info ***")
    print(traceback_lines)
    app = QApplication.instance()
    if app:
        stray_icon = app.property("stray_icon")
        if stray_icon:
            stray_icon.hide()
    sys.exit()


def main():

    args = sys.argv
    os.chdir(os.path.dirname(__file__))
    sys.excepthook = excepthook

    app = QApplication(args)

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
