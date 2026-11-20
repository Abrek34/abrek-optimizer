"""Paketler / Kaldırma sekmesi."""
from __future__ import annotations

import subprocess

from PySide6.QtCore import QThread, Signal, QSize
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from abrekoptimizer.i18n import tr as _
from abrekoptimizer.core import iconres as ico
from abrekoptimizer.core import history
from abrekoptimizer.core.pkgmanager import PackageManager
from abrekoptimizer.ui.runtime import run_in_app, run_in_terminal, shorten_detail


class PackageListWorker(QThread):
    done = Signal(list)
    failed = Signal(str)

    def __init__(self, pkgmgr: PackageManager):
        super().__init__()
        self.pkgmgr = pkgmgr

    def run(self):
        try:
            pkgs = self.pkgmgr.list_installed()
            self.done.emit([(p.name, p.version, p.size, p.description) for p in pkgs])
        except Exception as e:
            self.failed.emit(str(e))


class PackagesTab(QWidget):
    def __init__(self, pkgmgr: PackageManager):
        super().__init__()
        self.pkgmgr = pkgmgr
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel(f"{_('Paket yöneticisi')}: <b>{pkgmgr.name}</b>"))
        self.search = QLineEdit()
        self.search.setPlaceholderText(_("Paket ara..."))
        self.search.textChanged.connect(self._filter)
        top.addWidget(self.search, 1)
        self.refresh_btn = QPushButton(_("Yenile"))
        self.refresh_btn.clicked.connect(self.reload)
        top.addWidget(self.refresh_btn)
        self.select_all_btn = QPushButton(_("Tümünü seç"))
        self.select_all_btn.clicked.connect(lambda: self.table.selectAll())
        top.addWidget(self.select_all_btn)
        layout.addLayout(top)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([_("Ad"), _("Sürüm"), _("Boyut"), _("Açıklama")])
        self.table.setIconSize(QSize(22, 22))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        self.purge_chk = QCheckBox(_("Yapılandırma + bağımlılıkları sil (-Rns / purge)"))
        self.purge_chk.setChecked(True)
        self.purge_chk.setToolTip(_("Pacman'da -Rns: konfig dosyalarını ve kullanılmayan bağımlılıkları siler."))
        bottom.addWidget(self.purge_chk)
        self.cascade_chk = QCheckBox(_("Bağımlı paketleri de kaldır (cascade)"))
        self.cascade_chk.setToolTip(_(
            "Bu paketi gerektiren DİĞER paketleri de kaldırır.\n"
            "Örn: 'gamescope' kaldırılırken 'cachyos-gaming-applications' meta-paketi de gider.\n"
            "DİKKAT: Beklenmedik kadar çok paket kaldırılabilir."
        ))
        bottom.addWidget(self.cascade_chk)
        bottom.addStretch(1)
        self.why_btn = QPushButton(_("Neye bağımlı?"))
        self.why_btn.setToolTip(_("Seçili paketin hangi başka paketler tarafından gerektirildiğini gösterir."))
        self.why_btn.clicked.connect(self._why_depends)
        bottom.addWidget(self.why_btn)
        self.autoremove_btn = QPushButton(_("Yetim paketleri kaldır"))
        self.autoremove_btn.clicked.connect(self._autoremove)
        bottom.addWidget(self.autoremove_btn)
        self.clean_cache_btn = QPushButton(_("Paket önbelleğini temizle"))
        self.clean_cache_btn.clicked.connect(self._clean_cache)
        bottom.addWidget(self.clean_cache_btn)
        self.remove_btn = QPushButton(_("Seçilenleri kaldır"))
        self.remove_btn.setStyleSheet("font-weight:bold;")
        self.remove_btn.clicked.connect(self._remove_selected)
        bottom.addWidget(self.remove_btn)
        layout.addLayout(bottom)

        self._all_rows: list[tuple] = []
        self._worker: PackageListWorker | None = None
        self.reload()

    def reload(self):
        if self._worker and self._worker.isRunning():
            return
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText(_("Yükleniyor..."))
        self.table.setRowCount(0)
        self._worker = PackageListWorker(self.pkgmgr)
        self._worker.done.connect(self._reload_done)
        self._worker.failed.connect(self._reload_failed)
        self._worker.start()

    def _reload_done(self, rows: list[tuple]):
        # Eski (iptal edilmiş) worker'dan gelen sonucu yoksay
        if self.sender() is not self._worker:
            return
        self._all_rows = rows
        self._render(self._all_rows)
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText(_("Yenile"))

    def _reload_failed(self, msg: str):
        if self.sender() is not self._worker:
            return
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText(_("Yenile"))
        QMessageBox.warning(self, _("Hata"), msg)

    def _render(self, rows):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for i, (n, v, s, d) in enumerate(rows):
            name_item = QTableWidgetItem(n)
            try:
                icon = ico.icon_for_package(n)
                if not icon.isNull():
                    name_item.setIcon(icon)
            except Exception:
                pass
            self.table.setItem(i, 0, name_item)
            for j, val in enumerate((v, s, d), start=1):
                self.table.setItem(i, j, QTableWidgetItem(val))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setSortingEnabled(True)

    def _filter(self, text: str):
        t = text.lower().strip()
        if not t:
            self._render(self._all_rows)
            return
        self._render([r for r in self._all_rows if t in r[0].lower() or t in r[3].lower()])

    def _selected_names(self) -> list[str]:
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self.table.item(r, 0).text() for r in rows if self.table.item(r, 0)]

    def _remove_selected(self):
        names = self._selected_names()
        if not names:
            QMessageBox.information(self, _("Bilgi"), _("Lütfen kaldırılacak paket(ler)i seçin."))
            return
        cascade = self.cascade_chk.isChecked()

        # Pacman için: dry-run ile gerçek listeyi göster
        preview_text = ""
        extras: list[str] = []
        if hasattr(self.pkgmgr, "preview_remove"):
            ok, full_list, err = self.pkgmgr.preview_remove(names, cascade=cascade)
            if not ok:
                # Cascade kapalıyken bu hata olur → cascade öner
                box = QMessageBox(self)
                box.setIcon(QMessageBox.Warning)
                box.setWindowTitle(_("Bağımlılık çatışması"))
                box.setText(_("İşlem başlatılamadı."))
                box.setInformativeText(
                    _("Pacman bu işlemi reddediyor:") + "\n\n"
                    + _("Çünkü seçtiğiniz paketlere başka paketler bağımlı. Cascade modunu açıp tekrar deneyin (alttaki kutu).")
                )
                box.setDetailedText(shorten_detail(err))
                enable_btn = box.addButton(_("Cascade'i aç ve tekrar dene"), QMessageBox.AcceptRole)
                box.addButton(_("İptal"), QMessageBox.RejectRole)
                box.exec()
                if box.clickedButton() is enable_btn:
                    self.cascade_chk.setChecked(True)
                    self._remove_selected()
                return
            extras = [p for p in full_list if p not in set(names)]
            preview_text = (
                _("Toplam <b>{n}</b> paket kaldırılacak.").format(n=len(full_list)) + "\n"
                + "  • " + _("Seçtiğiniz: {n}").format(n=len(names)) + "\n"
                + "  • " + _("Ek (bağımlılar/cascade): {n}").format(n=len(extras))
            )

        sel_msg = "\n".join(names[:15]) + ("\n…" if len(names) > 15 else "")
        extra_msg = ""
        if extras:
            extra_msg = "\n\n" + _("— Ek olarak kaldırılacak —") + "\n" + "\n".join(extras[:30])
            if len(extras) > 30:
                extra_msg += "\n" + _("… ve {n} tane daha").format(n=len(extras) - 30)
        warn = ""
        if cascade and extras:
            warn = "\n\n" + _("⚠ CASCADE: meta paketler ve bağımlılar da kaldırılacak.")

        body = (preview_text + "\n\n" if preview_text else "") + \
               _("Seçilen ({n}):").format(n=len(names)) + f"\n{sel_msg}{extra_msg}{warn}\n\n" + _("Devam edilsin mi?")

        reply = QMessageBox.warning(
            self, _("Onayla"), body,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        cmd = self.pkgmgr.remove_command(
            names, purge=self.purge_chk.isChecked(), cascade=cascade
        )
        history.record("paket_kaldirma", ", ".join(names[:5]) + ("..." if len(names) > 5 else ""))
        run_in_app(self, _("Paket kaldırma"), cmd)

    def _why_depends(self):
        names = self._selected_names()
        if not names:
            QMessageBox.information(self, _("Bilgi"), _("Lütfen bir paket seçin."))
            return
        name = names[0]
        try:
            cmd = self.pkgmgr.why_depends_command(name)
        except NotImplementedError:
            QMessageBox.information(self, _("Desteklenmiyor"), _("Bu paket yöneticisi için desteklenmiyor."))
            return
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=15)
            output = (res.stdout or "") + (res.stderr or "")
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            output = _("Komut çalıştırılamadı: {e}\n\nKomut: {cmd}").format(e=e, cmd=' '.join(cmd))
        dlg = QMessageBox(self)
        dlg.setWindowTitle(_("'{name}' neye bağımlı?").format(name=name))
        dlg.setIcon(QMessageBox.Information)
        dlg.setText(_("<b>{name}</b> paketini gerektirenler:").format(name=name))
        dlg.setDetailedText(shorten_detail(output) or _("(çıktı yok)"))
        dlg.exec()

    def _autoremove(self):
        if QMessageBox.question(self, _("Onayla"), _("Yetim paketler kaldırılsın mı?")) == QMessageBox.Yes:
            history.record("yetim_paket_temizligi")
            run_in_app(self, _("Yetim paketler"), self.pkgmgr.autoremove_command())

    def _clean_cache(self):
        if QMessageBox.question(self, _("Onayla"), _("Paket önbelleği temizlensin mi?")) == QMessageBox.Yes:
            history.record("paket_onbellegi_temizligi")
            run_in_app(self, _("Paket önbelleği"), self.pkgmgr.clean_cache_command())
