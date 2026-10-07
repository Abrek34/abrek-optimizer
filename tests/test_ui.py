"""UI duman testleri (offscreen Qt)."""
from __future__ import annotations

import pytest

QtWidgets = pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtWidgets import QTabWidget  # noqa: E402

from abrekoptimizer.core.pkgmanager import PackageManager  # noqa: E402


@pytest.fixture(scope="session")
def pkgmgr():
    return PackageManager.detect()


def test_main_window_has_seven_tabs(qtbot, pkgmgr):
    from abrekoptimizer.ui.main_window import MainWindow
    w = MainWindow(pkgmgr)
    qtbot.addWidget(w)
    tabs = w.findChild(QTabWidget)
    assert tabs is not None
    assert tabs.count() == 9
    # worker'ların bitmesini bekle (kapatırken abort olmaması için)
    qtbot.wait(2000)


def test_gamemode_health_score(qtbot, pkgmgr):
    from abrekoptimizer.core import gameopt as go
    from abrekoptimizer.ui.main_window import GameModeTab
    tab = GameModeTab()
    qtbot.addWidget(tab)
    # Sahte öneri listesiyle skor hesabı
    recs = [
        go.Recommendation("a", "b", [], "critical"),
        go.Recommendation("c", "d", [], "warn"),
        go.Recommendation("e", "f", [], "info"),
    ]
    assert tab._health_score(recs) == 100 - 15 - 5
    assert tab._health_score([]) == 100
    qtbot.waitUntil(lambda: not (tab._worker and tab._worker.isRunning()), timeout=15000)


def test_profiles_save_load_apply(tmp_path, monkeypatch, qtbot, pkgmgr):
    import abrekoptimizer.core.profiles as prof
    cfg = tmp_path / "abrek"
    monkeypatch.setattr(prof, "PROFILES_FILE", cfg / "profiles.json")
    p = prof.Profile(name="test", governor="performance", bbr=True)
    prof.save_all({"test": p})
    loaded = prof.load_all()
    assert "test" in loaded
    cmds = loaded["test"].commands()
    joined = " ".join(" ".join(c) for c in cmds)
    assert "frequency-set" in joined and "tcp_congestion_control" in joined
