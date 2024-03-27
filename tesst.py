









from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtNetwork import *

import sys


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

if __name__ == '__main__':

    app = QApplication(sys.argv)

    input_rect = QRect(2360, 0, 500, 400)
    input_rect = QRect(0, 0, 2560*2, 1440)
    input_rect = QRect(2560, 0, 2560, 1440)
    make_user_defined_capture_screenshot(input_rect).save('image.jpg')

