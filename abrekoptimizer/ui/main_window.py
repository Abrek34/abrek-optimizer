"""Abrek Optimizer ana pencere - PySide6/Qt6."""
from __future__ import annotations

import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal, QSize
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QScrollArea, QSlider, QSpinBox, QSplitter,
    QStatusBar, QTabWidget, QTableWidget, QTableWidgetItem, QTextEdit,
    QToolBar, QVBoxLayout, QWidget,
)

from abrekoptimizer import __app_name__, __version__, i18n
from abrekoptimizer.i18n import tr as _
from abrekoptimizer.core import autostart as au
from abrekoptimizer.core import cleaner as cl
from abrekoptimizer.core import gameopt as go
from abrekoptimizer.core import iconres as ico
from abrekoptimizer.core import perfmon as pm
from abrekoptimizer.core import applog
from abrekoptimizer.core import history
from abrekoptimizer.core import trend
from abrekoptimizer.core import profiles as prof
from abrekoptimizer.core.pkgmanager import PackageManager


# ---------- yardımcılar ----------
def confirm_and_run(parent, cmd: list[str], body: str | None = None) -> bool:
    """'Emin misiniz? Evet/Hayır' onayından sonra komutu terminalde çalıştırır."""
    if body is None:
        body = _("Bu işlem sistemde değişiklik yapacak. Emin misiniz?")
    reply = QMessageBox.question(
        parent, _("Onayla"), body,
        QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
    )
    if reply != QMessageBox.Yes:
        return False
    return run_in_terminal(cmd)


def run_in_terminal(cmd: list[str]) -> bool:
    """Komutu konsol uygulamasında çalıştır (sudo şifresi için)."""
    import shlex, shutil
    log = applog.get("ui")
    joined = " ".join(shlex.quote(c) for c in cmd)
    full = f"{joined}; echo; read -p 'Bitti. Enter ile kapat...'"
    for term, args in (
        ("konsole", ["-e", "bash", "-lc", full]),
        ("kgx", ["-e", "bash", "-lc", full]),
        ("gnome-terminal", ["--", "bash", "-lc", full]),
        ("xterm", ["-e", "bash", "-lc", full]),
        ("alacritty", ["-e", "bash", "-lc", full]),
        ("kitty", ["bash", "-lc", full]),
    ):
        if shutil.which(term):
            subprocess.Popen([term, *args])
            log.info("terminal command started: %s", joined)
            return True
    # son çare: arkaplan
    try:
        subprocess.Popen(["bash", "-lc", full])
        log.warning("no terminal emulator found, command started in background: %s", joined)
        return True
    except OSError as e:
        log.exception("terminal command failed: %s", joined)
        QMessageBox.warning(None, _("Hata"), _("Komut çalıştırılamadı: {e}\n\nKomut: {cmd}").format(e=e, cmd=joined))
        return False


def shorten_detail(text: str, max_len: int = 2000) -> str:
    """QMessageBox detay metnini kısalt: ev dizinini ~ yap, çok uzun çıktıları budama."""
    text = text.replace(str(Path.home()), "~")
    if len(text) > max_len:
        text = text[:max_len] + " …"
    return text


# ---------- Paket sekmesi ----------
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

        # Pacman i\u00e7in: dry-run ile ger\u00e7ek listeyi g\u00f6ster
        preview_text = ""
        extras: list[str] = []
        if hasattr(self.pkgmgr, "preview_remove"):
            ok, full_list, err = self.pkgmgr.preview_remove(names, cascade=cascade)
            if not ok:
                # Cascade kapalıyken bu hata olur → cascade öner (kullanılmayan msg bloğu kaldırıldı)
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


