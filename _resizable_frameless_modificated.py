
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtNetwork import *


from _resizable_frameless import ResizableFramelessWindow

class CustomSizeGrip(QSizeGrip):

    def paintEvent(self, event):
        painter = QPainter()
        painter.begin(self)
        painter.setBrush(Qt.magenta)
        r = self.rect()
        painter.drawRect(r)
        painter.end()


class ResizableWidgetWindow(ResizableFramelessWindow):

    def __init__(self):
        super().__init__(CustomSizeGrip)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # задаю минимальный размер, чтобы пользователь нечаянно не занулил размеры
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.setMinimumSize(100, 100)

    def paintEvent(self, event):
        painter = QPainter()
        painter.begin(self)
        width_size = 5
        pen = QPen(QColor(200, 50, 50, 50), width_size)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        r = self.rect()
        r.adjust(width_size-1, width_size-1, -width_size, -width_size)
        painter.drawRect(r)
        painter.end()


if __name__ == '__main__':

    app = QApplication([])
    m = ResizableWidgetWindow()
    m.show()
    m.resize(240, 160)
    app.exec_()
