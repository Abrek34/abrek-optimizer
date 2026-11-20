"""Çekirdek modüller için birim testleri (Qt'süz, saf Python)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from abrekoptimizer.core import autostart, cleaner, gameopt, pkgmanager  # noqa: E402


class TestPkgValidation(unittest.TestCase):
    def test_valid_names(self):
        self.assertEqual(
            pkgmanager.validate_pkg_names(["gimp", "lib32-foo", "python3.12", "x@y+z"]),
            ["gimp", "lib32-foo", "python3.12", "x@y+z"],
        )

    def test_rejects_shell_meta(self):
        for bad in ("x; rm -rf /", "$(whoami)", "a b", "`id`", "-rf", "../../etc/passwd", ""):
            with self.assertRaises(ValueError, msg=bad):
                pkgmanager.validate_pkg_names([bad])

    def test_remove_command_is_argv_no_shell(self):
        p = pkgmanager.Pacman()
        cmd = p.remove_command(["gimp"], purge=True, cascade=True)
        self.assertIsInstance(cmd, list)
        self.assertNotIn("sh", cmd[:2])
        self.assertIn("gimp", cmd)

    def test_apt_cascade_keeps_names_as_argv(self):
        cmd = pkgmanager.Apt().remove_command(["gimp"], purge=False, cascade=True)
        # isim shell string'i içinde değil, argv olarak kalmalı
        self.assertIn("gimp", cmd)
        joined = " ".join(cmd)
        self.assertNotIn("gimp; ", joined)

    def test_autoremove_no_shell_substitution(self):
        for klass in (pkgmanager.Pacman, pkgmanager.Apt, pkgmanager.Dnf, pkgmanager.Zypper):
            cmd = klass().autoremove_command()
            self.assertIsInstance(cmd, list)
            self.assertNotIn("$(", " ".join(cmd))


class TestGameOptSanitize(unittest.TestCase):
    def test_governor_rejects_injection(self):
        with self.assertRaises(ValueError):
            gameopt.cmd_set_governor("performance; reboot")

    def test_sysctl_rejects_bad_key(self):
        with self.assertRaises(ValueError):
            gameopt.cmd_sysctl({"vm.swappiness; rm -rf /": "10"})

    def test_sysctl_rejects_bad_value(self):
        with self.assertRaises(ValueError):
            gameopt.cmd_sysctl({"vm.swappiness": "10; reboot"})

    def test_sysctl_ok(self):
        cmd = gameopt.cmd_sysctl({"vm.swappiness": "10"})
        self.assertIsInstance(cmd, list)
        self.assertIn("vm.swappiness=10", cmd[-1])

    def test_thp_rejects_injection(self):
        with self.assertRaises(ValueError):
            gameopt.cmd_set_thp("always; id")

    def test_amd_x3d_quotes_sysfs_path(self):
        cmd = gameopt.cmd_amd_x3d_mode("cache", "/sys/path with space/f")
        self.assertIn("'/sys/path with space/f'", cmd[-1])


class TestCleanerFreed(unittest.TestCase):
    def test_freed_matches_actual_deletion(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "cache"
            root.mkdir()
            (root / "a.bin").write_bytes(b"x" * 1000)
            sub = root / "sub"
            sub.mkdir()
            (sub / "b.bin").write_bytes(b"y" * 500)
            t = cleaner.CleanTarget("test", [root])
            freed, errors = t.clean()
            self.assertEqual(errors, [])
            self.assertEqual(freed, 1500)
            self.assertTrue(root.exists())  # klasörün kendisi silinmez
            self.assertEqual(list(root.iterdir()), [])

    def test_clean_keeps_dir_on_partial(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "cache"
            root.mkdir()
            (root / "a").write_bytes(b"x" * 10)
            t = cleaner.CleanTarget("test", [root])
            freed, _ = t.clean()
            self.assertEqual(freed, 10)


class TestAutostartPrecedence(unittest.TestCase):
    def test_user_overrides_system(self):
        """Kullanıcı override'ı (/etc/xdg/autostart kaydını) gölgeler — XDG önceliği."""
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            user_dir = home / ".config/autostart"
            sys_dir = home / "etc-xdg"
            user_dir.mkdir(parents=True)
            sys_dir.mkdir()
            content = "[Desktop Entry]\nName=App\nType=Application\nExec=app\n"
            (sys_dir / "app.desktop").write_text(content, encoding="utf-8")
            (user_dir / "app.desktop").write_text(
                content + "Hidden=true\n", encoding="utf-8"
            )
            entries = autostart.list_xdg_autostart([sys_dir, user_dir])
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].path, user_dir / "app.desktop")


    def test_protected_path_skipped(self):
        """Korumalı dizinler (~/.config gibi) temizleme adayından atlanmalı."""
        import abrekoptimizer.core.cleaner as c
        target = Path.home() / ".config" / "abrek"
        assert c._is_protected(target)
        assert not c._is_protected(Path.home() / ".cache" / "mesa_shader_cache")


