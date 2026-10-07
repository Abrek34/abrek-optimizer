#!/usr/bin/env python3
"""Abrek Optimizer grafiksel kurulum penceresi.

Mevcut install.sh'i çalıştırır ve çıktıyı canlı olarak gösterir.
Kullanım:
    ./install-gui.sh              # önerilen
    python3 installer.py          # sistem python3 ile (PySide6 gerekir)
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

PROJECT_DIR = Path(__file__).resolve().parent


class InstallerWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Abrek Optimizer — Kurulum")
        self.resize(720, 480)

        root = QVBoxLayout(self)
        root.addWidget(QLabel("<h2>Abrek Optimizer Kurulumu</h2>"))
        root.addWidget(QLabel(
            "Bu kurulum: önce eski sürümü kaldırır, sanal ortamı kurar (.venv), "
            "paketi taze kurar, <code>abrek-optimizer</code> komutunu ve masaüstü "
            "menü girdisini ekler.\n"
            f"Hedef: <code>{PROJECT_DIR}</code>"
        ))

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        root.addWidget(self.log, 1)

        self.bar = QProgressBar()
        self.bar.setRange(0, 0)  # belirsiz
        self.bar.setVisible(False)
        root.addWidget(self.bar)

        row = QHBoxLayout()
        self.install_btn = QPushButton("Kur")
        self.install_btn.setStyleSheet("font-weight: bold;")
        self.install_btn.clicked.connect(self.start_install)
        row.addWidget(self.install_btn)
        row.addStretch(1)
        self.close_btn = QPushButton("Kapat")
        self.close_btn.setEnabled(False)
        self.close_btn.clicked.connect(self.close)
        row.addWidget(self.close_btn)
        root.addLayout(row)

        self.proc: QProcess | None = None

    # ------------------------------------------------------------------
    def start_install(self):
        if self.proc and self.proc.state() == QProcess.Running:
            return
        self.install_btn.setEnabled(False)
        self.bar.setVisible(True)
        self.log.clear()

        self.proc = QProcess(self)
        self.proc.setProgram("bash")
        self.proc.setArguments([str(PROJECT_DIR / "install.sh")])
        self.proc.setWorkingDirectory(str(PROJECT_DIR))
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._on_output)
        self.proc.finished.connect(self._on_finished)
        self.proc.start()

    def _on_output(self):
        assert self.proc is not None
        data = bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        self.log.appendPlainText(data.rstrip("\n"))

    def _on_finished(self, exit_code: int, _status):
        self.bar.setVisible(False)
        self.install_btn.setEnabled(True)
        self.close_btn.setEnabled(True)
        if exit_code == 0:
            self.log.appendPlainText("\n✓ Kurulum tamamlandı. 'abrek-optimizer' ile başlatabilirsiniz.")
            QMessageBox.information(self, "Kurulum", "Kurulum başarıyla tamamlandı.")
        else:
            self.log.appendPlainText(f"\n✗ Kurulum başarısız (çıkış kodu {exit_code}).")
            QMessageBox.critical(self, "Kurulum", f"Kurulum başarısız (kod {exit_code}).\nGünlüğe bakın.")


def main() -> int:
    app = QApplication(sys.argv)
    try:
        from abrekoptimizer import __app_name__
        app.setApplicationName(__app_name__ + " Kurulum")
    except ImportError:
        pass
    win = InstallerWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
