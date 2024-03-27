
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
        self.translating_ongoing = False
        self.center_rect = QRect(0, 0, 50, 50)

    def getCenterRect(self):
        r = QRect(self.center_rect)
        r.moveCenter(self.rect().center())
        return r

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

        r = self.getCenterRect()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(240, 240, 240, 200))
        painter.drawRect(r)

        painter.end()

    def mousePressEvent(self, event):

        center_rect = self.getCenterRect()
        if center_rect.contains(event.pos()):
            self.translating_ongoing = True 
            self.start_pos = QCursor().pos()
            self.start_topleft = self.geometry().topLeft()
        else:
            self.translating_ongoing = False

    def mouseMoveEvent(self, event):
        if self.translating_ongoing:
            # перенос всего виджета целиком
            pos = QCursor().pos()
            delta = self.start_pos - pos
            geometry = self.geometry()
            geometry.moveTopLeft(self.start_topleft - delta)
            self.setGeometry(geometry)

    def mouseReleaseEvent(self, event):
        if self.translating_ongoing:
            # ни за что не убирать этот код отсюда,
            # иначе угловые прихватки начнут чудить,
            # плюс это нужно по внутренней логике
            self.translating_ongoing = False

if __name__ == '__main__':

    app = QApplication([])
    m = ResizableWidgetWindow()
    m.show()
    m.resize(240, 160)
    app.exec_()