# ---------- Temizleme sekmesi ----------
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
        cmds = []
        for p in t.paths:
            if p.exists():
                cmds.append(f"sudo find {shlex.quote(str(p))} -mindepth 1 -delete 2>/dev/null || true")
        if cmds:
            reply = QMessageBox.question(
                self, _("Onayla"),
                _("'{label}' root ile temizlenecek. Emin misiniz?").format(label=_(t.label)),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            run_in_app(self, _(t.label), ["bash", "-lc", " ; ".join(cmds)])
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


# ---------- Autostart sekmesi ----------
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


# ---------- Performans sekmesi ----------
class PerfTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        grid = QHBoxLayout()
        self.cpu_bar = self._meter(_("CPU"))
        self.mem_bar = self._meter(_("RAM"))
        self.swap_bar = self._meter(_("Swap"))
        self.disk_bar = self._meter(_("Disk /"))
        for w in (self.cpu_bar, self.mem_bar, self.swap_bar, self.disk_bar):
            grid.addWidget(w)
        layout.addLayout(grid)

        self.info_lbl = QLabel("—")
        self.info_lbl.setTextFormat(Qt.RichText)
        layout.addWidget(self.info_lbl)

        layout.addWidget(QLabel(_("<b>En çok bellek kullanan süreçler</b>")))
        self.proc_table = QTableWidget(0, 5)
        self.proc_table.setHorizontalHeaderLabels([_("PID"), _("Kullanıcı"), _("Ad"), _("CPU %"), _("RAM %")])
        self.proc_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.proc_table.verticalHeader().setVisible(False)
        layout.addWidget(self.proc_table, 1)

        row = QHBoxLayout()
        self.kill_btn = QPushButton(_("Seçili süreci sonlandır (SIGTERM)"))
        self.kill_btn.clicked.connect(self._kill_selected)
        row.addWidget(self.kill_btn)
        row.addStretch(1)
        layout.addLayout(row)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1500)
        self.refresh()

    def _meter(self, label: str) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w); v.setContentsMargins(4, 4, 4, 4)
        lbl = QLabel(f"<b>{label}</b>"); lbl.setAlignment(Qt.AlignCenter)
        bar = QProgressBar(); bar.setRange(0, 100); bar.setTextVisible(True)
        v.addWidget(lbl); v.addWidget(bar)
        w.bar = bar
        return w

    def refresh(self):
        s = pm.snapshot()
        self.cpu_bar.bar.setValue(int(s.cpu_percent))
        self.mem_bar.bar.setValue(int(s.mem_percent))
        self.swap_bar.bar.setValue(int(s.swap_percent))
        self.disk_bar.bar.setValue(int(s.disk_percent))
        self.info_lbl.setText(
            _("RAM: <b>{used}</b> / {total} &nbsp;|&nbsp; Disk: <b>{dused}</b> / {dtotal} &nbsp;|&nbsp; Süreç: <b>{procs}</b> &nbsp;|&nbsp; Yük: {l1:.2f} {l2:.2f} {l3:.2f}").format(
                used=cl.human_size(s.mem_used), total=cl.human_size(s.mem_total),
                dused=cl.human_size(s.disk_used), dtotal=cl.human_size(s.disk_total),
                procs=s.process_count, l1=s.load_avg[0], l2=s.load_avg[1], l3=s.load_avg[2],
            )
        )
        try:
            procs = pm.top_processes("memory", 20)
        except Exception:
            procs = []
        self._fill_proc_table(procs)

    def _fill_proc_table(self, procs):
        # Yeniden çizimi azalt: sadece metinleri güncelle, gereksizse satır sayısını değiştirme
        self.proc_table.setUpdatesEnabled(False)
        try:
            self.proc_table.setSortingEnabled(False)
            if self.proc_table.rowCount() != len(procs):
                self.proc_table.setRowCount(len(procs))
            for i, p in enumerate(procs):
                vals = (
                    str(p.get("pid", "")),
                    str(p.get("username", "")),
                    str(p.get("name", "")),
                    f"{p.get('cpu_percent', 0):.1f}",
                    f"{p.get('memory_percent', 0):.1f}",
                )
                for j, v in enumerate(vals):
                    item = self.proc_table.item(i, j)
                    if item is None:
                        self.proc_table.setItem(i, j, QTableWidgetItem(v))
                    elif item.text() != v:
                        item.setText(v)
            self.proc_table.setSortingEnabled(True)
        finally:
            self.proc_table.setUpdatesEnabled(True)

    def _kill_selected(self):
        rows = sorted({i.row() for i in self.proc_table.selectedIndexes()})
        if not rows:
            return
        import os, signal
        pids = [self.proc_table.item(r, 0).text() for r in rows]
        reply = QMessageBox.question(
            self,
            _("Onay"),
            _("Seçili süreçlere SIGTERM gönderilsin mi?") + "\n" + ", ".join(pids),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        for r in rows:
            try:
                pid = int(self.proc_table.item(r, 0).text())
                os.kill(pid, signal.SIGTERM)
            except (ValueError, ProcessLookupError, PermissionError) as e:
                QMessageBox.warning(self, _("Hata"), f"PID {pid}: {e}")


# ---------- Oyun / Sistem Performans Modu sekmesi ----------
class GameStatusWorker(QThread):
    done = Signal(object)
    failed = Signal(str)

    def run(self):
        try:
            self.done.emit(go.read_status())
        except Exception as e:
            self.failed.emit(str(e))


class GameModeTab(QWidget):
    """CachyOS odaklı sistemsel oyun optimizasyon paneli (Mayıs 2026 güncel)."""

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)

        # Kaydırılabilir alan
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        container = QWidget(); root = QVBoxLayout(container)
        scroll.setWidget(container)
        outer.addWidget(scroll, 1)

        # --- Üst: durum özeti
        self.status_box = QGroupBox(_("Sistem Durumu"))
        self.status_form = QFormLayout(self.status_box)
        root.addWidget(self.status_box)

        # --- Hızlı uygula
        rec_box = QGroupBox(_("CS2 / Rekabetçi FPS için Önerilenler"))
        rec_lay = QVBoxLayout(rec_box)
        self.rec_log = QTextEdit(); self.rec_log.setReadOnly(True); self.rec_log.setMaximumHeight(160)
        rec_lay.addWidget(self.rec_log)
        row = QHBoxLayout()
        self.apply_all_btn = QPushButton(_("Önerilenleri sırayla uygula"))
        self.apply_all_btn.setStyleSheet("font-weight:bold;")
        self.apply_all_btn.clicked.connect(self._apply_all)
        row.addWidget(self.apply_all_btn)
        self.refresh_btn = QPushButton(_("Durumu yenile"))
        self.refresh_btn.clicked.connect(self.reload)
        row.addWidget(self.refresh_btn)
        row.addStretch(1)
        rec_lay.addLayout(row)
        root.addWidget(rec_box)

        # --- CPU & Power
        cpu_box = QGroupBox(_("CPU & Güç"))
        f = QFormLayout(cpu_box)
        self.gov_combo = QComboBox(); self.gov_combo.addItems(["performance", "schedutil", "powersave", "ondemand"])
        gov_btn = QPushButton(_("Uygula"))
        gov_btn.clicked.connect(lambda: confirm_and_run(self, go.cmd_set_governor(self.gov_combo.currentText())))
        f.addRow(_("Governor:"), self._hbox(self.gov_combo, gov_btn))

        self.epp_combo = QComboBox(); self.epp_combo.addItems(
            ["performance", "balance_performance", "balance_power", "power"])
        epp_btn = QPushButton(_("Uygula (AMD EPP)"))
        epp_btn.clicked.connect(lambda: confirm_and_run(self, go.cmd_set_epp(self.epp_combo.currentText())))
        f.addRow(_("AMD EPP:"), self._hbox(self.epp_combo, epp_btn))

        self.ppd_combo = QComboBox(); self.ppd_combo.addItems(["performance", "balanced", "power-saver"])
        prof_btn = QPushButton(_("Uygula"))
        prof_btn.clicked.connect(lambda: confirm_and_run(self, go.cmd_power_profile(self.ppd_combo.currentText())))
        f.addRow(_("Güç profili (PPD):"), self._hbox(self.ppd_combo, prof_btn))

        self.x3d_combo = QComboBox(); self.x3d_combo.addItems(["cache", "frequency"])
        x3d_btn = QPushButton(_("Uygula"))
        x3d_btn.clicked.connect(lambda: confirm_and_run(self, go.cmd_amd_x3d_mode(self.x3d_combo.currentText())))
        f.addRow(_("AMD 3D V-Cache:"), self._hbox(self.x3d_combo, x3d_btn))
        root.addWidget(cpu_box)

        # --- Scheduler
        sched_box = QGroupBox(_("Sched-ext (CachyOS scheduler)"))
        sf = QFormLayout(sched_box)
        self.sched_combo = QComboBox(); self.sched_combo.addItems(
            ["scx_bpfland", "scx_lavd", "scx_rusty", "scx_rustland", "scx_flash"])
        sched_apply = QPushButton(_("Etkinleştir (Gaming)"))
        sched_apply.clicked.connect(
            lambda: confirm_and_run(self, go.cmd_scx_set_scheduler(self.sched_combo.currentText(), "gaming")))
        sched_stop = QPushButton(_("Kapat"))
        sched_stop.clicked.connect(lambda: confirm_and_run(self, go.cmd_scx_stop()))
        sf.addRow(_("Scheduler:"), self._hbox(self.sched_combo, sched_apply, sched_stop))
        note = QLabel(_(
            "<i>Not: 2026/05 itibariyle hybrid CPU'larda <b>scx_bpfland Gaming</b> en stabil seçenek. "
            "scx_lavd'da bilinen bellek sızıntısı (#3340) var.</i>"
        ))
        note.setWordWrap(True); sf.addRow(note)
        root.addWidget(sched_box)

        # --- Bellek
        mem_box = QGroupBox(_("Bellek"))
        mf = QFormLayout(mem_box)
        self.swap_spin = QSpinBox(); self.swap_spin.setRange(0, 200); self.swap_spin.setValue(10)
        swap_btn = QPushButton(_("Uygula (kalıcı)"))
        swap_btn.clicked.connect(
            lambda: confirm_and_run(self, go.cmd_set_swappiness(self.swap_spin.value(), persist=True)))
        mf.addRow(_("Swappiness:"), self._hbox(self.swap_spin, swap_btn))

        self.mapcount_btn = QPushButton(_("vm.max_map_count = 1048576 (kalıcı)"))
        self.mapcount_btn.clicked.connect(
            lambda: confirm_and_run(self, go.cmd_sysctl({"vm.max_map_count": "1048576"}, persist=True)))
        mf.addRow(self.mapcount_btn)

        self.thp_combo = QComboBox(); self.thp_combo.addItems(["madvise", "always", "never"])
        thp_btn = QPushButton(_("Uygula (oturum)"))
        thp_btn.clicked.connect(lambda: confirm_and_run(self, go.cmd_set_thp(self.thp_combo.currentText())))
        mf.addRow(_("Transparent Hugepage:"), self._hbox(self.thp_combo, thp_btn))

        zram_btn = QPushButton(_("zram kur (RAM/2, lz4)"))
        zram_btn.clicked.connect(lambda: confirm_and_run(self, go.cmd_setup_zram()))
        mf.addRow(zram_btn)
        pipewire_btn = QPushButton(_("PipeWire RT önceliği ver"))
        pipewire_btn.clicked.connect(lambda: confirm_and_run(self, go.cmd_pipewire_rt()))
        mf.addRow(pipewire_btn)
        root.addWidget(mem_box)

        # --- Ağ
        net_box = QGroupBox(_("Ağ (online oyun gecikmesi)"))
        nf = QFormLayout(net_box)
        bbr_btn = QPushButton(_("TCP BBR + fq qdisc aktif et (kalıcı)"))
        bbr_btn.clicked.connect(lambda: confirm_and_run(self, go.cmd_enable_bbr(persist=True)))
        nf.addRow(bbr_btn)
        root.addWidget(net_box)

        # --- GPU
        gpu_box = QGroupBox(_("GPU"))
        gf = QFormLayout(gpu_box)
        nv_btn = QPushButton(_("NVIDIA: Prefer Maximum Performance (oturum)"))
        nv_btn.clicked.connect(lambda: confirm_and_run(self, go.cmd_nvidia_max_perf()))
        gf.addRow(nv_btn)
        amd_btn = QPushButton(_("AMD GPU: performance level = high"))
        amd_btn.clicked.connect(lambda: confirm_and_run(self, go.cmd_amd_gpu_perf_level("high")))
        amd_auto = QPushButton(_("AMD GPU: auto'ya döndür"))
        amd_auto.clicked.connect(lambda: confirm_and_run(self, go.cmd_amd_gpu_perf_level("auto")))
        gf.addRow(self._hbox(amd_btn, amd_auto))
        root.addWidget(gpu_box)

        # --- KWin compositor
        kwin_box = QGroupBox(_("KDE / KWin Compositor"))
        kf = QFormLayout(kwin_box)
        suspend_btn = QPushButton(_("Compositing'i askıya al (Shift+Alt+F12 eşdeğeri)"))
        suspend_btn.clicked.connect(lambda: confirm_and_run(self, go.cmd_kwin_compositor_suspend()))
        resume_btn = QPushButton(_("Compositing'i geri aç"))
        resume_btn.clicked.connect(lambda: confirm_and_run(self, go.cmd_kwin_compositor_resume()))
        kf.addRow(self._hbox(suspend_btn, resume_btn))
        tear_on = QPushButton(_("AllowTearing açık (VRR / düşük gecikme)"))
        tear_on.clicked.connect(lambda: confirm_and_run(self, go.cmd_kwin_allow_tearing(True)))
        tear_off = QPushButton(_("AllowTearing kapalı"))
        tear_off.clicked.connect(lambda: confirm_and_run(self, go.cmd_kwin_allow_tearing(False)))
        kf.addRow(self._hbox(tear_on, tear_off))
        root.addWidget(kwin_box)

        # --- Geri Al (varsayılanlara dön)
        rv_box = QGroupBox(_("Geri Al (varsayılanlara dön)"))
        rf = QFormLayout(rv_box)
        rv_sysctl = QPushButton(_("Abrek sysctl ayarlarını kaldır + eski değerleri geri yükle"))
        rv_sysctl.clicked.connect(lambda: confirm_and_run(self, go.cmd_revert_sysctl()))
        rf.addRow(rv_sysctl)
        gov_auto = QPushButton(_("Governor: schedutil"))
        gov_auto.clicked.connect(lambda: confirm_and_run(self, go.cmd_set_governor("schedutil")))
        epp_auto = QPushButton(_("EPP: balance_performance"))
        epp_auto.clicked.connect(lambda: confirm_and_run(self, go.cmd_set_epp("balance_performance")))
        prof_bal = QPushButton(_("Güç profili: balanced"))
        prof_bal.clicked.connect(lambda: confirm_and_run(self, go.cmd_power_profile("balanced")))
        thp_back = QPushButton(_("THP: madvise"))
        thp_back.clicked.connect(lambda: confirm_and_run(self, go.cmd_set_thp("madvise")))
        swap_back = QPushButton(_("Swappiness: 60"))
        swap_back.clicked.connect(lambda: confirm_and_run(self, go.cmd_set_swappiness(60, persist=True)))
        scx_back = QPushButton(_("scx scheduler'i kapat"))
        scx_back.clicked.connect(lambda: confirm_and_run(self, go.cmd_scx_stop()))
        rf.addRow(self._hbox(gov_auto, epp_auto, prof_bal, thp_back, swap_back, scx_back))
        root.addWidget(rv_box)

        # --- Paket kurulum kısayolları
        pkg_box = QGroupBox(_("Eksik paketleri kur (CachyOS / Arch)"))
        pf = QFormLayout(pkg_box)
        meta_btn = QPushButton(_("cachyos-gaming-meta + cachyos-gaming-applications"))
        meta_btn.clicked.connect(lambda: confirm_and_run(self, 
            go.install_packages_command(["cachyos-gaming-meta", "cachyos-gaming-applications"])))
        pf.addRow(meta_btn)
        scx_btn = QPushButton(_("scx-scheds + scx_loader"))
        scx_btn.clicked.connect(lambda: confirm_and_run(self, go.install_packages_command(["scx-scheds"])))
        pf.addRow(scx_btn)
        misc_btn = QPushButton(_("gamemode + gamescope + mangohud"))
        misc_btn.clicked.connect(lambda: confirm_and_run(self, 
            go.install_packages_command(["gamemode", "lib32-gamemode", "gamescope", "mangohud", "lib32-mangohud"])))
        pf.addRow(misc_btn)
        ananicy_btn = QPushButton(_("ananicy-cpp (oyun süreçlerine otomatik öncelik)"))
        ananicy_btn.clicked.connect(lambda: confirm_and_run(self, 
            go.install_packages_command(["ananicy-cpp", "cachyos-ananicy-rules-git"])))
        pf.addRow(ananicy_btn)
        proton_btn = QPushButton(_("proton-cachyos (Steam'de seçilebilir hale gelir)"))
        proton_btn.clicked.connect(lambda: confirm_and_run(self, 
            go.install_packages_command(["proton-cachyos"])))
        pf.addRow(proton_btn)
        root.addWidget(pkg_box)

        # --- Servisler
        svc_box = QGroupBox(_("Servisler"))
        sf2 = QFormLayout(svc_box)
        for unit, label in [
            ("scx_loader.service", "scx_loader"),
            ("ananicy-cpp.service", "ananicy-cpp"),
            ("irqbalance.service", "irqbalance"),
            ("power-profiles-daemon.service", "power-profiles-daemon"),
        ]:
            on = QPushButton(_("Aç"))
            on.clicked.connect(lambda _c=False, u=unit: confirm_and_run(self, go.cmd_enable_service(u)))
            off = QPushButton(_("Kapat"))
            off.clicked.connect(lambda _c=False, u=unit: confirm_and_run(self, go.cmd_disable_service(u)))
            sf2.addRow(label, self._hbox(on, off))
        root.addWidget(svc_box)

        # --- Profiller
        prof_box = QGroupBox(_("Profiller"))
        pf2 = QFormLayout(prof_box)
        self.profile_combo = QComboBox()
        prof_row = QHBoxLayout()
        save_p = QPushButton(_("Mevcut durumu kaydet"))
        save_p.clicked.connect(self._profile_save)
        apply_p = QPushButton(_("Uygula"))
        apply_p.clicked.connect(self._profile_apply)
        del_p = QPushButton(_("Sil"))
        del_p.clicked.connect(self._profile_delete)
        for b in (save_p, apply_p, del_p):
            prof_row.addWidget(b)
        pf2.addRow(_("Profil:"), self.profile_combo)
        wrap = QWidget(); wrap.setLayout(prof_row)
        pf2.addRow(wrap)
        root.addWidget(prof_box)
        self._refresh_profiles()

        root.addStretch(1)

        self._recommendations: list[go.Recommendation] = []
        self._worker: GameStatusWorker | None = None
        self._last_status = None
        self._pending_score: int | None = None
        self.reload()

    def _hbox(self, *widgets) -> QWidget:
        w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(0, 0, 0, 0)
        for x in widgets:
            h.addWidget(x)
        h.addStretch(1)
        return w

    def reload(self):
        if self._worker and self._worker.isRunning():
            return
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText(_("Yükleniyor..."))
        self._worker = GameStatusWorker()
        self._worker.done.connect(self._render_status)
        self._worker.failed.connect(self._status_failed)
        self._worker.start()

    def _render_status(self, st):
        # Eski worker'dan gelen sonucu yoksay
        if self.sender() is not self._worker:
            return
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText(_("Durumu yenile"))
        self._last_status = st
        # PPD yalnızca bu makinenin desteklediği profilleri göstersin
        avail = go.ppd_available_profiles()
        if avail:
            cur = self.ppd_combo.currentText()
            self.ppd_combo.clear()
            self.ppd_combo.addItems([p for p in ("performance", "balanced", "power-saver") if p in avail])
            if cur:
                i = self.ppd_combo.findText(cur)
                if i >= 0:
                    self.ppd_combo.setCurrentIndex(i)
        # Form'u temizle
        while self.status_form.rowCount():
            self.status_form.removeRow(0)

        def row(k, v):
            # Satır etiketlerini çeviri anahtarları üzerinden göster
            self.status_form.addRow(QLabel(f"<b>{_(k)}</b>"), QLabel(str(v) if v != "" else "—"))

        row("Kernel", f"{st.kernel}  " + ("✓ CachyOS" if st.is_cachyos_kernel else ""))
        if st.cachyos_kernel_pkg:
            row("Kernel paketi", st.cachyos_kernel_pkg)
        row("CPU", f"{st.cpu_model}  ({st.cpu_vendor})")
        row("CPU sürücüsü", st.cpu_driver)
        row("Governor", st.cpu_governor)
        if st.epp:
            row("AMD EPP", st.epp)
        row("Güç profili (PPD)", st.power_profile)
        row("Çalışan SCX", st.scx_running or _("(kapalı)"))
        row("scx_loader servisi", st.scx_loader_service)
        row("TCP congestion", f"{st.tcp_cc}  |  qdisc: {st.tcp_qdisc}")
        row("Swappiness", st.swappiness)
        row("vm.max_map_count", st.vm_max_map_count)
        row("Transparent Hugepage", st.thp)
        row("zram / zswap", f"zram={_('aktif') if st.zram_active else _('kapalı')}  |  zswap={_('aktif') if st.zswap_enabled else _('kapalı')}")
        row("GPU", f"{st.gpu_vendor}  {st.gpu_name}")
        if st.amd_x3d_mode:
            row("AMD 3D V-Cache modu", st.amd_x3d_mode)
        row("Mitigations off", _("EVET") if st.mitigations_off else _("hayır"))
        row("Oturum tipi", st.compositor)
        row("Paketler",
            f"gamemode={'✓' if st.has_gamemode else '✗'} "
            f"gamescope={'✓' if st.has_gamescope else '✗'} "
            f"mangohud={'✓' if st.has_mangohud else '✗'} "
            f"game-performance={'✓' if st.has_game_performance else '✗'} "
            f"scx_loader={'✓' if st.has_scx_loader else '✗'} "
            f"proton-cachyos={'✓' if st.has_proton_cachyos else '✗'} "
            f"ananicy-cpp={'✓' if st.has_ananicy_cpp else '✗'} "
            f"cachyos-gaming-meta={'✓' if st.has_cachyos_gaming_meta else '✗'}")

        # önerileri üret
        self._recommendations = go.recommended_for_competitive_fps(st)
        new_score = self._health_score(self._recommendations)
        if self._pending_score is not None:
            delta = new_score - self._pending_score
            sign = "+" if delta >= 0 else ""
            msg = _("Uygulama sonrası sağlık skoru: <b>{s}/100</b> ({sign}{d})").format(
                s=new_score, sign=sign, d=delta)
            self.rec_log.append(msg)
            notify(_("Optimizasyon skoru"), f"{new_score}/100 ({sign}{delta})")
            history.record("skor_degisimi", f"{self._pending_score} → {new_score}")
            self._pending_score = None
        if not self._recommendations:
            self.rec_log.setHtml(_(
                "<b>✓ Sistem zaten optimize görünüyor.</b><br/>"
                "Oyunu başlatırken Steam launch options'a "
                "<code>game-performance %command%</code> eklemeyi unutmayın."
            ))
        else:
            lines = [_("<b>Şu öneriler uygulanabilir:</b><br/>")]
            for i, r in enumerate(self._recommendations, 1):
                lines.append(f"{i}. <b>{r.title}</b> — {r.rationale}")
            self.rec_log.setHtml("<br/>".join(lines))

    def _health_score(self, recs) -> int:
        crit = sum(1 for r in recs if r.severity == "critical")
        warn = sum(1 for r in recs if r.severity == "warn")
        return max(0, 100 - 15 * crit - 5 * warn)

    def _status_failed(self, msg: str):
        if self.sender() is not self._worker:
            return
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText(_("Durumu yenile"))
        QMessageBox.warning(self, _("Hata"), msg)

    def _apply_all(self):
        if not self._recommendations:
            QMessageBox.information(self, _("Bilgi"), _("Uygulanacak öneri yok."))
            return
        body = "\n".join(f"{i}. {r.title}" for i, r in enumerate(self._recommendations, 1))
        reply = QMessageBox.warning(
            self, _("Onayla"),
            _("Toplam {n} öneri terminalde sırayla çalıştırılacak.").format(n=len(self._recommendations))
            + f"\n\n{body}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        # Tüm komutları tek terminalde && ile zincirle (kullanıcı bir kez şifre girer)
        import shlex
        chain = []
        for r in self._recommendations:
            for cmd in r.commands:
                chain.append(" ".join(shlex.quote(c) for c in cmd))
        full = " ; ".join(chain) if chain else "echo 'Uygulanacak komut yok (sadece bilgi önerileri).'"
        history.record("oneri_uygulama", f"{len(self._recommendations)} öneri")
        self._pending_score = self._health_score(self._recommendations)
        run_in_app(self, _("Öneriler uygulanıyor"), ["bash", "-lc", full])
        self.reload()

    # ---------- Profil yönetimi ----------
    def _refresh_profiles(self):
        self.profile_combo.clear()
        for name in prof.load_all():
            self.profile_combo.addItem(name)

    def _profile_save(self):
        if self._last_status is None:
            QMessageBox.information(self, _("Bilgi"), _("Önce 'Durumu yenile' ile durum okunmalı."))
            return
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, _("Profil adı"), _("Profil adı:"))
        if not ok or not name.strip():
            return
        profiles = prof.load_all()
        profiles[name.strip()] = prof.Profile(name=name.strip(), **prof.capture_from_status(self._last_status))
        prof.save_all(profiles)
        self._refresh_profiles()
        history.record("profil_kayit", name.strip())

    def _profile_apply(self):
        name = self.profile_combo.currentText()
        if not name:
            QMessageBox.information(self, _("Bilgi"), _("Kayıtlı profil yok."))
            return
        p = prof.load_all().get(name)
        if p is None:
            return
        cmds = p.commands()
        if not cmds:
            QMessageBox.information(self, _("Bilgi"), _("Bu profilde uygulanacak ayar yok."))
            return
        import shlex
        full = " ; ".join(" ".join(shlex.quote(x) for x in cmd) for cmd in cmds)
        reply = QMessageBox.question(
            self, _("Onayla"),
            _("'{name}' profili uygulanacak. Emin misiniz?").format(name=name),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        history.record("profil_uygulama", name)
        if self._recommendations is not None:
            self._pending_score = self._health_score(self._recommendations)
        run_in_app(self, f"{_('Profil')}: {name}", ["bash", "-lc", full])
        self.reload()

    def _profile_delete(self):
        name = self.profile_combo.currentText()
        if not name:
            return
        profiles = prof.load_all()
        if name in profiles:
            del profiles[name]
            prof.save_all(profiles)
            self._refresh_profiles()
            history.record("profil_silme", name)


# ---------- Sistem özeti sekmesi ----------
class OverviewTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        grid = QHBoxLayout()
        self.cpu_bar = self._meter(_("CPU"))
        self.mem_bar = self._meter(_("RAM"))
        self.gpu_bar = self._meter(_("GPU"))
        self.disk_bar = self._meter(_("Disk /"))
        for w in (self.cpu_bar, self.mem_bar, self.gpu_bar, self.disk_bar):
            grid.addWidget(w)
        layout.addLayout(grid)

        self.info_lbl = QLabel("—")
        self.info_lbl.setTextFormat(Qt.RichText)
        layout.addWidget(self.info_lbl)

        self.score_lbl = QLabel(_("<b>Sağlık skoru:</b> hesaplanıyor..."))
        layout.addWidget(self.score_lbl)

        self.status_box = QGroupBox(_("Sistem Durumu"))
        self.status_form = QFormLayout(self.status_box)
        layout.addWidget(self.status_box, 1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick_bars)
        self.timer.start(1500)
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self.reload)
        self._status_timer.start(10_000)
        self._worker = None
        self.reload()
        self._tick_bars()

    def _meter(self, label: str) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w); v.setContentsMargins(4, 4, 4, 4)
        lbl = QLabel(f"<b>{label}</b>"); lbl.setAlignment(Qt.AlignCenter)
        bar = QProgressBar(); bar.setRange(0, 100)
        v.addWidget(lbl); v.addWidget(bar)
        w.bar = bar
        return w

    def _tick_bars(self):
        try:
            s = pm.snapshot()
        except Exception:
            return
        self.cpu_bar.bar.setValue(int(s.cpu_percent))
        self.mem_bar.bar.setValue(int(s.mem_percent))
        self.gpu_bar.bar.setValue(int(s.gpu_busy))
        self.disk_bar.bar.setValue(int(s.disk_percent))
        up = pm.format_uptime(pm.uptime_seconds())
        self.info_lbl.setText(
            _("Açık kalma: <b>{up}</b> &nbsp;|&nbsp; CPU: {cpu:.0f}°C &nbsp;|&nbsp; "
              "RAM: <b>{used}</b> / {total} &nbsp;|&nbsp; Disk: <b>{dused}</b> / {dtotal} &nbsp;|&nbsp; "
              "Süreç: <b>{procs}</b> &nbsp;|&nbsp; Yük: {l1:.2f}").format(
                up=up, cpu=s.cpu_temp_c, used=cl.human_size(s.mem_used),
                total=cl.human_size(s.mem_total), dused=cl.human_size(s.disk_used),
                dtotal=cl.human_size(s.disk_total), procs=s.process_count, l1=s.load_avg[0])
        )

    def reload(self):
        if self._worker and self._worker.isRunning():
            return
        self._worker = GameStatusWorker()
        self._worker.done.connect(self._render)
        self._worker.start()

    def _render(self, st):
        if self.sender() is not self._worker:
            return
        while self.status_form.rowCount():
            self.status_form.removeRow(0)

        def row(k, v):
            self.status_form.addRow(QLabel(f"<b>{k}</b>"), QLabel(str(v) if v != "" else "—"))

        row(_("Kernel"), f"{st.kernel}  " + ("✓ CachyOS" if st.is_cachyos_kernel else ""))
        row(_("CPU"), f"{st.cpu_model} ({st.cpu_vendor})")
        row(_("Governor"), st.cpu_governor)
        row(_("Güç profili (PPD)"), st.power_profile)
        row(_("Çalışan SCX"), st.scx_running or _("(kapalı)"))
        row(_("TCP congestion"), f"{st.tcp_cc} | {st.tcp_qdisc}")
        row(_("Swappiness"), st.swappiness)
        row(_("Transparent Hugepage"), st.thp)
        row("zram / zswap", f"zram={'aktif' if st.zram_active else 'kapalı'} | zswap={'aktif' if st.zswap_enabled else 'kapalı'}")
        row(_("GPU"), f"{st.gpu_vendor} {st.gpu_name}")
        row(_("Mitigations off"), _("EVET") if st.mitigations_off else _("hayır"))

        try:
            recs = go.recommended_for_competitive_fps(st)
        except Exception:
            recs = []
        crit = sum(1 for r in recs if r.severity == "critical")
        warn = sum(1 for r in recs if r.severity == "warn")
        score = max(0, 100 - 15 * crit - 5 * warn)
        try:
            s = pm.snapshot()
            trend.record_sample(score, s.disk_used, s.mem_used)
        except Exception:
            pass
        self.score_lbl.setText(
            _("<b>Sağlık skoru: {score}/100</b> — {crit} kritik, {warn} uyarı önerisi var.").format(
                score=score, crit=crit, warn=warn)
        )


