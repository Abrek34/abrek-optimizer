"""Sistem raporu sekmesi."""
from __future__ import annotations

import contextlib
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from abrekoptimizer.core import cleaner as cl
from abrekoptimizer.core import gameopt as go
from abrekoptimizer.core import history, trend
from abrekoptimizer.core import perfmon as pm
from abrekoptimizer.i18n import tr as _
from abrekoptimizer.ui.game_tab import GameStatusWorker
from abrekoptimizer.ui.runtime import notify


class BenchWorker(QThread):
    done = Signal(dict)

    def run(self):
        import math
        import os
        import pathlib
        import tempfile
        import time
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
            with contextlib.suppress(OSError):
                p.unlink()
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
        self.export_btn = QPushButton(_("Raporu kaydet..."))
        self.export_btn.clicked.connect(self._export)
        row.addWidget(self.export_btn)
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

    def _export(self):
        from PySide6.QtWidgets import QFileDialog
        path, _filter = QFileDialog.getSaveFileName(
            self, _("Raporu kaydet"), "abrek-rapor.html", "HTML (*.html);;Text (*.txt)")
        if not path:
            return
        try:
            if path.endswith(".txt"):
                # HTML tag'larını temizle
                import re
                txt = re.sub(r"<[^>]+>", "", self.view.toHtml())
                Path(path).write_text(txt, encoding="utf-8")
            else:
                Path(path).write_text(self.view.toHtml(), encoding="utf-8")
            history.record("rapor_kayit", path)
            notify(_("Rapor kaydedildi"), path)
        except OSError as e:
            QMessageBox.warning(self, _("Hata"), str(e))

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
