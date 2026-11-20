"""Sistem özeti sekmesi."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from abrekoptimizer.core import cleaner as cl
from abrekoptimizer.core import gameopt as go
from abrekoptimizer.core import perfmon as pm
from abrekoptimizer.core import trend
from abrekoptimizer.i18n import tr as _
from abrekoptimizer.ui.game_tab import GameStatusWorker


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
