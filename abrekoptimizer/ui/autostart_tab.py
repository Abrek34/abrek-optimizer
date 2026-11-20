"""Başlangıç (Autostart) sekmesi."""
from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from abrekoptimizer.i18n import tr as _
from abrekoptimizer.core import autostart as au
from abrekoptimizer.core import iconres as ico
from abrekoptimizer.core import history


class AutostartTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(_(
            "Açılışta çalışan öğeler: XDG autostart girdileri ve kullanıcı systemd servisleri. "
            "Onay kutusunu kapatınca devre dışı kalır."
        )))

        row = QHBoxLayout()
        self.sys_chkbox = QCheckBox(_("systemd user servislerini de göster"))
        self.sys_chkbox.setChecked(True)
        self.sys_chkbox.toggled.connect(lambda _v: self.reload())
        row.addWidget(self.sys_chkbox)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(_("Ara..."))
        self.filter_edit.textChanged.connect(self._apply_filter)
        row.addWidget(self.filter_edit, 1)
        layout.addLayout(row)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([_("Aktif"), _("Ad"), _("Komut"), _("Açıklama"), _("Kaynak")])
        self.table.setIconSize(QSize(22, 22))
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

        row = QHBoxLayout()
        self.refresh_btn = QPushButton(_("Yenile"))
        self.refresh_btn.clicked.connect(self.reload)
        row.addWidget(self.refresh_btn)
        row.addStretch(1)
        layout.addLayout(row)

        self.entries: list[au.AutostartEntry] = []
        self.reload()

    def reload(self):
        self.entries = au.list_xdg_autostart()
        if self.sys_chkbox.isChecked():
            self.entries += au.list_systemd_user_units()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.entries))
        for i, e in enumerate(self.entries):
            chk = QCheckBox()
            chk.setChecked(e.enabled)
            chk.toggled.connect(lambda v, ent=e: self._toggle(ent, v))
            w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(8, 0, 0, 0); h.addWidget(chk); h.addStretch()
            self.table.setCellWidget(i, 0, w)
            name_item = QTableWidgetItem(e.name)
            icon = ico.icon_from_name(e.icon) if e.icon else QIcon()
            if not icon.isNull():
                name_item.setIcon(icon)
            self.table.setItem(i, 1, name_item)
            self.table.setItem(i, 2, QTableWidgetItem(e.exec_cmd))
            self.table.setItem(i, 3, QTableWidgetItem(e.comment))
            self.table.setItem(i, 4, QTableWidgetItem(e.source))
        self.table.setSortingEnabled(True)
        self._apply_filter(self.filter_edit.text())

    def _apply_filter(self, text: str):
        t = text.lower().strip()
        for i in range(self.table.rowCount()):
            hay = " ".join(
                (self.table.item(i, j).text() if self.table.item(i, j) else "")
                for j in range(1, 5)
            ).lower()
            self.table.setRowHidden(i, bool(t) and t not in hay)

    def _toggle(self, entry: au.AutostartEntry, enabled: bool):
        try:
            if entry.source == "systemd":
                au.set_systemd_enabled(entry.name, enabled)
            else:
                au.set_xdg_enabled(entry, enabled)
            history.record("baslangic_degisimi", f"{entry.name}: {'açık' if enabled else 'kapalı'}")
        except OSError as e:
            QMessageBox.warning(self, _("Hata"), str(e))
