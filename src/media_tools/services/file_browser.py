import logging
import subprocess
import platform
from pathlib import Path
from fastapi import HTTPException
from media_tools.transcribe.media_extensions import MEDIA_EXTENSIONS
from media_tools.common.paths import get_download_path

logger = logging.getLogger(__name__)


def _is_allowed_scan_path(dir_path: Path) -> bool:
    """Restrict directory scanning to safe roots."""
    import sys
    import os
    resolved = dir_path.resolve()
    dir_str = str(resolved)

    if any(part == ".." for part in dir_path.parts):
        return False

    home = Path.home().resolve()
    downloads = get_download_path().resolve()
    allowed_roots = [home, downloads, Path("/tmp").resolve()]
    if sys.platform == "darwin":
        allowed_roots.append(Path("/Volumes").resolve())

    for root in allowed_roots:
        root_str = str(root)
        if dir_str.startswith(root_str + os.sep) or dir_str == root_str:
            return True
    return False


def select_folder():
    """调用系统原生文件选择器弹出文件夹选择对话框，返回选中的绝对路径。"""
    system = platform.system()
    selected = ""

    try:
        if system == "Darwin":
            result = subprocess.run(
                ["osascript", "-e", 'POSIX path of (choose folder with prompt "选择要扫描的文件夹")'],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                selected = result.stdout.strip()
            else:
                logger.info(f"用户取消选择文件夹: {result.stderr.strip()}")
        elif system == "Linux":
            result = subprocess.run(
                ["zenity", "--file-selection", "--directory", "--title=选择要扫描的文件夹"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                selected = result.stdout.strip()
            else:
                logger.info("用户取消选择文件夹")
        elif system == "Windows":
            ps_cmd = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
                "$f.Description = '选择要扫描的文件夹'; "
                "[void]$f.ShowDialog(); "
                "$f.SelectedPath"
            )
            result = subprocess.run(
                ["powershell", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                selected = result.stdout.strip()
            else:
                logger.info("用户取消选择文件夹")
    except subprocess.TimeoutExpired:
        logger.warning("文件夹选择器超时")
    except FileNotFoundError as e:
        logger.warning(f"系统文件选择器不可用: {e}")

    if not selected:
        raise HTTPException(status_code=400, detail="未选择文件夹或选择器不可用")

    return {"directory": selected}


def scan_directory(directory: str):
    dir_path = Path(directory)
    if not _is_allowed_scan_path(dir_path):
        raise HTTPException(status_code=400, detail="Invalid directory path")
    if not dir_path.is_dir():
        raise HTTPException(status_code=400, detail="目录不存在")
    extensions = MEDIA_EXTENSIONS
    files = []
    for f in sorted(dir_path.iterdir()):
        if f.is_file() and f.suffix.lower() in extensions:
            try:
                files.append({"path": str(f), "name": f.name, "size_mb": round(f.stat().st_size / 1024 / 1024, 1)})
            except OSError:
                continue
    return {"directory": str(dir_path), "files": files}