# ---------- İşlem geçmişi sekmesi ----------
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


# ---------- Disk analizi sekmesi ----------
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


# ---------- Sistem raporu sekmesi ----------
class BenchWorker(QThread):
    done = Signal(dict)

    def run(self):
        import math
        import os
        import tempfile
        import time
        import pathlib
        res: dict = {}
        try:
            t0 = time.perf_counter()
            n = 0
            while time.perf_counter() - t0 < 2.0:
                n += int(math.factorial(20) % 9973 + math.sqrt(n + 1))
            res["cpu_score"] = n / (time.perf_counter() - t0)
        except Exception:
            res["cpu_score"] = 0.0
        try:
            buf = bytearray(50 * 1024 * 1024)
            t0 = time.perf_counter()
            for _ in range(5):
                _copy = buf[:]
            res["mem_gbps"] = 5 * len(buf) / (time.perf_counter() - t0) / 1e9
        except Exception:
            res["mem_gbps"] = 0.0
        try:
            p = pathlib.Path(tempfile.gettempdir()) / "abrek_bench.tmp"
            data = os.urandom(64 * 1024 * 1024)
            t0 = time.perf_counter()
            p.write_bytes(data)
            res["disk_mbps"] = len(data) / (time.perf_counter() - t0) / 1e6
            try:
                p.unlink()
            except OSError:
                pass
        except Exception:
            res["disk_mbps"] = 0.0
        self.done.emit(res)


class ReportTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.view = QTextEdit()
        self.view.setReadOnly(True)
        layout.addWidget(self.view, 1)
        row = QHBoxLayout()
        btn = QPushButton(_("Raporu yenile"))
        btn.clicked.connect(self.reload)
        row.addWidget(btn)
        self.bench_btn = QPushButton(_("Benchmark çalıştır (~8sn)"))
        self.bench_btn.clicked.connect(self.run_bench)
        row.addWidget(self.bench_btn)
        row.addStretch(1)
        layout.addLayout(row)
        self.bench_log = QPlainTextEdit()
        self.bench_log.setReadOnly(True)
        self.bench_log.setMaximumHeight(110)
        self.bench_log.setPlaceholderText(_("Benchmark sonuçları burada görünür..."))
        layout.addWidget(self.bench_log)
        self._worker = None
        self._bench_worker = None
        self.reload()

    def run_bench(self):
        if self._bench_worker and self._bench_worker.isRunning():
            return
        self.bench_btn.setEnabled(False)
        self.bench_log.appendPlainText(_("Benchmark başladı..."))
        self._bench_worker = BenchWorker()
        self._bench_worker.done.connect(self._bench_done)
        self._bench_worker.start()

    def _bench_done(self, res: dict):
        if self.sender() is not self._bench_worker:
            return
        self.bench_log.appendPlainText(
            _("CPU ~{cpu:,.0f} op/s | Bellek kopyalama ~{mem:.1f} GB/s | Disk yazma ~{disk:.0f} MB/s").format(
                cpu=res["cpu_score"], mem=res["mem_gbps"], disk=res["disk_mbps"])
        )
        history.record("benchmark", f"cpu={res['cpu_score']:.0f} mem={res['mem_gbps']:.1f}GB/s disk={res['disk_mbps']:.0f}MB/s")
        self.bench_btn.setEnabled(True)

    def reload(self):
        if self._worker and self._worker.isRunning():
            return
        self._worker = GameStatusWorker()
        self._worker.done.connect(self._render)
        self._worker.failed.connect(lambda m: self.view.setHtml(f"<b>{_('Hata')}:</b> {m}"))
        self._worker.start()

    def _render(self, st):
        if self.sender() is not self._worker:
            return
        import datetime
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        try:
            recs = go.recommended_for_competitive_fps(st)
        except Exception:
            recs = []
        crit = [r for r in recs if r.severity == "critical"]
        warn = [r for r in recs if r.severity == "warn"]
        score = max(0, 100 - 15 * len(crit) - 5 * len(warn))
        try:
            s = pm.snapshot()
            disk_free = s.disk_total - s.disk_used
            disk_txt = f"{cl.human_size(s.disk_used)} / {cl.human_size(s.disk_total)} (boş: {cl.human_size(disk_free)})"
            mem_txt = f"{cl.human_size(s.mem_used)} / {cl.human_size(s.mem_total)}"
        except Exception:
            disk_txt = mem_txt = "—"
        last = history.entries(limit=8)
        hist_html = "".join(
            f"<li>{datetime.datetime.fromtimestamp(e.get('ts', 0)).strftime('%m-%d %H:%M')} — "
            f"{e.get('action', '')} {e.get('detail', '')}</li>" for e in last
        ) or f"<li>{_('(kayıt yok)')}</li>"
        rec_html = "".join(
            f"<li><b>[{r.severity}]</b> {r.title}</li>" for r in recs[:8]
        ) or f"<li>{_('✓ Öneri yok — sistem optimize görünüyor.')}</li>"
        trend_samples = trend.samples(limit=6)
        trend_html = "".join(
            f"<li>{datetime.datetime.fromtimestamp(e['ts']).strftime('%m-%d %H:%M')} — "
            f"skor {e.get('score', '?')}/100, disk {cl.human_size(e.get('disk_used', 0))}</li>"
            for e in reversed(trend_samples)
        ) or f"<li>{_('(henüz örnek yok)')}</li>"
        self.view.setHtml(f"""
        <h2>Abrek Optimizer — {_('Sistem Raporu')} ({now})</h2>
        <h3>{_('Özet')}</h3>
        <p><b>{_('Sağlık skoru')}:</b> {score}/100 &nbsp;|&nbsp;
           <b>{_('Kernel')}:</b> {st.kernel} &nbsp;|&nbsp;
           <b>{_('Governor')}:</b> {st.cpu_governor} &nbsp;|&nbsp;
           <b>{_('Güç profili')}:</b> {st.power_profile}</p>
        <p><b>{_('RAM')}:</b> {mem_txt} &nbsp;|&nbsp; <b>{_('Disk')}:</b> {disk_txt} &nbsp;|&nbsp;
           <b>zram:</b> {'✓' if st.zram_active else '✗'} &nbsp;|&nbsp;
           <b>{_('TCP')}:</b> {st.tcp_cc}/{st.tcp_qdisc} &nbsp;|&nbsp;
           <b>scx:</b> {st.scx_running or _('(kapalı)')}</p>
        <h3>{_('Öneriler')} ({len(recs)})</h3><ul>{rec_html}</ul>
        <h3>{_('Trend (son örnekler)')}</h3><ul>{trend_html}</ul>
        <h3>{_('Son işlemler')}</h3><ul>{hist_html}</ul>
        """)


