"""Performans sekmesi."""
from __future__ import annotations

import contextlib

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from abrekoptimizer.core import cleaner as cl
from abrekoptimizer.core import perfmon as pm
from abrekoptimizer.i18n import tr as _
from abrekoptimizer.ui.charts import TimeSeriesChart


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

        # Ağ / disk I/O hızları
        self.io_lbl = QLabel("—")
        self.io_lbl.setTextFormat(Qt.RichText)
        layout.addWidget(self.io_lbl)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel(_("Süreç ara:")))
        self.proc_filter = QLineEdit()
        self.proc_filter.setPlaceholderText(_("Ad veya PID..."))
        self.proc_filter.textChanged.connect(self._apply_proc_filter)
        filter_row.addWidget(self.proc_filter, 1)
        layout.addLayout(filter_row)

        # Zaman serisi grafiği
        layout.addWidget(QLabel(_("<b>Zaman serisi (CPU / RAM / GPU)</b>")))
        self.chart = TimeSeriesChart(
            {"CPU": QColor("#4fc3f7"), "RAM": QColor("#81c784"), "GPU": QColor("#ffb74d")})
        layout.addWidget(self.chart)

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
        with contextlib.suppress(Exception):
            self.chart.push({"CPU": s.cpu_percent, "RAM": s.mem_percent, "GPU": s.gpu_busy})
        self.info_lbl.setText(
            _("RAM: <b>{used}</b> / {total} &nbsp;|&nbsp; Disk: <b>{dused}</b> / {dtotal} &nbsp;|&nbsp; "
              "Süreç: <b>{procs}</b> &nbsp;|&nbsp; Yük: {l1:.2f} {l2:.2f} {l3:.2f} &nbsp;|&nbsp; "
              "CPU: {freq:.0f} MHz").format(
                used=cl.human_size(s.mem_used), total=cl.human_size(s.mem_total),
                dused=cl.human_size(s.disk_used), dtotal=cl.human_size(s.disk_total),
                procs=s.process_count, l1=s.load_avg[0], l2=s.load_avg[1], l3=s.load_avg[2],
                freq=s.cpu_freq_mhz,
            )
        )
        self.io_lbl.setText(
            _("Ağ: ↓{dr} ↑{ur} &nbsp;|&nbsp; Disk I/O: R {rr} W {wr}").format(
                dr=cl.human_size(int(s.net_recv_rate)) + "/s",
                ur=cl.human_size(int(s.net_sent_rate)) + "/s",
                rr=cl.human_size(int(s.disk_read_rate)) + "/s",
                wr=cl.human_size(int(s.disk_write_rate)) + "/s",
            )
        )
        try:
            procs = pm.top_processes("memory", 20)
        except Exception:
            procs = []
        self._proc_cache = procs
        self._apply_proc_filter(self.proc_filter.text() if hasattr(self, "proc_filter") else "")

    def _apply_proc_filter(self, text: str = ""):
        t = text.lower().strip()
        rows = getattr(self, "_proc_cache", [])
        if t:
            rows = [p for p in rows if t in str(p.get("name", "")).lower()
                    or t in str(p.get("pid", ""))]
        self._fill_proc_table(rows)

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
            # fazlalık satırları temizle
            if self.proc_table.rowCount() > len(procs):
                self.proc_table.setRowCount(len(procs))
            self.proc_table.setSortingEnabled(True)
        finally:
            self.proc_table.setUpdatesEnabled(True)

    def _kill_selected(self):
        rows = sorted({i.row() for i in self.proc_table.selectedIndexes()})
        if not rows:
            return
        import os
        import signal
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
