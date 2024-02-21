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


from PyQt5 import QtCore, QtGui, QtWidgets, uic
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *

import os, sys, ctypes, time, math, traceback, locale

from on_windows_startup import is_app_in_startup, add_to_startup, remove_from_startup


class Globals():
    DEBUG = True

    VERSION_INFO = "v0.1"
    AUTHOR_INFO = "by Sergei Krumas"


class StartWindow(QMainWindow):
    some_signal = QtCore.pyqtSignal()

    settings_checkbox = """
        QCheckBox {
            font-size: 18px;
            font-family: 'Consolas';
            color: white;
            font-weight: normal;
        }
        QCheckBox::indicator:unchecked {
            background: gray;
        }
        QCheckBox::indicator:checked {
            background: green;
        }
        QCheckBox:checked {
            background-color: rgba(150, 150, 150, 50);
            color: rgb(100, 255, 100);
        }
        QCheckBox:unchecked {
            color: gray;
        }
    """


    def __init__(self, *args):
        super().__init__(*args)


        self.STARTUP_CONFIG = (
            'lan_desktop_explorer_launcher',
            os.path.join(os.path.dirname(__file__), "launcher.pyw")
        )

        self.root_layout = QVBoxLayout()
        self.child_layout = QVBoxLayout()

        self.setStyleSheet("QPushButton{ padding: 10px 20px; font: 11pt; margin: 0 100; }")

        self.title_label = QLabel("<center>LAN-DESKTOP</center>")
        self.title_label.setStyleSheet("font-weight:bold; font-size: 30pt; color: gray;")

        self.black_text_label = QLabel("<center> black text label</center>" )
        self.black_text_label.setStyleSheet("font-weight:bold; font-size: 18pt; color: black; font-family: consolas;")

        start_client_btn = QPushButton("                 Start Client                 ")
        start_client_btn.clicked.connect( lambda: None )
        start_server_btn = QPushButton("                 Start Server                 ")
        start_server_btn.clicked.connect( lambda: None )

        self.child_layout.addWidget(self.title_label)
        self.child_layout.addWidget(self.black_text_label)

        self.gray_text_label = QLabel("<center>gray text label</center>")
        style_sheet = "font: 13pt; font-weight:bold; color: #aaaaaa; font-family: consolas;"
        self.gray_text_label.setStyleSheet(style_sheet)

        self.child_layout.addWidget( self.gray_text_label )
        self.child_layout.addSpacing(35)

        self.child_layout.addWidget(start_client_btn)
        self.child_layout.addWidget(start_server_btn)


        chbx_3 = QCheckBox("Запускать при старте Windows")
        chbx_3.setStyleSheet(self.settings_checkbox)
        chbx_3.setChecked(is_app_in_startup(self.STARTUP_CONFIG[0]))
        chbx_3.stateChanged.connect(lambda: self.handle_windows_startup_chbx(chbx_3))
        layout_3 = QVBoxLayout()
        layout_3.setAlignment(Qt.AlignCenter)
        layout_3.addWidget(chbx_3)

        self.child_layout.addSpacing(50)
        self.child_layout.addLayout(layout_3)

        self.root_layout.addSpacing(50)
        self.root_layout.addLayout(self.child_layout)
        self.root_layout.addSpacing(50)

        main_widget = QWidget()
        main_widget.setLayout(self.root_layout)

        self.setWindowTitle('LAN-DEKSTOP')
        self.setCentralWidget(main_widget)
        self.setFont(QFont("Times", 14, QFont.Normal))
        self.center_window()
        self.show()

        self.some_signal.connect(lambda: None)

    def handle_windows_startup_chbx(self, sender):
        if sender.isChecked():
            add_to_startup(*self.STARTUP_CONFIG)
        else:
            remove_from_startup(self.STARTUP_CONFIG[0])

    def center_window(self):
        window_rect = QDesktopWidget().screenGeometry(screen=0)
        x = (window_rect.width() - self.frameSize().width()) // 2
        y = (window_rect.height() - self.frameSize().height()) // 2
        self.move(x, y)


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

    appid = 'sergei_krumas.LAN_DESKTOP.client.1'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(appid)
    path_icon = os.path.abspath(os.path.join(os.path.dirname(__file__), "icon.png"))
    icon = QIcon(path_icon)
    app.setWindowIcon(icon)

    start_window = StartWindow()

    stray_icon = show_system_tray(app, icon)

    app.exec_()

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