# ---------- Uygulama içi komut çalıştırıcı (canlı çıktı) ----------
class CommandDialog(QDialog):
    def __init__(self, parent, title: str, cmd: list[str]):
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 420)
        self._cmd = cmd
        lay = QVBoxLayout(self)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        lay.addWidget(self.log, 1)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)  # belirsiz; ilerleme bulununca yüzdeliye döner
        lay.addWidget(self.bar)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.Close).setEnabled(False)
        lay.addWidget(self.buttons)

        from PySide6.QtCore import QProcess
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._on_out)
        self.proc.finished.connect(self._on_done)
        self.proc.start(cmd[0], cmd[1:])

    def _on_out(self):
        data = bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        self.log.appendPlainText(data.rstrip("\n"))
        self._update_progress(data)

    def _update_progress(self, text: str):
        import re
        # pacman: "(2/10) Installing: ..." veya "1/5"
        m = list(re.finditer(r"\((\d+)\s*/\s*(\d+)\)", text)) or list(re.finditer(r"\b(\d+)/(\d+)\b", text))
        if m:
            a, b = int(m[-1].group(1)), int(m[-1].group(2))
            if b > 0:
                self.bar.setRange(0, 100)
                self.bar.setValue(int(a * 100 / b))
                return
        # apt/dnf: "Progress: [ 50%]" / "[#####-----] 50%"
        p = list(re.finditer(r"(\d{1,3})\s*%", text))
        if p and ("Progress" in text or "]" in text):
            self.bar.setRange(0, 100)
            self.bar.setValue(min(100, int(p[-1].group(1))))

    def _on_done(self, code: int, _status):
        self.bar.setRange(0, 100)
        self.bar.setValue(100 if code == 0 else 0)
        self.log.appendPlainText(f"\n[çıkış kodu: {code}]")
        history.record("komut", " ".join(self._cmd[:3]), ok=code == 0)
        notify(_("İşlem tamamlandı"), f"{' '.join(self._cmd[:3])}... (kod {code})")
        self.buttons.button(self.buttons.Close).setEnabled(True)

    def closeEvent(self, ev):
        # Pencere kapatılsa bile çalışan süreç askıda kalmasın
        if self.proc and self.proc.state() == QProcess.Running:
            self.proc.kill()
            self.proc.waitForFinished(2000)
        super().closeEvent(ev)


