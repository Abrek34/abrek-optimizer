"""İşlem geçmişi sekmesi."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout, QHeaderView, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from abrekoptimizer.i18n import tr as _
from abrekoptimizer.core import history


class HistoryTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([_("Zaman"), _("İşlem"), _("Detay"), _("Durum")])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        btn = QPushButton(_("Yenile"))
        btn.clicked.connect(self.reload)
        row.addWidget(btn)
        row.addStretch(1)
        layout.addLayout(row)
        self.reload()

    def showEvent(self, ev):
        # Geçmiş sekmesine geçilince yeni kayıtları yükle
        try:
            self.reload()
        except Exception:
            pass
        super().showEvent(ev)

    def reload(self):
        import datetime
        ents = history.entries()
        self.table.setRowCount(len(ents))
        for i, e in enumerate(ents):
            ts = datetime.datetime.fromtimestamp(e.get("ts", 0)).strftime("%Y-%m-%d %H:%M")
            self.table.setItem(i, 0, QTableWidgetItem(ts))
            self.table.setItem(i, 1, QTableWidgetItem(str(e.get("action", ""))))
            self.table.setItem(i, 2, QTableWidgetItem(str(e.get("detail", ""))))
            self.table.setItem(i, 3, QTableWidgetItem("✓" if e.get("ok", True) else "✗"))
