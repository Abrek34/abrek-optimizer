"""Uygulama planı önizleme dialog'u (dry-run).

Komutları çalıştırmadan önce neyin değişeceğini gösterir;
kullanıcı onayladıktan sonra çalıştırılır.
"""
from __future__ import annotations

import shlex

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class PlanDialog(QDialog):
    """Uygulanacak komutları önizleme dialog'u."""

    def __init__(self, parent, title: str, commands: list[list[str]], descriptions: list[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(700, 500)
        self._commands = commands
        self._accepted = False

        lay = QVBoxLayout(self)

        info = QLabel(
            "Aşağıdaki komutlar sırayla çalıştırılacak. "
            "İnceleyip onaylayın veya iptal edin."
        )
        info.setWordWrap(True)
        lay.addWidget(info)

        # Komut listesi
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        v = QVBoxLayout(container)
        v.setSpacing(8)

        for i, cmd in enumerate(commands, 1):
            desc = descriptions[i - 1] if descriptions and i - 1 < len(descriptions) else ""
            group = QWidget()
            gl = QVBoxLayout(group)
            gl.setContentsMargins(8, 4, 8, 4)
            if desc:
                lbl = QLabel(f"<b>{i}. {desc}</b>")
                gl.addWidget(lbl)
            cmd_text = QPlainTextEdit()
            cmd_text.setReadOnly(True)
            cmd_text.setPlainText(" ".join(shlex.quote(c) for c in cmd))
            cmd_text.setMaximumHeight(60)
            gl.addWidget(cmd_text)
            v.addWidget(group)

        scroll.setWidget(container)
        lay.addWidget(scroll, 1)

        # Butonlar
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("Uygula")
        btns.button(QDialogButtonBox.Cancel).setText("İptal")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def accept(self):
        self._accepted = True
        super().accept()

    @property
    def accepted_plan(self) -> bool:
        return self._accepted
