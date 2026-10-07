"""Çapraz dağıtım paket yöneticisi soyutlaması (apt/dnf/pacman/zypper)."""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Iterable


@dataclass
class Package:
    name: str
    version: str = ""
    description: str = ""
    size: str = ""


_PKG_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9@+._:-]*$")


def validate_pkg_names(names: Iterable[str]) -> list[str]:
    """Paket adlarını whitelist ile doğrular; shell metakarakterlerini reddeder."""
    out = []
    for n in names:
        n = str(n).strip()
        if not _PKG_NAME_RE.fullmatch(n):
            raise ValueError(f"geçersiz paket adı: {n!r}")
        out.append(n)
    return out


class PackageManager:
    """Tespit edilen paket yöneticisi için ortak arayüz."""

    name: str = "unknown"
    needs_sudo: bool = True

    @classmethod
    def detect(cls) -> "PackageManager":
        for klass in (Pacman, Apt, Dnf, Zypper):
            if shutil.which(klass.bin):
                return klass()
        raise RuntimeError("Desteklenen bir paket yöneticisi bulunamadı.")

    # alt sınıflarca uygulanır
    bin: str = ""

    def list_installed(self) -> list[Package]:  # pragma: no cover
        raise NotImplementedError

    def remove_command(self, names: Iterable[str], purge: bool = True, cascade: bool = False) -> list[str]:
        raise NotImplementedError

    def why_depends_command(self, name: str) -> list[str]:
        """Bir paketin neden gerekli olduğunu gösteren komut."""
        raise NotImplementedError

    def autoremove_command(self) -> list[str]:
        raise NotImplementedError

    def clean_cache_command(self) -> list[str]:
        raise NotImplementedError


class Pacman(PackageManager):
    name = "pacman"
    bin = "pacman"

    def list_installed(self) -> list[Package]:
        import os
        env = {**os.environ, "LC_ALL": "C", "LANG": "C", "LANGUAGE": "C"}
        out = subprocess.run(
            ["pacman", "-Qi"], capture_output=True, text=True, check=False, env=env
        ).stdout
        pkgs: list[Package] = []
        cur: dict[str, str] = {}
        for line in out.splitlines():
            if not line.strip():
                if cur:
                    pkgs.append(
                        Package(
                            name=cur.get("Name", ""),
                            version=cur.get("Version", ""),
                            description=cur.get("Description", ""),
                            size=cur.get("Installed Size", ""),
                        )
                    )
                    cur = {}
                continue
            if ":" in line:
                k, _, v = line.partition(":")
                cur[k.strip()] = v.strip()
        if cur:
            pkgs.append(
                Package(
                    name=cur.get("Name", ""),
                    version=cur.get("Version", ""),
                    description=cur.get("Description", ""),
                    size=cur.get("Installed Size", ""),
                )
            )
        return pkgs

    def remove_command(self, names, purge=True, cascade=False):
        # -R kald\u0131r, -n config sakla, -s ba\u011f\u0131ml\u0131l\u0131klar\u0131, -c cascade (ba\u011f\u0131ml\u0131lar\u0131 da)
        flags = "R"
        if purge:
            flags += "ns"
        if cascade:
            flags += "c"
        return ["sudo", "pacman", "-" + flags, "--noconfirm", *validate_pkg_names(names)]

    def why_depends_command(self, name):
        return ["pactree", "-r", validate_pkg_names([name])[0]]

    def preview_remove(self, names, cascade=False):
        """pacman -Rs[c]p --print ile dry-run: ger\u00e7ekten kald\u0131r\u0131lacak paketlerin listesini d\u00f6ner."""
        flags = "Rsp"
        if cascade:
            flags = "Rscp"
        res = subprocess.run(
            ["pacman", "-" + flags, "--print", "--print-format", "%n", *names],
            capture_output=True, text=True, check=False,
        )
        ok = res.returncode == 0
        out = res.stdout.strip().splitlines() if ok else []
        return ok, out, (res.stderr or res.stdout)

    def autoremove_command(self):
        # $(...) shell alt komutu yerine: yetim paketleri kullanıcı yetkisiyle listeleyip argv ver.
        res = subprocess.run(
            ["pacman", "-Qdtq"], capture_output=True, text=True, check=False
        )
        names = [n for n in res.stdout.split() if n]
        if not names:
            return ["true"]
        return ["sudo", "pacman", "-Rns", "--noconfirm", *names]

    def clean_cache_command(self):
        return ["sudo", "pacman", "-Sc", "--noconfirm"]


