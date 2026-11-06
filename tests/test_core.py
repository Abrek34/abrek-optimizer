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
