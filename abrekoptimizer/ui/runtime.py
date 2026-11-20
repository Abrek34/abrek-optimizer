"""Abrek Optimizer UI yardımcıları: terminal/uygulama içi komut çalıştırma, bildirim."""
from __future__ import annotations

import subprocess
from pathlib import Path

from PySide6.QtCore import QProcess
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QMessageBox,
    QPlainTextEdit, QProgressBar, QVBoxLayout,
)

from abrekoptimizer import __app_name__
from abrekoptimizer.i18n import tr as _
from abrekoptimizer.core import applog
from abrekoptimizer.core import history


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
    log.info("terminal command: %s", joined)
    try:
        from abrekoptimizer.core import history
        history.record("terminal_komut", joined[:200])
    except Exception:
        pass
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


class CommandDialog(QDialog):
    def __init__(self, parent, title: str, cmd: list[str]):
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
        self.buttons.button(QDialogButtonBox.Close).setEnabled(True)

    def closeEvent(self, ev):
        # Pencere kapatılsa bile çalışan süreç askıda kalmasın
        if self.proc and self.proc.state() == QProcess.Running:
            self.proc.kill()
            self.proc.waitForFinished(2000)
        super().closeEvent(ev)


def run_in_app(parent, title: str, cmd: list[str]) -> None:
    joined = " ".join(cmd)
    log = applog.get("ui")
    log.info("in-app command: %s", joined[:300])
    try:
        from abrekoptimizer.core import history
        history.record("uygulama_komutu", f"{title}: {joined[:150]}")
    except Exception:
        pass
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
