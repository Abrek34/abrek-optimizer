"""Abrek Optimizer ana pencere - PySide6/Qt6."""
from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QTabWidget,
    QWidget,
)

from abrekoptimizer import __app_name__, __version__, i18n
from abrekoptimizer.core import applog
from abrekoptimizer.core.pkgmanager import PackageManager
from abrekoptimizer.i18n import tr as _
from abrekoptimizer.ui.autostart_tab import AutostartTab
from abrekoptimizer.ui.cleaner_tab import CleanerTab, ScanWorker
from abrekoptimizer.ui.disk_tab import DiskScanWorker, DiskTab
from abrekoptimizer.ui.game_tab import GameModeTab, GameStatusWorker
from abrekoptimizer.ui.history_tab import HistoryTab
from abrekoptimizer.ui.overview_tab import OverviewTab

# Sekmeler (ayrı modüllerden)
from abrekoptimizer.ui.packages_tab import PackageListWorker, PackagesTab
from abrekoptimizer.ui.perf_tab import PerfTab
from abrekoptimizer.ui.report_tab import BenchWorker, ReportTab

# Geriye dönük uyumluluk (eski import yolları)
from abrekoptimizer.ui.runtime import (
    CommandDialog,
    confirm_and_run,
    notify,
    run_in_app,
    run_in_terminal,
    shorten_detail,
)

__all__ = [
    "MainWindow",
    "PackagesTab", "PackageListWorker",
    "CleanerTab", "ScanWorker",
    "AutostartTab",
    "PerfTab",
    "GameModeTab", "GameStatusWorker",
    "OverviewTab",
    "HistoryTab",
    "DiskTab", "DiskScanWorker",
    "ReportTab", "BenchWorker",
    "CommandDialog", "confirm_and_run", "notify", "run_in_app", "run_in_terminal", "shorten_detail",
]


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
