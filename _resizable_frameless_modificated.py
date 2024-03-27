
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtNetwork import *

import os
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
        folder_path = os.path.dirname(__file__)
        filepath_translate_svg = os.path.join(folder_path, "resources", "translate.svg")
        self.translate_rastr_source = QPixmap(filepath_translate_svg).scaledToWidth(40, Qt.SmoothTransformation)
        self.setCursor(Qt.SizeAllCursor)

    def getCenterRect(self):
        r = QRect(self.center_rect)
        r.moveCenter(self.rect().center())
        return r

    def paintEvent(self, event):
        painter = QPainter()
        painter.begin(self)
        painter.setRenderHint(QPainter.HighQualityAntialiasing, True)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        width_size = 5
        pen = QPen(QColor(200, 50, 50, 50), width_size)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        r = self.rect()
        r.adjust(width_size-1, width_size-1, -width_size, -width_size)
        painter.drawRect(r)

        if self.translate_rastr_source.isNull():
            r = self.getCenterRect()
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(240, 240, 240, 200))
            painter.drawRect(r)
        else:
            factor = 1.0
            s = QRect(self.translate_rastr_source.rect())
            r1 = QRect(0, 0, int(s.width()*factor), int(s.height()*factor))
            r1.moveCenter(self.rect().center())
            factor = 0.8
            r2 = QRect(0, 0, int(s.width()*factor), int(s.height()*factor))
            r2.moveCenter(self.rect().center())
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 10))
            painter.drawEllipse(r2)
            painter.setOpacity(0.5)
            painter.drawPixmap(r1, self.translate_rastr_source, s)

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