class Apt(PackageManager):
    name = "apt"
    bin = "apt"

    def list_installed(self):
        out = subprocess.run(
            ["dpkg-query", "-W", "-f=${Package}\t${Version}\t${Installed-Size}\t${binary:Summary}\n"],
            capture_output=True, text=True, check=False,
        ).stdout
        pkgs = []
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) >= 4:
                pkgs.append(Package(parts[0], parts[1], parts[3], f"{parts[2]} KB"))
        return pkgs

    def remove_command(self, names, purge=True, cascade=False):
        action = "purge" if purge else "remove"
        names = validate_pkg_names(names)
        cmd = ["sudo", "apt-get", action, "-y", *names]
        if cascade:
            # sh -c yerine: paket adları argv olarak kalır, zincir shell'e verilmez.
            return ["sudo", "sh", "-c",
                    'exec "$0" "$@" && sudo apt-get autoremove --purge -y',
                    "apt-get", action, "-y", *names]
        return cmd

    def why_depends_command(self, name):
        return ["apt-cache", "rdepends", "--installed", validate_pkg_names([name])[0]]

    def autoremove_command(self):
        return ["sudo", "apt-get", "autoremove", "--purge", "-y"]

    def clean_cache_command(self):
        return ["sudo", "apt-get", "clean"]


class Dnf(PackageManager):
    name = "dnf"
    bin = "dnf"

    def list_installed(self):
        out = subprocess.run(
            ["rpm", "-qa", "--qf", "%{NAME}\t%{VERSION}-%{RELEASE}\t%{SIZE}\t%{SUMMARY}\n"],
            capture_output=True, text=True, check=False,
        ).stdout
        pkgs = []
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) >= 4:
                pkgs.append(Package(parts[0], parts[1], parts[3], f"{int(parts[2]) // 1024} KB"))
        return pkgs

    def remove_command(self, names, purge=True, cascade=False):
        # dnf zaten cascade yapar; cascade=False istense bile teknik olarak engellenir,
        # bu y\u00fczden sadece autoremove ekleyip kald\u0131rm\u0131yoruz.
        return ["sudo", "dnf", "remove", "-y", *validate_pkg_names(names)]

    def why_depends_command(self, name):
        return ["dnf", "repoquery", "--installed", "--whatrequires", name]

    def autoremove_command(self):
        return ["sudo", "dnf", "autoremove", "-y"]

    def clean_cache_command(self):
        return ["sudo", "dnf", "clean", "all"]


class Zypper(PackageManager):
    name = "zypper"
    bin = "zypper"

    def list_installed(self):
        out = subprocess.run(
            ["rpm", "-qa", "--qf", "%{NAME}\t%{VERSION}-%{RELEASE}\t%{SIZE}\t%{SUMMARY}\n"],
            capture_output=True, text=True, check=False,
        ).stdout
        pkgs = []
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) >= 4:
                pkgs.append(Package(parts[0], parts[1], parts[3], f"{int(parts[2]) // 1024} KB"))
        return pkgs

    def remove_command(self, names, purge=True, cascade=False):
        # zypper'da cascade ayr\u0131 bir seyrek senaryo; --clean-deps zaten yetimleri al\u0131r.
        return ["sudo", "zypper", "--non-interactive", "remove", "--clean-deps", *validate_pkg_names(names)]

    def why_depends_command(self, name):
        return ["zypper", "search", "--requires-pkg", name]

    def autoremove_command(self):
        # awk/xargs pipe yerine zypper'ın kendi zarfı; kullanıcı onayı UI'da.
        return ["sudo", "zypper", "--non-interactive", "remove", "--clean-deps", "--auto-orphans"]

    def clean_cache_command(self):
        return ["sudo", "zypper", "clean", "-a"]
