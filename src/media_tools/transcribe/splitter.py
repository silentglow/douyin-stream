from __future__ import annotations

"""大文件预切分：千问平台限制单文件 > 6 GB，超出时用 ffmpeg `-c copy`
按时长均分成多个 part，每个 part 作为独立转写任务（不合并结果）。"""

import logging
import math
import shutil
import subprocess
from pathlib import Path

from media_tools.common.paths import get_download_path
from media_tools.store.db import local_asset_id

logger = logging.getLogger(__name__)

SPLIT_THRESHOLD_BYTES = 6 * 1024 * 1024 * 1024
SPLIT_TARGET_BYTES = 5_500_000_000

_FFPROBE_TIMEOUT = 60
_FFMPEG_TIMEOUT_PER_PART = 1800


class SplitError(RuntimeError):
    """ffmpeg / ffprobe 失败、磁盘空间不足等切分阶段的错误。"""


def _split_cache_root() -> Path:
    return get_download_path() / ".split_cache"


def _cache_dir_for(source: Path) -> Path:
    asset_id = local_asset_id(source)
    hex_part = asset_id.split(":", 1)[-1]
    return _split_cache_root() / hex_part


def needs_split(path: Path) -> bool:
    try:
        return path.stat().st_size > SPLIT_THRESHOLD_BYTES
    except OSError:
        return False


def is_split_part(path: Path) -> bool:
    try:
        root = _split_cache_root().resolve()
        return root in path.resolve().parents
    except OSError:
        return False


def _probe_duration(path: Path) -> float:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=_FFPROBE_TIMEOUT,
            check=True,
        )
    except FileNotFoundError as e:
        raise SplitError("ffprobe 未安装") from e
    except subprocess.TimeoutExpired as e:
        raise SplitError(f"ffprobe 超时 ({_FFPROBE_TIMEOUT}s)") from e
    except subprocess.CalledProcessError as e:
        raise SplitError(f"ffprobe 失败: {e.stderr.strip()}") from e
    value = result.stdout.strip()
    try:
        duration = float(value)
    except ValueError as e:
        raise SplitError(f"ffprobe 返回非法时长: {value!r}") from e
    if duration <= 0:
        raise SplitError(f"ffprobe 返回非正时长: {duration}")
    return duration


def _run_ffmpeg_segment(source: Path, start: float, duration: float, output: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(source),
        "-t",
        f"{duration:.3f}",
        "-c",
        "copy",
        "-avoid_negative_ts",
        "make_zero",
        "-movflags",
        "+faststart",
        str(output),
    ]
    try:
        subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_FFMPEG_TIMEOUT_PER_PART,
            check=True,
        )
    except FileNotFoundError as e:
        raise SplitError("ffmpeg 未安装") from e
    except subprocess.TimeoutExpired as e:
        raise SplitError(f"ffmpeg 切分超时 ({_FFMPEG_TIMEOUT_PER_PART}s): {output.name}") from e
    except subprocess.CalledProcessError as e:
        tail = (e.stderr or "").strip().splitlines()[-5:]
        raise SplitError(f"ffmpeg 切分失败 {output.name}: {' | '.join(tail)}") from e


def split_video(source: Path) -> list[Path]:
    """将 source 按时长均分成 N 段（N = ceil(size / SPLIT_TARGET_BYTES)），
    返回所有 part 的路径列表。已存在且大小合理的 part 会被复用。
    """
    try:
        size = source.stat().st_size
    except OSError as e:
        raise SplitError(f"无法读取源文件: {source}") from e

    n = max(2, math.ceil(size / SPLIT_TARGET_BYTES))
    duration = _probe_duration(source)
    seg_duration = duration / n

    cache_dir = _cache_dir_for(source)
    cache_dir.mkdir(parents=True, exist_ok=True)

    parts: list[Path] = []
    stem = source.stem
    suffix = source.suffix or ".mp4"

    for idx in range(n):
        part_name = f"{stem}__part{idx + 1}of{n}{suffix}"
        part_path = cache_dir / part_name

        if part_path.exists() and part_path.stat().st_size > 1024 * 1024:
            logger.info(f"切分缓存命中，复用: {part_path.name}")
            parts.append(part_path)
            continue

        start = idx * seg_duration
        logger.info(f"切分中 ({idx + 1}/{n}): start={start:.1f}s dur={seg_duration:.1f}s -> {part_path.name}")
        _run_ffmpeg_segment(source, start, seg_duration, part_path)

        try:
            part_size = part_path.stat().st_size
        except OSError as e:
            raise SplitError(f"切分后无法读取 part: {part_path}") from e
        if part_size > SPLIT_THRESHOLD_BYTES:
            raise SplitError(
                f"切分后 part 仍 > 6GB ({part_size} bytes): {part_path.name}，"
                "可能源文件码率过高，需减小 SPLIT_TARGET_BYTES"
            )
        logger.info(f"切分完成 ({idx + 1}/{n}): {part_path.name} -> {part_size / 1e9:.2f} GB")
        parts.append(part_path)

    return parts


def cleanup_part(part_path: Path) -> None:
    if not is_split_part(part_path):
        return
    try:
        part_path.unlink()
        logger.info(f"已清理切分 part: {part_path.name}")
    except FileNotFoundError:
        pass
    except OSError as e:
        logger.warning(f"清理切分 part 失败: {part_path} - {e}")
        return

    parent = part_path.parent
    try:
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
            logger.info(f"已清理空的切分目录: {parent}")
    except OSError as e:
        logger.warning(f"清理切分目录失败: {parent} - {e}")


def cleanup_cache_dir_if_empty(source: Path) -> None:
    """全部 part 都被 cleanup_part 删完后，兜底删空目录。"""
    cache_dir = _cache_dir_for(source)
    try:
        if cache_dir.exists() and not any(cache_dir.iterdir()):
            cache_dir.rmdir()
    except OSError:
        pass


def ensure_tools_available() -> None:
    """启动期可选检查；缺工具时抛 SplitError，便于调用方提前 fail-fast。"""
    if shutil.which("ffmpeg") is None:
        raise SplitError("ffmpeg 未安装（请通过 brew install ffmpeg 或类似方式安装）")
    if shutil.which("ffprobe") is None:
        raise SplitError("ffprobe 未安装（通常随 ffmpeg 一起安装）")