def run_in_app(parent, title: str, cmd: list[str]) -> None:
    joined = " ".join(cmd)
    needs_sudo = (cmd and cmd[0] == "sudo") or " sudo " in joined or "'sudo'" in joined or joined.startswith("sudo")
    if needs_sudo:
        try:
            r = subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=3)
            sudo_ok = r.returncode == 0
        except Exception:
            sudo_ok = False
        if not sudo_ok:
            # NOPASSWD kuralı yoksa in-app penceresi şifre soramaz → terminale düş
            QMessageBox.information(
                parent, _("Sudo gerekli"),
                _("Bu komut root istiyor; sudo şifresiz kural olmadığı için komut terminalde çalışacak.\n"
                  "Şifresiz çalıştırmak için: cd ~/Masaüstü/\"Abrek Optimizer Linux\" && ./install.sh"),
            )
            run_in_terminal(cmd)
            return

    # Pencere şifre isterse kilitlenir; in-app çalıştırma da sudo her zaman -n ile (parolasız) denesin
    if cmd and cmd[0] == "sudo":
        cmd = ["sudo", "-n", *cmd[1:]]
    elif len(cmd) >= 3 and cmd[0] == "bash":
        cmd = [cmd[0], cmd[1], cmd[2].replace("sudo ", "sudo -n ")]

    dlg = CommandDialog(parent, title, cmd)
    dlg.exec()


