"""Oyun modu profilleri: mevcut ayarları kaydet, sonra tek tıkla uygula."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from abrekoptimizer.core import gameopt as go

_CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "abrek"
PROFILES_FILE = _CONFIG_DIR / "profiles.json"


@dataclass
class Profile:
    name: str
    governor: str = ""
    epp: str = ""
    power_profile: str = ""
    swappiness: int | None = None
    thp: str = ""
    amd_gpu_level: str = ""     # "high" | "auto" | "" (boş = dokunma)
    x3d_mode: str = ""
    bbr: bool = False

    def commands(self) -> list[list[str]]:
        cmds: list[list[str]] = []
        if self.governor:
            cmds.append(go.cmd_set_governor(self.governor))
        if self.epp:
            cmds.append(go.cmd_set_epp(self.epp))
        if self.power_profile:
            cmds.append(go.cmd_power_profile(self.power_profile))
        if self.swappiness is not None:
            cmds.append(go.cmd_set_swappiness(self.swappiness, persist=True))
        if self.thp:
            cmds.append(go.cmd_set_thp(self.thp))
        if self.amd_gpu_level:
            cmds.append(go.cmd_amd_gpu_perf_level(self.amd_gpu_level))
        if self.x3d_mode:
            cmds.append(go.cmd_amd_x3d_mode(self.x3d_mode))
        if self.bbr:
            cmds.append(go.cmd_enable_bbr(persist=True))
        return cmds


def capture_from_status(st: go.Status) -> dict:
    return {
        "governor": st.cpu_governor,
        "epp": st.epp,
        "power_profile": st.power_profile,
        "swappiness": st.swappiness,
        "thp": st.thp,
        "amd_gpu_level": "",       # mevcut GPU seviyesi okunmadığı için atlanır
        "x3d_mode": st.amd_x3d_mode,
        "bbr": st.tcp_cc in ("bbr", "bbr3"),
    }


def load_all() -> dict[str, Profile]:
    try:
        data = json.loads(PROFILES_FILE.read_text())
    except (OSError, ValueError):
        return {}
    out: dict[str, Profile] = {}
    if not isinstance(data, dict):
        return out
    fields = set(Profile.__dataclass_fields__) - {"name"}
    for name, d in data.items():
        if isinstance(d, dict):
            try:
                out[name] = Profile(name=name, **{k: v for k, v in d.items() if k in fields})
            except TypeError:
                continue
    return out


def save_all(profiles: dict[str, Profile]) -> None:
    PROFILES_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {n: {k: v for k, v in asdict(p).items() if k != "name"} for n, p in profiles.items()}
    PROFILES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
