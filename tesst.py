









from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtNetwork import *

import sys


def make_screenshot_pyqt():
    desktop = QDesktopWidget()
    MAX = 1000000000
    left = MAX
    right = -MAX
    top = MAX
    bottom = -MAX
    for i in range(0, desktop.screenCount()):
        r = desktop.screenGeometry(screen=i)
        left = min(r.left(), left)
        right = max(r.right(), right)
        top = min(r.top(), top)
        bottom = max(r.bottom(), bottom)
    all_monitors_zone = QRect(QPoint(left, top), QPoint(right+1, bottom+1))

    # print(all_monitors_zone)
    qimage = QImage(
        all_monitors_zone.width(),
        all_monitors_zone.height(),
        QImage.Format_RGB32
    )
    qimage.fill(Qt.black)

    painter = QPainter()
    painter.begin(qimage)
    screens = QGuiApplication.screens()
    for n, screen in enumerate(screens):
        p = screen.grabWindow(0)
        source_rect = QRect(QPoint(0, 0), screen.geometry().size())
        painter.drawPixmap(screen.geometry(), p, source_rect)
    painter.end()
    return qimage



app = QApplication(sys.argv)



# stream = QDataStream()
# stream << make_screenshot_pyqt()
# print(dir(stream))
# QByteArray(stream)
# print(stream.status())

# print(make_screenshot_pyqt().bits())


# make_screenshot_pyqt()
def prepare_screenshot_to_transfer():
    image = make_screenshot_pyqt()

    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "jpg")

    data = byte_array.data()
    data_length = len(data)
    data_to_sent = data_length.to_bytes(4, 'big') + data

	# testing
    # input_byte_array = QByteArray(data)
    # i = QImage()
    # i.loadFromData(input_byte_array, "jpg");
    # print(i.size())

    return data_to_sent



prepare_screenshot_to_transfer()