_TRAY = None


def notify(title: str, message: str) -> None:
    """Sistem tepsisi bildirimi (tray yoksa sade şekilde yoksay)."""
    global _TRAY
    try:
        from PySide6.QtWidgets import QSystemTrayIcon
        app = QApplication.instance()
        if app is None:
            return
        if _TRAY is None:
            icon = QIcon.fromTheme("abrek-optimizer")
            if icon.isNull():
                icon = app.windowIcon()
            _TRAY = QSystemTrayIcon(icon, app)
            _TRAY.setToolTip(__app_name__)
            _TRAY.show()
        _TRAY.showMessage(title, message, QSystemTrayIcon.Information, 4000)
    except Exception:
        pass


# ---------- Ana pencere ----------
class MainWindow(QMainWindow):
    def __init__(self, pkgmgr: PackageManager):
        super().__init__()
        self.pkgmgr = pkgmgr
        self.setWindowTitle(_("Abrek Program Silme Aracı"))
        self.resize(1100, 720)

        self._create_menu()
        self.setCentralWidget(self._build_tabs())

        sb = QStatusBar(); self.setStatusBar(sb)
        sb.showMessage(self._status_message())

    def _build_tabs(self) -> QTabWidget:
        """Sekmeleri güncel dille kurar; dil değişiminde yeniden kullanılır."""
        tabs = QTabWidget()
        tabs.addTab(OverviewTab(), _("Özet"))
        tabs.addTab(PackagesTab(self.pkgmgr), _("Paketler / Kaldırma"))
        tabs.addTab(CleanerTab(), _("Temizleme"))
        tabs.addTab(AutostartTab(), _("Başlangıç"))
        tabs.addTab(PerfTab(), _("Performans"))
        tabs.addTab(GameModeTab(), _("Oyun Modu"))
        tabs.addTab(DiskTab(), _("Disk Analizi"))
        tabs.addTab(ReportTab(), _("Rapor"))
        tabs.addTab(HistoryTab(), _("Geçmiş"))
        return tabs

    def _status_message(self) -> str:
        return f"{_('Paket yöneticisi')}: {self.pkgmgr.name}  |  {__app_name__} v{__version__}"

    def _create_menu(self):
        menu = self.menuBar()
        lang_menu = menu.addMenu(_("Dil"))
        for code, label in i18n.LANGUAGES.items():
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(i18n.current() == code)
            act.triggered.connect(lambda _checked=False, c=code: self._set_language(c))
            lang_menu.addAction(act)
        help_menu = menu.addMenu(_("Yardım"))
        about = QAction(_("Hakkında"), self)
        about.triggered.connect(self._about)
        help_menu.addAction(about)

    def _set_language(self, code: str):
        # Dili kaydet ve menü/sekmeleri yeniden kur: yeniden başlatma gerekmez.
        i18n.save(code)
        old = self.takeCentralWidget()
        if old:
            # Eski sekmelerdeki zamanlayıcı ve worker thread'lerini durdur
            for child in old.findChildren(QWidget):
                timer = getattr(child, "timer", None)
                if timer is not None:
                    timer.stop()
                for attr in ("_worker", "worker"):
                    worker = getattr(child, attr, None)
                    if worker and worker.isRunning():
                        worker.wait(10000)
        self.menuBar().clear()
        self._create_menu()
        self.setCentralWidget(self._build_tabs())
        if old:
            old.deleteLater()
        self.setWindowTitle(_("Abrek Program Silme Aracı"))
        self.statusBar().showMessage(self._status_message())
        QMessageBox.information(self, _("Bilgi"), _("Dil değiştirildi."))

    def _about(self):
        QMessageBox.about(self, _("Hakkında"), f"<b>{__app_name__}</b> v{__version__}<br/>{_('Abrek Optimizer / CachyOS bakım ve oyun performansı aracı.')}<br/>Log: {applog.log_path()}")

    def closeEvent(self, event):
        # Kapanırken arka plan okuma thread'lerinin bitmesini bekle; aksi halde Qt abort eder.
        for child in self.findChildren(QWidget):
            for attr in ("_worker", "worker"):
                worker = getattr(child, attr, None)
                if worker and worker.isRunning():
                    worker.wait(10000)
        super().closeEvent(event)
