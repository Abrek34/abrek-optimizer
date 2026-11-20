"""Temizleme sekmesi."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from abrekoptimizer.core import cleaner as cl
from abrekoptimizer.core import history
from abrekoptimizer.i18n import tr as _
from abrekoptimizer.ui.runtime import notify, run_in_app


class ScanWorker(QThread):
    done = Signal(list)  # [(target, size)]

    def __init__(self, targets: list[cl.CleanTarget]):
        super().__init__()
        self.targets = targets

    def run(self):
        result = [(t, t.size()) for t in self.targets]
        self.done.emit(result)


class CleanerTab(QWidget):
    def __init__(self):
        super().__init__()
        self.targets = cl.default_targets()
        layout = QVBoxLayout(self)

        info = QLabel(_(
            "Temizlenecek hedefleri seçin. <b>Root</b> gerektiren öğeler için "
            "terminal açılıp şifre istenecektir."
        ))
        info.setWordWrap(True)
        layout.addWidget(info)

        self.table = QTableWidget(len(self.targets), 4)
        self.table.setHorizontalHeaderLabels([_("✓"), _("Hedef"), _("Boyut"), _("Açıklama")])
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        for i, t in enumerate(self.targets):
            chk = QCheckBox()
            chk.setChecked(not t.needs_root)
            w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(8, 0, 0, 0); h.addWidget(chk); h.addStretch()
            self.table.setCellWidget(i, 0, w)
            label = _(t.label) + (" 🔒" if t.needs_root else "")
            self.table.setItem(i, 1, QTableWidgetItem(label))
            self.table.setItem(i, 2, QTableWidgetItem("—"))
            self.table.setItem(i, 3, QTableWidgetItem(_(t.description)))
        layout.addWidget(self.table, 1)

        row = QHBoxLayout()
        self.scan_btn = QPushButton(_("Tara (boyutları hesapla)"))
        self.scan_btn.clicked.connect(self.scan)
        row.addWidget(self.scan_btn)
        self.clean_btn = QPushButton(_("Seçilenleri Temizle"))
        self.clean_btn.setStyleSheet("font-weight:bold;")
        self.clean_btn.clicked.connect(self.clean)
        row.addWidget(self.clean_btn)
        self.smart_btn = QPushButton(_("Akıllı seçim (≥50MB, root'suz)"))
        self.smart_btn.clicked.connect(self.smart_select)
        row.addWidget(self.smart_btn)
        self.journal_btn = QPushButton(_("Journal log'larını 7 günde tut"))
        self.journal_btn.clicked.connect(self.vacuum)
        row.addWidget(self.journal_btn)
        row.addStretch(1)
        self.total_lbl = QLabel(_("Toplam: —"))
        row.addWidget(self.total_lbl)
        layout.addLayout(row)

        self.log = QTextEdit(); self.log.setReadOnly(True); self.log.setMaximumHeight(140)
        layout.addWidget(self.log)

    def _is_checked(self, row: int) -> bool:
        w = self.table.cellWidget(row, 0)
        return bool(w and w.findChild(QCheckBox).isChecked())

    def scan(self):
        self.scan_btn.setEnabled(False)
        self.log.append(_("Tarama başladı..."))
        self.worker = ScanWorker(self.targets)
        self.worker.done.connect(self._scan_done)
        self.worker.start()

    def _scan_done(self, results):
        # Başka bir tarama başlatıldıysa bu eski sonucu yoksay
        if self.sender() is not getattr(self, "worker", None):
            return
        total = 0
        self._last_sizes = []
        for i, (_t, sz) in enumerate(results):
            self.table.item(i, 2).setText(cl.human_size(sz))
            self._last_sizes.append(sz)
            total += sz
        self.total_lbl.setText(_("Toplam: <b>{size}</b>").format(size=cl.human_size(total)))
        self.log.append(_("Tarama tamam. Toplam: {size}").format(size=cl.human_size(total)))
        self.scan_btn.setEnabled(True)

    def smart_select(self):
        """Son taramadan sonra: root gerektirmeyen ve ≥50MB olanları işaretle."""
        sizes = getattr(self, "_last_sizes", None)
        if not sizes:
            QMessageBox.information(self, _("Bilgi"), _("Önce tarama yapın."))
            return
        n = 0
        for i, t in enumerate(self.targets):
            w = self.table.cellWidget(i, 0)
            chk = w.findChild(QCheckBox) if w else None
            if chk is None:
                continue
            pick = (not t.needs_root) and i < len(sizes) and sizes[i] >= 50 * 1024 * 1024
            chk.setChecked(pick)
            n += int(pick)
        self.log.append(_("Akıllı seçim: {n} hedef işaretlendi (≥50MB, root'suz).").format(n=n))

    def clean(self):
        chosen = [t for i, t in enumerate(self.targets) if self._is_checked(i)]
        if not chosen:
            QMessageBox.information(self, _("Bilgi"), _("Lütfen temizlenecek hedef seçin."))
            return
        if QMessageBox.warning(
            self, _("Onayla"),
            _("{n} hedef temizlenecek. Bu işlem geri alınamaz. Devam?").format(n=len(chosen)),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        total_freed = 0
        for t in chosen:
            if t.needs_root:
                # Root gerektirenler: özel komutlarla
                self._clean_root(t)
                continue
            freed, errors = t.clean()
            total_freed += freed
            self.log.append(_("✓ {label}: {size} boşaltıldı").format(label=_(t.label), size=cl.human_size(freed))
                            + (_(" ({n} hata)").format(n=len(errors)) if errors else ""))
        self.log.append(_("<b>Toplam boşaltılan (kullanıcı): {size}</b>").format(size=cl.human_size(total_freed)))
        history.record("temizlik", f"{len(chosen)} hedef, {cl.human_size(total_freed)} boşaltıldı",
                       ok=total_freed > 0 or len(chosen) > 0)
        notify(_("Temizlik tamamlandı"),
               _("{size} boşaltıldı ({n} hedef)").format(size=cl.human_size(total_freed), n=len(chosen)))

    def _clean_root(self, t: cl.CleanTarget):
        import shlex
        if t.root_command is not None:
            cmd = list(t.root_command)
        else:
            cmds = []
            for p in t.paths:
                if p.exists():
                    cmds.append(f"sudo find {shlex.quote(str(p))} -mindepth 1 -delete 2>/dev/null || true")
            if not cmds:
                return
            cmd = ["bash", "-lc", " ; ".join(cmds)]
        reply = QMessageBox.question(
            self, _("Onayla"),
            _("'{label}' root ile temizlenecek. Emin misiniz?").format(label=_(t.label)),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        run_in_app(self, _(t.label), cmd)
        self.log.append(_("↗ {label}: uygulamada çalıştırıldı (root)").format(label=_(t.label)))

    def vacuum(self):
        reply = QMessageBox.question(
            self, _("Onayla"),
            _("Journal log'ları 7 güne indirilecek. Emin misiniz?"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            history.record("journal_vacuum")
            run_in_app(self, _("Journal vacuum"), ["sudo", "journalctl", "--vacuum-time=7d"])
