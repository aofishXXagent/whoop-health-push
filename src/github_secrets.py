"""更新 GitHub Secrets（用于 WHOOP token 轮换）。"""

import os
import subprocess
from src import config


def rotate_secrets(secrets: dict):
    """用 gh CLI 更新 GitHub Secrets。需要 GH_PAT 和 GITHUB_REPOSITORY。"""
    if not config.GH_PAT or not config.GH_REPO:
        print("[Secrets] GH_PAT or GITHUB_REPOSITORY not set, skipping rotation")
        return

    env = {**os.environ, "GH_TOKEN": config.GH_PAT}
    for name, value in secrets.items():
        result = subprocess.run(
            ["gh", "secret", "set", name, "--body", value, "--repo", config.GH_REPO],
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"[Secrets] Failed to rotate {name}: {result.stderr}")
        else:
            print(f"[Secrets] Rotated {name}")
