

from PyQt5.QtWidgets import (QWidget, QMessageBox, QDesktopWidget, QApplication,
    QGraphicsBlurEffect, QGraphicsPixmapItem, QGraphicsScene)
from PyQt5.QtCore import (QRectF, QPoint, pyqtSignal, QSizeF, Qt, QPointF, QSize, QRect,
                                                                    QMimeData, QUrl)
from PyQt5.QtGui import (QPixmap, QBrush, QRegion, QImage, QRadialGradient, QColor,
                    QGuiApplication, QPen, QPainterPath, QPolygon, QLinearGradient, QPainter,
                    QCursor, QImageReader, QTransform, QPolygonF, QVector2D)







def fit_rect_into_rect(source_rect, input_rect, float_mode=False):
    # копируем прямоугольники, чтобы не изменять исходники
    if float_mode:
        main_rect = QRectF(input_rect)
        size_rect = QRectF(source_rect)
    else:
        main_rect = QRect(input_rect)
        size_rect = QRect(source_rect)
    w = size_rect.width()
    h = size_rect.height()
    nw = size_rect.width()
    nh = size_rect.height()
    if size_rect.width() == 0 or size_rect.height() == 0:
        return source_rect
    if size_rect.width() > main_rect.width() or size_rect.height() > main_rect.height():
        # если контент не влазит на экран
        image_scale1 = main_rect.width()/size_rect.width()
        image_scale2 = main_rect.height()/size_rect.height()
        new_width1 = w*image_scale1
        new_height1 = h*image_scale1
        new_width2 = w*image_scale2
        new_height2 = h*image_scale2
        nw = min(new_width1, new_width2)
        nh = min(new_height1, new_height2)
    elif size_rect.width() < main_rect.width() or size_rect.height() < main_rect.height():
        # если контент меньше экрана
        image_scale1 = main_rect.width()/size_rect.width()
        image_scale2 = main_rect.height()/size_rect.height()
        new_width1 = w*image_scale1
        new_height1 = h*image_scale1
        new_width2 = w*image_scale2
        new_height2 = h*image_scale2
        nw = min(new_width1, new_width2)
        nh = min(new_height1, new_height2)
    center = main_rect.center()
    new_width = int(nw)
    new_height = int(nh)
    result = QRectF(QPointF(center) - QPointF(new_width/2-1, new_height/2-1), QSizeF(new_width, new_height))
    if float_mode:
        return result
    else:
        return result.toRect()