class TestGameOptNewSanitize(unittest.TestCase):
    def test_epp_rejects_injection(self):
        with self.assertRaises(ValueError):
            gameopt.cmd_set_epp("performance; reboot")

    def test_power_profile_rejects_injection(self):
        with self.assertRaises(ValueError):
            gameopt.cmd_power_profile("performance; id")

    def test_service_unit_rejects_injection(self):
        with self.assertRaises(ValueError):
            gameopt.cmd_enable_service("foo.service; reboot")
        with self.assertRaises(ValueError):
            gameopt.cmd_disable_service("$(id)")

    def test_service_unit_ok(self):
        cmd = gameopt.cmd_enable_service("power-profiles-daemon.service")
        self.assertIn("power-profiles-daemon.service", cmd)

    def test_scx_name_rejects_injection(self):
        with self.assertRaises(ValueError):
            gameopt.cmd_scx_set_scheduler("scx_bpfland; reboot")

    def test_amd_gpu_level_rejects_injection(self):
        with self.assertRaises(ValueError):
            gameopt.cmd_amd_gpu_perf_level("high`id`")


class TestCleanerSymlink(unittest.TestCase):
    def test_symlink_not_followed(self):
        """Symlink'in hedefi silinmemeli; freed link boyutu kadar olmalı."""
        with tempfile.TemporaryDirectory() as d:
            outside = Path(d) / "outside.bin"
            outside.write_bytes(b"z" * 2000)
            root = Path(d) / "cache"
            root.mkdir()
            link = root / "link.bin"
            os.symlink(outside, link)
            t = cleaner.CleanTarget("test", [root])
            freed, errors = t.clean()
            self.assertEqual(errors, [])
            self.assertTrue(outside.exists())  # hedef korunur
            self.assertFalse(link.exists())   # link silinir
            self.assertLess(freed, 100)       # link boyutu küçük

    def test_broken_symlink_no_error(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "cache"
            root.mkdir()
            os.symlink(Path(d) / "nonexistent", root / "broken")
            t = cleaner.CleanTarget("test", [root])
            freed, errors = t.clean()
            self.assertEqual(errors, [])
            self.assertFalse((root / "broken").exists())

    def test_size_uses_lstat(self):
        with tempfile.TemporaryDirectory() as d:
            outside = Path(d) / "big.bin"
            outside.write_bytes(b"z" * 5000)
            root = Path(d) / "cache"
            root.mkdir()
            os.symlink(outside, root / "link")
            t = cleaner.CleanTarget("test", [root])
            self.assertLess(t.size(), 1000)  # 5000 sayılmaz


class TestCleanerExtra(unittest.TestCase):
    def test_tmp_target_has_root_command(self):
        from abrekoptimizer.core import cleaner as cl
        targets = cl.default_targets()
        tmp_targets = [t for t in targets if "Geçici" in t.label or "/tmp" in str(t.paths)]
        self.assertTrue(len(tmp_targets) > 0)
        for t in tmp_targets:
            self.assertIsNotNone(t.root_command, f"{t.label} root_command None")
            self.assertIn("find", t.root_command)

    def test_human_size(self):
        from abrekoptimizer.core import cleaner as cl
        self.assertEqual(cl.human_size(0), "0.0 B")
        self.assertEqual(cl.human_size(1024), "1.0 KB")
        self.assertEqual(cl.human_size(1024 * 1024), "1.0 MB")

    def test_protected_prefixes(self):
        from abrekoptimizer.core import cleaner as cl
        # ~/.config is protected
        self.assertTrue(cl._is_protected(Path.home() / ".config" / "test"))
        # ~/.ssh is protected
        self.assertTrue(cl._is_protected(Path.home() / ".ssh" / "id_rsa"))
        # /tmp is not protected
        self.assertFalse(cl._is_protected(Path("/tmp") / "test.txt"))


class TestAutostart(unittest.TestCase):
    def test_parse_desktop_basic(self):
        import tempfile
        from pathlib import Path
        from abrekoptimizer.core import autostart as au
        content = (
            "[Desktop Entry]\n"
            "Name=Test App\n"
            "Exec=/usr/bin/test-app\n"
            "Comment=A test application\n"
            "Icon=test-icon\n"
            "Hidden=false\n"
        )
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.desktop"
            p.write_text(content)
            entry = au._parse_desktop(p)
            self.assertIsNotNone(entry)
            self.assertEqual(entry.name, "Test App")
            self.assertEqual(entry.exec_cmd, "/usr/bin/test-app")
            self.assertTrue(entry.enabled)
            self.assertEqual(entry.icon, "test-icon")

    def test_parse_desktop_hidden(self):
        import tempfile
        from pathlib import Path
        from abrekoptimizer.core import autostart as au
        content = (
            "[Desktop Entry]\n"
            "Name=Hidden App\n"
            "Exec=/usr/bin/hidden\n"
            "Hidden=true\n"
        )
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "hidden.desktop"
            p.write_text(content)
            entry = au._parse_desktop(p)
            self.assertIsNotNone(entry)
            self.assertFalse(entry.enabled)

    def test_set_xdg_enabled_creates_override(self):
        import tempfile
        from pathlib import Path
        from abrekoptimizer.core import autostart as au
        import unittest.mock as mock
        content = "[Desktop Entry]\nName=Test\nExec=/usr/bin/test\n"
        with tempfile.TemporaryDirectory() as d:
            # patch home
            fake_home = Path(d)
            with mock.patch.object(Path, "home", return_value=fake_home):
                src = fake_home / ".config" / "autostart" / "test.desktop"
                src.parent.mkdir(parents=True, exist_ok=True)
                src.write_text(content)
                entry = au.AutostartEntry(
                    name="Test", path=src, exec_cmd="/usr/bin/test",
                    enabled=True, source="xdg",
                )
                result = au.set_xdg_enabled(entry, False)
                self.assertTrue(result.exists())
                text = result.read_text()
                self.assertIn("Hidden=true", text)


class TestProfiles(unittest.TestCase):
    def test_capture_and_commands(self):
        from abrekoptimizer.core import profiles as prof
        from abrekoptimizer.core import gameopt as go
        st = go.Status(
            cpu_governor="performance", epp="performance",
            power_profile="performance", swappiness=10, thp="madvise",
            amd_x3d_mode="cache", tcp_cc="bbr",
        )
        data = prof.capture_from_status(st)
        self.assertEqual(data["governor"], "performance")
        self.assertEqual(data["swappiness"], 10)
        self.assertTrue(data["bbr"])
        p = prof.Profile(name="test", **data)
        cmds = p.commands()
        self.assertTrue(len(cmds) > 0)
        joined = " ".join(" ".join(c) for c in cmds)
        self.assertIn("frequency-set", joined)
        self.assertIn("tcp_congestion_control", joined)

    def test_save_load_roundtrip(self):
        import tempfile, pathlib
        from abrekoptimizer.core import profiles as prof
        tmp = pathlib.Path(tempfile.mkdtemp()) / "profiles.json"
        with unittest.mock.patch.object(prof, "PROFILES_FILE", tmp):
            p = prof.Profile(name="x", governor="performance", bbr=True)
            prof.save_all({"x": p})
            loaded = prof.load_all()
            self.assertIn("x", loaded)
            self.assertEqual(loaded["x"].governor, "performance")
            self.assertTrue(loaded["x"].bbr)

    def test_load_corrupt_file(self):
        import tempfile, pathlib
        from abrekoptimizer.core import profiles as prof
        tmp = pathlib.Path(tempfile.mkdtemp()) / "profiles.json"
        tmp.write_text("not json {{{")
        with unittest.mock.patch.object(prof, "PROFILES_FILE", tmp):
            result = prof.load_all()
            self.assertEqual(result, {})


class TestHistoryExtra(unittest.TestCase):
    def test_record_and_entries(self):
        import tempfile, pathlib
        from abrekoptimizer.core import history as h
        tmp = pathlib.Path(tempfile.mkdtemp()) / "history.jsonl"
        with unittest.mock.patch.object(h, "HISTORY_FILE", tmp):
            h.record("test_action", "detail1", ok=True)
            h.record("test_action2", "detail2", ok=False)
            ents = h.entries()
            self.assertEqual(len(ents), 2)
            self.assertEqual(ents[0]["action"], "test_action2")  # newest first
            self.assertFalse(ents[0]["ok"])
            self.assertTrue(ents[1]["ok"])

    def test_entries_limit(self):
        import tempfile, pathlib
        from abrekoptimizer.core import history as h
        tmp = pathlib.Path(tempfile.mkdtemp()) / "history.jsonl"
        with unittest.mock.patch.object(h, "HISTORY_FILE", tmp):
            for i in range(10):
                h.record(f"action_{i}")
            ents = h.entries(limit=3)
            self.assertEqual(len(ents), 3)

    def test_entries_empty_file(self):
        import tempfile, pathlib
        from abrekoptimizer.core import history as h
        tmp = pathlib.Path(tempfile.mkdtemp()) / "nonexistent.jsonl"
        with unittest.mock.patch.object(h, "HISTORY_FILE", tmp):
            self.assertEqual(h.entries(), [])


class TestSnapshot(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        self._tmp = tempfile.mkdtemp()
        self._old_dir = None
        import abrekoptimizer.core.snapshot as snap
        self._snap = snap
        self._old_snap_dir = snap.SNAPSHOT_DIR
        snap.SNAPSHOT_DIR = pathlib.Path(self._tmp) / "snapshots"

    def tearDown(self):
        self._snap.SNAPSHOT_DIR = self._old_snap_dir

    def test_capture_and_load(self):
        import unittest.mock as mock
        fake_status = self._snap.go.Status(
            cpu_governor="performance", epp="performance", power_profile="performance",
            swappiness=10, thp="madvise", vm_max_map_count=1048576,
            tcp_cc="bbr", tcp_qdisc="fq", scx_running="scx_bpfland",
            zram_active=True, kernel="6.12.0-cachyos",
        )
        with mock.patch.object(self._snap.go, "read_status", return_value=fake_status):
            s = self._snap.capture(name="test_snap", notes="unit test")
        self.assertEqual(s.name, "test_snap")
        self.assertEqual(s.cpu_governor, "performance")
        self.assertEqual(s.swappiness, 10)
        loaded = self._snap.load("test_snap")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.name, "test_snap")
        self.assertEqual(loaded.tcp_cc, "bbr")

    def test_list_and_delete(self):
        import unittest.mock as mock
        fake_status = self._snap.go.Status(cpu_governor="schedutil")
        with mock.patch.object(self._snap.go, "read_status", return_value=fake_status):
            self._snap.capture(name="snap_a")
            self._snap.capture(name="snap_b")
        snaps = self._snap.list_snapshots()
        names = [s.name for s in snaps]
        self.assertIn("snap_a", names)
        self.assertIn("snap_b", names)
        self.assertTrue(self._snap.delete("snap_a"))
        names2 = [s.name for s in self._snap.list_snapshots()]
        self.assertNotIn("snap_a", names2)
        self.assertIn("snap_b", names2)

    def test_restore_commands_nonempty(self):
        import unittest.mock as mock
        fake_status = self._snap.go.Status(
            cpu_governor="performance", swappiness=10, thp="madvise",
            vm_max_map_count=1048576, tcp_cc="bbr", tcp_qdisc="fq",
            scx_running="scx_bpfland",
        )
        with mock.patch.object(self._snap.go, "read_status", return_value=fake_status):
            s = self._snap.capture(name="restore_test")
        cmds = self._snap.restore_commands(s)
        self.assertIsInstance(cmds, list)
        self.assertTrue(len(cmds) > 0)
        # governor komutu üretilmeli
        joined = " ".join(" ".join(c) for c in cmds)
        self.assertIn("frequency-set", joined)

    def test_format_snapshot(self):
        import unittest.mock as mock
        fake_status = self._snap.go.Status(cpu_governor="performance", kernel="6.12")
        with mock.patch.object(self._snap.go, "read_status", return_value=fake_status):
            s = self._snap.capture(name="fmt_test")
        text = self._snap.format_snapshot(s)
        self.assertIn("fmt_test", text)
        self.assertIn("performance", text)


class TestPlanDialog(unittest.TestCase):
    def test_plan_dialog_import(self):
        from abrekoptimizer.ui.plan_dialog import PlanDialog
        self.assertTrue(PlanDialog is not None)

    def test_plan_dialog_creation(self):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        from abrekoptimizer.ui.plan_dialog import PlanDialog
        cmds = [["echo", "hello"], ["echo", "world"]]
        descs = ["Say hello", "Say world"]
        dlg = PlanDialog(None, "Test Plan", cmds, descs)
        self.assertEqual(dlg._commands, cmds)
        self.assertFalse(dlg.accepted_plan)


if __name__ == "__main__":
    unittest.main()

class TestTrend(unittest.TestCase):
    def test_rate_limit(self):
        import tempfile, pathlib
        import abrekoptimizer.core.trend as tr
        old = tr.TREND_FILE
        try:
            tr.TREND_FILE = pathlib.Path(tempfile.mkdtemp()) / "trend.jsonl"
            self.assertTrue(tr.record_sample(80, 1000, 2000))   # ilk kayıt
            self.assertFalse(tr.record_sample(85, 1100, 2100))  # 1 saatten erken
            self.assertEqual(len(tr.samples()), 1)
            self.assertEqual(tr.samples()[0]["score"], 80)
        finally:
            tr.TREND_FILE = old


class TestGameOptExtras(unittest.TestCase):
    def test_ppd_profiles_parse(self):
        import unittest.mock as mock
        fake = "* balanced:\n    PlatformDriver:\tplaceholder\n\n  power-saver:\n    PlatformDriver:\tplaceholder\n"
        with mock.patch.object(gameopt, "_run", return_value=fake):
            self.assertEqual(gameopt.ppd_available_profiles(), {"balanced", "power-saver"})

    def test_setup_zram_command_shape(self):
        cmd = gameopt.cmd_setup_zram()
        self.assertEqual(cmd[0], "bash")
        self.assertIn("zram-generator", cmd[-1])
        self.assertIn("systemd-zram-setup@zram0.service", cmd[-1])

    def test_profile_commands_full(self):
        import abrekoptimizer.core.profiles as prof
        p = prof.Profile(name="x", governor="performance", epp="performance",
                         power_profile="balanced", swappiness=10, thp="madvise",
                         amd_gpu_level="high", x3d_mode="cache", bbr=True)
        self.assertEqual(len(p.commands()), 8)

    def test_history_roundtrip(self):
        import tempfile, pathlib
        import abrekoptimizer.core.history as h
        old = h.HISTORY_FILE
        try:
            h.HISTORY_FILE = pathlib.Path(tempfile.mkdtemp()) / "h.jsonl"
            h.record("a", "1")
            h.record("b", "2", ok=False)
            ents = h.entries()
            self.assertEqual([e["action"] for e in ents], ["b", "a"])
            self.assertIs(ents[0]["ok"], False)
        finally:
            h.HISTORY_FILE = old
