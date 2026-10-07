"""Abrek Optimizer giriş noktası."""
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from abrekoptimizer import __app_id__, __app_name__, i18n
from abrekoptimizer.core import applog
from abrekoptimizer.core.pkgmanager import PackageManager
from abrekoptimizer.ui.main_window import MainWindow


def main() -> int:
    applog.configure()
    i18n.load()
    app = QApplication(sys.argv)
    app.setApplicationName(__app_id__)
    app.setDesktopFileName(__app_id__)
    app.setApplicationDisplayName(i18n.tr("Abrek Program Silme Aracı"))
    # QApplication oluşturulduktan SONRA QMessageBox çağrılabilir.
    try:
        pkgmgr = PackageManager.detect()
    except RuntimeError as e:
        QMessageBox.critical(None, "Abrek", str(e))
        return 1
    win = MainWindow(pkgmgr)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
