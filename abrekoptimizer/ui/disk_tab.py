"""Disk analizi sekmesi."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QHeaderView, QLabel, QProgressBar,
    QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from abrekoptimizer.i18n import tr as _
from abrekoptimizer.core import cleaner as cl


class DiskScanWorker(QThread):
    done = Signal(list)  # [(path, bytes)]

    def run(self):
        import subprocess
        home = Path.home()
        candidates = [home / p for p in (
            "Desktop", "Downloads", "Documents", "Videos", "Music",
            "Pictures", ".cache", ".local", ".config", ".steam",
            ".var", ".mozilla", "snap",
        )]
        candidates += [Path("/var/cache"), Path("/var/log"), Path("/tmp"), Path("/var/lib/flatpak")]
        found = []
        for c in candidates:
            if not c.exists():
                continue
            try:
                r = subprocess.run(
                    ["du", "-sb", "--apparent-size", str(c)],
                    capture_output=True, text=True, timeout=60, check=False,
                )
                if r.returncode == 0 and r.stdout.strip():
                    found.append((str(c), int(r.stdout.split()[0])))
            except (ValueError, subprocess.TimeoutExpired, FileNotFoundError):
                continue
        found.sort(key=lambda x: x[1], reverse=True)
        self.done.emit(found[:20])


class DiskTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(_(
            "En büyük klasörler (du ile hızlı tarama; root gerekmez, ev dizini + sistem önbellekleri)."
        )))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([_("Yol"), _("Boyut"), ""])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        btn = QPushButton(_("Tara"))
        btn.clicked.connect(self.scan)
        row.addWidget(btn)
        row.addStretch(1)
        layout.addLayout(row)
        self._worker = None
        self.scan()

    def scan(self):
        if self._worker and self._worker.isRunning():
            return
        self._worker = DiskScanWorker()
        self._worker.done.connect(self._done)
        self._worker.start()

    def _done(self, rows):
        if self.sender() is not self._worker:
            return
        self.table.setRowCount(len(rows))
        maxsz = max((s for _, s in rows), default=1) or 1
        for i, (path, size) in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(path))
            self.table.setItem(i, 1, QTableWidgetItem(cl.human_size(size)))
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(int(size * 100 / maxsz))
            bar.setTextVisible(False)
            bar.setMaximumHeight(16)
            self.table.setCellWidget(i, 2, bar)
