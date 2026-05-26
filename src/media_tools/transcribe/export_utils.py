from __future__ import annotations
"""转写导出工具函数"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Union

from media_tools.common.runtime import ExportConfig, ensure_dir, now_stamp


@dataclass(frozen=True)
class FlowDebugArtifacts:
    transcript_path: Path
    doc_edit_path: Path


def _get_video_title_from_db(video_path: Path) -> Optional[str]:
    """从文件名提取标题（下载时已清洗）"""
    stem = Path(video_path).stem
    if re.search(r'\d{15,}', stem):
        pass
    else:
        clean = stem.strip()
        if len(clean) > 5 and len(clean) < 65:
            return clean
    return None


def build_export_output_path(
    *,
    input_path: Union[str, Path],
    output_dir: Union[str, Path],
    export_config: ExportConfig,
    run_stamp: Optional[str] = None,
    title: Optional[str] = None,
) -> Path:
    """构建导出文件路径"""
    stamp = run_stamp or now_stamp()
    if title:
        clean_title = re.sub(r'[<>"/\\|?*]', '', title).strip()
        if len(clean_title) > 50:
            clean_title = clean_title[:50] + "..."
        filename = f"{clean_title}{export_config.extension}"
    else:
        source_path = Path(input_path)
        filename = f"{source_path.stem}-{stamp}{export_config.extension}"
    return Path(output_dir).resolve() / filename


def save_debug_artifacts(
    *,
    output_dir: Union[str, Path],
    output_base: str,
    run_stamp: str,
    transcript_json: Any,
    doc_edit_json: Any,
) -> FlowDebugArtifacts:
    """保存调试产物到文件"""
    root = Path(output_dir).resolve()
    ensure_dir(root)
    transcript_path = root / f"{output_base}-{run_stamp}-transcript.json"
    doc_edit_path = root / f"{output_base}-{run_stamp}-doc-edit.json"
    transcript_path.write_text(json.dumps(transcript_json, indent=2), encoding="utf-8")
    doc_edit_path.write_text(json.dumps(doc_edit_json, indent=2), encoding="utf-8")
    return FlowDebugArtifacts(transcript_path=transcript_path, doc_edit_path=doc_edit_path)
