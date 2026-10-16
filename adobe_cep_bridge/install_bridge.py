"""Installer and registrar for Argon Adobe CEP Bridge Extension.

Configures Adobe PlayerDebugMode in Windows Registry or macOS Plist,
and installs/symlinks the com.argon.bridge extension into the Adobe CEP extensions directory.
"""

from __future__ import annotations
import sys
import os
import shutil
import platform
import subprocess
import argparse
from pathlib import Path

# Supported CSXS versions across Adobe Creative Cloud (2019-2026)
CSXS_VERSIONS = [
    "CSXS.9",
    "CSXS.10",
    "CSXS.11",
    "CSXS.12",
    "CSXS.13",
    "CSXS.14",
    "CSXS.15",
    "CSXS.16",
    "CSXS.17",
]

EXTENSION_BUNDLE_ID = "com.argon.bridge"


def get_cep_target_dir() -> Path:
    """Return the platform-specific standard user CEP extensions directory."""
    system = platform.system()
    if system == "Windows":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            appdata = str(Path.home() / "AppData" / "Roaming")
        return Path(appdata) / "Adobe" / "CEP" / "extensions" / EXTENSION_BUNDLE_ID
    elif system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Adobe" / "CEP" / "extensions" / EXTENSION_BUNDLE_ID
    else:
        # Fallback for Linux or container environments
        return Path.home() / ".adobe" / "CEP" / "extensions" / EXTENSION_BUNDLE_ID


def enable_player_debug_mode_windows() -> list[str]:
    """Enable PlayerDebugMode=1 in Windows Registry for all CSXS versions."""
    import winreg

    modified_keys = []
    base_path = r"Software\Adobe"

    for csxs in CSXS_VERSIONS:
        key_path = f"{base_path}\\{csxs}"
        try:
            key = winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER,
                key_path,
                0,
                winreg.KEY_SET_VALUE | winreg.KEY_WRITE
            )
            winreg.SetValueEx(key, "PlayerDebugMode", 0, winreg.REG_SZ, "1")
            winreg.CloseKey(key)
            modified_keys.append(f"HKCU\\{key_path}\\PlayerDebugMode = 1")
        except Exception as e:
            print(f"[!] Warning: Could not set registry key for {csxs}: {e}", file=sys.stderr)

    return modified_keys


def enable_player_debug_mode_macos() -> list[str]:
    """Enable PlayerDebugMode=1 via defaults write on macOS."""
    modified = []
    for csxs in CSXS_VERSIONS:
        domain = f"com.adobe.{csxs}"
        try:
            subprocess.run(
                ["defaults", "write", domain, "PlayerDebugMode", "1"],
                check=True,
                capture_output=True,
                text=True
            )
            modified.append(f"defaults write {domain} PlayerDebugMode 1")
        except Exception as e:
            print(f"[!] Warning: defaults write failed for {domain}: {e}", file=sys.stderr)
    return modified


def install_extension(source_dir: Path, target_dir: Path, force_copy: bool = False) -> bool:
    """Install or symlink extension source directory to Adobe CEP target."""
    target_dir.parent.mkdir(parents=True, exist_ok=True)

    if target_dir.exists() or target_dir.is_symlink():
        print(f"[*] Removing existing installation at {target_dir}")
        if target_dir.is_symlink() or target_dir.is_file():
            target_dir.unlink()
        else:
            shutil.rmtree(target_dir)

    # Attempt symlink first for live development
    if not force_copy:
        try:
            target_dir.symlink_to(source_dir, target_is_directory=True)
            print(f"[+] Symlinked {source_dir} -> {target_dir}")
            return True
        except (OSError, PermissionError) as e:
            print(f"[*] Symlink creation failed ({e}), falling back to direct copy...")

    # Fallback to copy
    shutil.copytree(source_dir, target_dir)
    print(f"[+] Copied extension files to {target_dir}")
    return True


def check_status(target_dir: Path) -> dict:
    """Check whether extension is installed and PlayerDebugMode is enabled."""
    is_installed = target_dir.exists()
    system = platform.system()
    debug_modes = {}

    if system == "Windows":
        import winreg
        for csxs in CSXS_VERSIONS:
            key_path = f"Software\\Adobe\\{csxs}"
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
                val, _ = winreg.QueryValueEx(key, "PlayerDebugMode")
                winreg.CloseKey(key)
                debug_modes[csxs] = str(val)
            except Exception:
                debug_modes[csxs] = "0 (Not Set)"
    elif system == "Darwin":
        for csxs in CSXS_VERSIONS:
            domain = f"com.adobe.{csxs}"
            try:
                res = subprocess.run(
                    ["defaults", "read", domain, "PlayerDebugMode"],
                    capture_output=True,
                    text=True
                )
                debug_modes[csxs] = res.stdout.strip() if res.returncode == 0 else "0 (Not Set)"
            except Exception:
                debug_modes[csxs] = "Error"

    return {
        "installed": is_installed,
        "is_symlink": target_dir.is_symlink() if is_installed else False,
        "target_path": str(target_dir),
        "debug_modes": debug_modes,
    }


def main():
    parser = argparse.ArgumentParser(description="Install and configure Argon Adobe CEP Bridge.")
    parser.add_argument("--check", action="store_true", help="Check current installation status")
    parser.add_argument("--copy", action="store_true", help="Force copy instead of symlink")
    parser.add_argument("--uninstall", action="store_true", help="Remove extension from CEP directory")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    target_dir = get_cep_target_dir()

    if args.check:
        status = check_status(target_dir)
        print("=== Argon Adobe CEP Bridge Status ===")
        print(f"Installed: {status['installed']} (Symlink: {status['is_symlink']})")
        print(f"Path: {status['target_path']}")
        print("PlayerDebugMode Settings:")
        for k, v in status["debug_modes"].items():
            print(f"  {k}: {v}")
        return

    if args.uninstall:
        if target_dir.exists() or target_dir.is_symlink():
            if target_dir.is_symlink() or target_dir.is_file():
                target_dir.unlink()
            else:
                shutil.rmtree(target_dir)
            print(f"[+] Successfully uninstalled extension from {target_dir}")
        else:
            print(f"[*] Extension not found at {target_dir}")
        return

    print("=== Installing Argon Adobe CEP Bridge ===")
    system = platform.system()
    if system == "Windows":
        regs = enable_player_debug_mode_windows()
        print(f"[+] Enabled PlayerDebugMode on {len(regs)} Windows Registry keys.")
    elif system == "Darwin":
        plists = enable_player_debug_mode_macos()
        print(f"[+] Enabled PlayerDebugMode on {len(plists)} macOS defaults domains.")

    install_extension(script_dir, target_dir, force_copy=args.copy)
    print("\n[SUCCESS] Argon Adobe Bridge installed successfully!")
    print(f"Target: {target_dir}")
    print("Now, when Premiere Pro, After Effects, or Photoshop are launched,")
    print("the Argon bridge panel can be loaded under Window -> Extensions -> Argon Video Engine Bridge.")


if __name__ == "__main__":
    main()
