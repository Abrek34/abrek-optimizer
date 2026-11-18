"""Hafif zaman-serisi grafiği (Qt'nin kendi QPainter'ı ile, ek bağımlılık yok)."""
from __future__ import annotations

from collections import deque

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


class TimeSeriesChart(QWidget):
    """Birkaç seriyi (0-100 arası) aynı anda çizen rolling grafik."""

    def __init__(self, series: dict[str, QColor], max_points: int = 120, parent=None):
        super().__init__(parent)
        self.series = series  # {name: color}
        self.max_points = max_points
        self.history: dict[str, deque[float]] = {k: deque(maxlen=max_points) for k in series}
        self.setMinimumHeight(140)
        self._grid_color = QColor(80, 80, 80, 90)
        self._bg = QColor(20, 22, 28)

    def push(self, values: dict[str, float]) -> None:
        for k, v in values.items():
            if k in self.history:
                self.history[k].append(float(v))
        self.update()

    def clear(self) -> None:
        for h in self.history.values():
            h.clear()
        self.update()

    def paintEvent(self, _ev) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        margin_l, margin_r, margin_t, margin_b = 32, 8, 8, 22
        plot = QRectF(margin_l, margin_t, w - margin_l - margin_r, h - margin_t - margin_b)

        # arka plan
        p.fillRect(self.rect(), self._bg)

        # grid (0,25,50,75,100)
        pen = QPen(self._grid_color)
        pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        for lvl in (0, 25, 50, 75, 100):
            y = plot.bottom() - (lvl / 100.0) * plot.height()
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.drawText(QRectF(0, y - 8, margin_l - 4, 16), Qt.AlignRight | Qt.AlignVCenter, str(lvl))

        # eksen etiketleri
        p.setPen(QColor(180, 180, 180))
        font = QFont(); font.setPointSize(8); p.setFont(font)
        p.drawText(QRectF(plot.left(), plot.bottom() + 2, plot.width(), 18),
                   Qt.AlignLeft | Qt.AlignVCenter, "← eski")
        p.drawText(QRectF(plot.left(), plot.bottom() + 2, plot.width(), 18),
                   Qt.AlignRight | Qt.AlignVCenter, "yeni →")

        # seriler
        n = max((len(v) for v in self.history.values()), default=0)
        if n < 2:
            p.end()
            return
        for name, color in self.series.items():
            data = list(self.history[name])
            if len(data) < 2:
                continue
            pen = QPen(color, 1.8)
            p.setPen(pen)
            step = plot.width() / max(self.max_points - 1, 1)
            # sağa hizala: son nokta plot.right()'ta
            offset = self.max_points - len(data)
            prev = None
            for i, val in enumerate(data):
                x = plot.left() + (offset + i) * step
                y = plot.bottom() - (max(0.0, min(100.0, val)) / 100.0) * plot.height()
                if prev is not None:
                    p.drawLine(prev, QPointF(x, y))
                prev = QPointF(x, y)

        # legend
        lx = plot.left() + 4
        ly = margin_t + 2
        for name, color in self.series.items():
            p.setPen(QPen(color, 2))
            p.drawLine(QPointF(lx, ly + 6), QPointF(lx + 14, ly + 6))
            p.setPen(QColor(220, 220, 220))
            p.drawText(QRectF(lx + 18, ly, 80, 14), Qt.AlignLeft | Qt.AlignVCenter, name)
            lx += 90
        p.end()