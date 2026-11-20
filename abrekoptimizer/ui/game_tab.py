"""Oyun / Sistem Performans Modu sekmesi."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QScrollArea, QSpinBox, QTextEdit,
    QVBoxLayout, QWidget,
)

from abrekoptimizer.i18n import tr as _
from abrekoptimizer.core import gameopt as go
from abrekoptimizer.core import history
from abrekoptimizer.core import profiles as prof
from abrekoptimizer.ui.runtime import confirm_and_run, notify, run_in_app


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
