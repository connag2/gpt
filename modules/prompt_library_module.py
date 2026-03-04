from __future__ import annotations

"""
NAIA Prompt Library Module

- prompt_library/*.txt 목록/검색/편집
- 단일 적용/생성/대기열 publish
- prompt.txt 분할(1.txt,2.txt...)
- 자연 정렬
- Auto Refine 요청 payload 발행(랜덤 재시도 모드)
- API 설정 저장/불러오기 + API 인증 테스트
- 실행/오류 로그를 fix_logs/*.txt로 저장 + UI 조회
"""

import json
import random
import re
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QDoubleSpinBox,
    QSpinBox,
)

try:
    from interfaces.base_module import BaseMiddleModule
except ImportError:
    from ..interfaces.base_module import BaseMiddleModule

EVENT_NAME = "prompt_library_event_requested"

OPENAI_MODELS = [
    "gpt-image-1",
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-nano",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "gpt-4o",
    "gpt-4o-mini",
    "o3",
    "o4-mini",
]

GEMINI_MODELS = [
    "gemini-2.5-flash-image-preview",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-exp",
    "gemini-2.0-flash-lite",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
]

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def _find_naia_root(app_context=None) -> Tuple[Path, str]:
    for attr in ("project_root", "root", "project_path", "project_dir"):
        try:
            value = getattr(app_context, attr, None)
            if value:
                p = Path(value).resolve()
                if (p / "modules").exists():
                    return p, f"app_context.{attr}"
        except Exception:
            pass

    here = Path(__file__).resolve()
    for parent in [here.parent] + list(here.parents):
        try:
            if (parent / "modules").exists():
                return parent, "parents(modules)"
        except Exception:
            pass

    return here.parents[1], "fallback(parents[1])"


def _normalize_prompt_text(s: str) -> str:
    return (s or "").replace("\r\n", "\n").replace("\r", "\n").strip("\n")


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return path.read_text(encoding="cp949", errors="replace")


def _natural_key(path_or_name: Any):
    value = str(path_or_name)
    if isinstance(path_or_name, Path):
        value = path_or_name.stem
    parts = re.split(r"(\d+)", value.lower())
    return [int(part) if part.isdigit() else part for part in parts]


def _next_numbered_txt(dir_path: Path) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    max_num = 0
    for p in dir_path.glob("*.txt"):
        if p.stem.isdigit():
            max_num = max(max_num, int(p.stem))
    return dir_path / f"{max_num + 1}.txt"


class PromptLibraryModule(BaseMiddleModule):
    NAI_compatibility = True
    WEBUI_compatibility = True
    COMFYUI_compatibility = True

    def __init__(self):
        super().__init__()
        self.NAI_compatibility = True
        self.WEBUI_compatibility = True
        self.ignore_save_load = True

        self.app_context = None
        self.naia_root: Optional[Path] = None
        self.root_source = ""
        self.library_dir: Optional[Path] = None
        self.log_dir: Optional[Path] = None
        self.api_settings_path: Optional[Path] = None

        self.widget: Optional[QWidget] = None
        self.info_label: Optional[QLabel] = None
        self.search_edit: Optional[QLineEdit] = None
        self.table: Optional[QTableWidget] = None

        self.fold_btn: Optional[QToolButton] = None
        self.editor_container: Optional[QWidget] = None
        self.name_edit: Optional[QLineEdit] = None
        self.text_edit: Optional[QTextEdit] = None

        self.judge_mode_combo: Optional[QComboBox] = None
        self.provider_combo: Optional[QComboBox] = None
        self.model_combo: Optional[QComboBox] = None
        self.api_key_edit: Optional[QLineEdit] = None
        self.base_url_edit: Optional[QLineEdit] = None
        self.aesthetic_threshold_spin: Optional[QDoubleSpinBox] = None
        self.anatomy_error_limit_spin: Optional[QSpinBox] = None

        self.latest_image_label: Optional[QLabel] = None
        self.issue_status_label: Optional[QLabel] = None
        self.fix_log_edit: Optional[QTextEdit] = None

        self.log_list: Optional[QListWidget] = None
        self.log_preview: Optional[QTextEdit] = None
        self.queue_list: Optional[QListWidget] = None

        self._files: List[Path] = []
        self._bridge_listener_count: Optional[int] = None

    def get_title(self) -> str:
        return "📚 프롬프트 라이브러리"

    def get_order(self) -> int:
        return 115

    def initialize_with_context(self, context):
        self.context = context
        self.app_context = context
        self.naia_root, self.root_source = _find_naia_root(context)
        self.library_dir = (self.naia_root / "save" / "prompt_library").resolve()
        self.log_dir = (self.library_dir / "fix_logs").resolve()
        self.api_settings_path = (self.library_dir / "api_settings.json").resolve()

    def on_initialize(self):
        if self.library_dir:
            self.library_dir.mkdir(parents=True, exist_ok=True)
        if self.log_dir:
            self.log_dir.mkdir(parents=True, exist_ok=True)

    def create_widget(self, parent=None) -> QWidget:
        self.widget = QWidget(parent)
        self.widget.setMinimumHeight(980)
        root = QVBoxLayout(self.widget)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        self.info_label = QLabel("")
        self.info_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.info_label)

        top = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setMinimumHeight(34)
        self.search_edit.setPlaceholderText("검색(파일명) — 비우면 전체 표시")
        self.search_edit.textChanged.connect(self.apply_filter)
        top.addWidget(self.search_edit, 1)

        for text, cb in [
            ("지우기", lambda: self.search_edit.setText("")),
            ("새로고침", self.reload),
            ("폴더 열기", self.open_folder),
            ("prompt.txt 분할", self.split_prompt_txt),
        ]:
            btn = QPushButton(text)
            btn.setMinimumHeight(34)
            btn.clicked.connect(cb)
            top.addWidget(btn)
        root.addLayout(top)

        self.table = QTableWidget()
        self.table.setMinimumHeight(260)
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["이름", "경로"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        font = QFont()
        font.setPointSize(11)
        self.table.setFont(font)
        self.table.setStyleSheet(
            """
QTableWidget { border: 1px solid rgba(255,255,255,0.12); background: rgba(0,0,0,0.15); color: #EDEDED; }
QHeaderView::section { background: rgba(255,255,255,0.06); color: #EDEDED; padding: 8px; }
QTableWidget::item:selected { background: rgba(120,160,255,0.35); color: #FFFFFF; }
"""
        )
        self.table.itemSelectionChanged.connect(self.on_table_select)
        root.addWidget(self.table)

        actions = QHBoxLayout()
        for text, cb in [
            ("메인에 넣기(교체)", self.request_apply_replace),
            ("선택 1개 바로 생성", self.request_generate_single),
            ("선택 여러개 대기열", self.request_queue_selected),
            ("전체(필터 결과) 대기열", self.request_queue_filtered_all),
        ]:
            btn = QPushButton(text)
            btn.setMinimumHeight(36)
            btn.clicked.connect(cb)
            actions.addWidget(btn)
        actions.addStretch(1)
        root.addLayout(actions)

        root.addWidget(self._build_auto_refine_box())
        root.addWidget(self._build_queue_box())
        root.addWidget(self._build_logs_box())

        fold_row = QHBoxLayout()
        self.fold_btn = QToolButton()
        self.fold_btn.setText("▼ 추가/편집")
        self.fold_btn.setCheckable(True)
        self.fold_btn.setChecked(True)
        self.fold_btn.clicked.connect(self.toggle_editor)
        fold_row.addWidget(self.fold_btn)
        fold_row.addStretch(1)
        root.addLayout(fold_row)

        self.editor_container = QWidget()
        editor_layout = QVBoxLayout(self.editor_container)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        row_name = QHBoxLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setMinimumHeight(34)
        self.name_edit.setPlaceholderText("파일명(확장자 제외)")
        row_name.addWidget(QLabel("이름"))
        row_name.addWidget(self.name_edit, 1)

        for text, cb in [("새로", self.new_item), ("저장", self.save_item), ("삭제", self.delete_item)]:
            btn = QPushButton(text)
            btn.setMinimumHeight(34)
            btn.clicked.connect(cb)
            row_name.addWidget(btn)

        editor_layout.addLayout(row_name)

        self.text_edit = QTextEdit()
        self.text_edit.setMinimumHeight(220)
        self.text_edit.setPlaceholderText("프롬프트 내용")
        editor_layout.addWidget(self.text_edit, 1)
        root.addWidget(self.editor_container)

        self.search_edit.setText("")
        self._load_api_settings()
        self.reload()
        self.reload_log_list()
        self._refresh_latest_image_label()
        return self.widget

    def _build_auto_refine_box(self) -> QGroupBox:
        box = QGroupBox("API 검수 + 자동 점검 재생성")
        box.setMinimumHeight(300)
        grid = QGridLayout(box)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        self.judge_mode_combo = QComboBox()
        self.judge_mode_combo.addItems([
            "api_openai_or_gemini",
            "local_yolo_anatomy",
            "local_mediapipe_pose_hand",
            "local_aesthetic_clip",
        ])

        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["openai", "gemini"])
        self.provider_combo.currentTextChanged.connect(self.on_provider_changed)

        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.on_provider_changed("openai")

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("API Key")

        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText("선택: 커스텀 Base URL")

        self.aesthetic_threshold_spin = QDoubleSpinBox()
        self.aesthetic_threshold_spin.setRange(0.0, 10.0)
        self.aesthetic_threshold_spin.setSingleStep(0.1)
        self.aesthetic_threshold_spin.setValue(5.0)

        self.anatomy_error_limit_spin = QSpinBox()
        self.anatomy_error_limit_spin.setRange(0, 20)
        self.anatomy_error_limit_spin.setValue(1)

        self.latest_image_label = QLabel("latest image: (탐색 중)")
        self.latest_image_label.setWordWrap(True)

        self.issue_status_label = QLabel("판정 기준: 의도와 다르거나 부자연스러우면 FAIL (Gemini 제안: 로컬 YOLO/MediaPipe/Aesthetic 가능)")
        self.issue_status_label.setStyleSheet("color:#D8D8D8;")

        self.fix_log_edit = QTextEdit()
        self.fix_log_edit.setPlaceholderText("무엇을 수정했는지 / 왜 퇴짜났는지")
        self.fix_log_edit.setMinimumHeight(100)

        row = 0
        grid.addWidget(QLabel("Judge"), row, 0)
        grid.addWidget(self.judge_mode_combo, row, 1)
        grid.addWidget(QLabel("Provider"), row, 2)
        grid.addWidget(self.provider_combo, row, 3)
        row += 1

        grid.addWidget(QLabel("Model"), row, 0)
        grid.addWidget(self.model_combo, row, 1, 1, 3)
        row += 1

        grid.addWidget(QLabel("API Key"), row, 0)
        grid.addWidget(self.api_key_edit, row, 1, 1, 3)
        row += 1

        grid.addWidget(QLabel("Base URL"), row, 0)
        grid.addWidget(self.base_url_edit, row, 1, 1, 3)
        row += 1

        grid.addWidget(QLabel("Aesthetic 임계값"), row, 0)
        grid.addWidget(self.aesthetic_threshold_spin, row, 1)
        grid.addWidget(QLabel("Anatomy 오류 허용"), row, 2)
        grid.addWidget(self.anatomy_error_limit_spin, row, 3)
        row += 1

        grid.addWidget(QLabel("최근 이미지"), row, 0)
        grid.addWidget(self.latest_image_label, row, 1, 1, 3)
        row += 1

        grid.addWidget(QLabel("판정"), row, 0)
        grid.addWidget(self.issue_status_label, row, 1, 1, 3)
        row += 1

        grid.addWidget(QLabel("로컬 안내"), row, 0)
        grid.addWidget(QLabel("local_* 모드는 controller에서 ultralytics/mediapipe/clip 모델이 준비되어야 동작 (권장 실패 조건: detected_errors > anatomy_error_limit)"), row, 1, 1, 3)
        row += 1

        grid.addWidget(QLabel("Fix Log"), row, 0)
        grid.addWidget(self.fix_log_edit, row, 1, 1, 3)
        row += 1

        btn_row = QHBoxLayout()
        for text, cb in [
            ("API 설정 저장", self._save_api_settings),
            ("API 설정 불러오기", self._load_api_settings),
            ("API 인증 테스트", self.test_api_auth),
            ("자동 점검+재생성 요청", self.request_auto_refine_generate),
            ("수정 로그만 저장", self.save_fix_log_only),
        ]:
            btn = QPushButton(text)
            btn.setMinimumHeight(36)
            btn.clicked.connect(cb)
            btn_row.addWidget(btn)
        btn_row.addStretch(1)
        grid.addLayout(btn_row, row, 0, 1, 4)
        return box

    def _build_queue_box(self) -> QGroupBox:
        box = QGroupBox("대기열")
        box.setMinimumHeight(240)
        v = QVBoxLayout(box)

        guide = QLabel("여러 프롬프트를 먼저 대기열에 넣고, 여기서 다음 1개/전체 실행을 누르세요.")
        guide.setWordWrap(True)
        v.addWidget(guide)

        self.queue_list = QListWidget()
        self.queue_list.setMinimumHeight(140)
        v.addWidget(self.queue_list)

        row = QHBoxLayout()
        for text, cb in [
            ("다음 1개 실행", self.request_queue_run_next),
            ("전체 실행", self.request_queue_run_all),
            ("중지 요청", self.request_queue_stop),
            ("선택 제거", self.request_queue_remove_selected),
            ("비우기", self.request_queue_clear),
        ]:
            btn = QPushButton(text)
            btn.setMinimumHeight(34)
            btn.clicked.connect(cb)
            row.addWidget(btn)
        row.addStretch(1)
        v.addLayout(row)
        return box

    def _build_logs_box(self) -> QGroupBox:
        box = QGroupBox("실행/오류 로그")
        box.setMinimumHeight(280)
        v = QVBoxLayout(box)
        top = QHBoxLayout()

        for text, cb in [("로그 새로고침", self.reload_log_list), ("로그 폴더 열기", self.open_log_folder)]:
            btn = QPushButton(text)
            btn.setMinimumHeight(34)
            btn.clicked.connect(cb)
            top.addWidget(btn)

        top.addStretch(1)
        v.addLayout(top)

        body = QHBoxLayout()
        self.log_list = QListWidget()
        self.log_list.setMinimumWidth(240)
        self.log_list.itemClicked.connect(self.on_log_selected)
        body.addWidget(self.log_list, 1)

        self.log_preview = QTextEdit()
        self.log_preview.setReadOnly(True)
        self.log_preview.setMinimumHeight(190)
        body.addWidget(self.log_preview, 2)
        v.addLayout(body)
        return box

    def on_provider_changed(self, provider: str):
        if not self.model_combo:
            return
        current = self.model_combo.currentText()
        self.model_combo.clear()
        self.model_combo.addItems(OPENAI_MODELS if provider == "openai" else GEMINI_MODELS)
        idx = self.model_combo.findText(current)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)

    def _find_latest_image_path(self) -> Optional[Path]:
        candidates: List[Path] = []
        if self.naia_root:
            for rel in ["save", "outputs", "output", "save/images", "save/output"]:
                d = (self.naia_root / rel)
                if d.exists() and d.is_dir():
                    candidates.append(d)

        best: Optional[Path] = None
        best_mtime = -1.0
        for base in candidates:
            try:
                for p in base.rglob("*"):
                    if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
                        mt = p.stat().st_mtime
                        if mt > best_mtime:
                            best_mtime = mt
                            best = p
            except Exception:
                continue
        return best

    def _refresh_latest_image_label(self):
        if not self.latest_image_label:
            return
        latest = self._find_latest_image_path()
        self.latest_image_label.setText(str(latest) if latest else "(이미지를 찾지 못함)")

    def reload(self):
        if not self.library_dir:
            self._files = []
            self.populate_table([])
            self.update_info(0, 0)
            return

        files: List[Path] = []
        for p in self.library_dir.rglob("*"):
            if p.is_file() and p.suffix.lower() == ".txt" and p.parent != self.log_dir:
                files.append(p)

        self._files = sorted(files, key=_natural_key)
        self.apply_filter()
        self._refresh_latest_image_label()

    def apply_filter(self):
        q = (self.search_edit.text() if self.search_edit else "").strip().lower()
        shown = self._files[:] if not q else [p for p in self._files if q in p.stem.lower()]
        self.populate_table(shown)
        self.update_info(len(self._files), len(shown))

    def populate_table(self, files: List[Path]):
        if not self.table:
            return
        self.table.setRowCount(0)
        fg = QBrush(QColor(237, 237, 237))

        for p in files:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setRowHeight(row, 32)

            name_item = QTableWidgetItem(p.stem)
            name_item.setForeground(fg)
            name_item.setData(Qt.ItemDataRole.UserRole, str(p))
            path_item = QTableWidgetItem(str(p))
            path_item.setForeground(fg)
            path_item.setData(Qt.ItemDataRole.UserRole, str(p))

            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, path_item)

        self.table.setColumnWidth(0, 260)
        self.table.horizontalHeader().setStretchLastSection(True)

    def update_info(self, scan_count: int, shown_count: int):
        if not self.info_label:
            return
        root = str(self.naia_root) if self.naia_root else "(none)"
        lib = str(self.library_dir) if self.library_dir else "(none)"
        listeners = self._bridge_listener_count if self._bridge_listener_count is not None else self._detect_event_listener_count()
        bridge = f"bridge=listeners:{listeners}" if listeners >= 0 else "bridge=unknown"
        self.info_label.setText(f"root={root} ({self.root_source}) | lib={lib} | scan={scan_count} shown={shown_count} | {bridge}")

    def open_folder(self):
        self._open_path(self.library_dir)

    def open_log_folder(self):
        self._open_path(self.log_dir)

    def _open_path(self, path: Optional[Path]):
        if not path:
            return
        try:
            import os
            os.startfile(str(path.resolve()))
        except Exception:
            QMessageBox.information(self.widget, "경로", str(path.resolve()))

    def split_prompt_txt(self):
        if not self.library_dir:
            return
        source = self.library_dir / "prompt.txt"
        if not source.exists():
            QMessageBox.information(self.widget, "분할", f"파일 없음: {source}")
            return

        lines = [line.strip() for line in _read_text_file(source).splitlines() if line.strip()]
        if not lines:
            QMessageBox.information(self.widget, "분할", "prompt.txt에 유효한 줄이 없습니다.")
            return

        for idx, line in enumerate(lines, start=1):
            (self.library_dir / f"{idx}.txt").write_text(line + "\n", encoding="utf-8")
        self.reload()
        QMessageBox.information(self.widget, "완료", f"{len(lines)}개 파일 생성")

    def toggle_editor(self):
        if not self.fold_btn or not self.editor_container:
            return
        opened = self.fold_btn.isChecked()
        self.editor_container.setVisible(opened)
        self.fold_btn.setText("▼ 추가/편집" if opened else "▶ 추가/편집")

    def new_item(self):
        if self.name_edit:
            self.name_edit.setText("")
        if self.text_edit:
            self.text_edit.setPlainText("")

    def save_item(self):
        if not self.library_dir:
            return
        name = (self.name_edit.text() if self.name_edit else "").strip()
        if not name:
            QMessageBox.information(self.widget, "알림", "파일명을 입력하세요.")
            return

        for ch in '<>:"/\\|?*':
            name = name.replace(ch, "_")

        text = _normalize_prompt_text(self.text_edit.toPlainText() if self.text_edit else "")
        if not text:
            QMessageBox.information(self.widget, "알림", "내용이 비어 있습니다.")
            return

        (self.library_dir / f"{name}.txt").write_text(text + "\n", encoding="utf-8")
        self.reload()

    def delete_item(self):
        paths = self.get_selected_paths()
        if len(paths) != 1:
            QMessageBox.information(self.widget, "알림", "삭제는 1개만 선택하세요.")
            return

        p = Path(paths[0])
        if not p.exists():
            return
        if QMessageBox.question(self.widget, "삭제", f"삭제할까요?\n{p.name}") != QMessageBox.StandardButton.Yes:
            return
        p.unlink(missing_ok=True)
        self.reload()

    def on_table_select(self):
        paths = self.get_selected_paths()
        if len(paths) != 1:
            return

        p = Path(paths[0])
        if not p.exists():
            return

        if self.name_edit:
            self.name_edit.setText(p.stem)
        if self.text_edit:
            self.text_edit.setPlainText(_read_text_file(p))

    def get_selected_paths(self) -> List[str]:
        if not self.table:
            return []
        rows = {it.row() for it in self.table.selectedItems()}
        out: List[str] = []
        for r in sorted(rows):
            it = self.table.item(r, 0)
            if it:
                out.append(str(it.data(Qt.ItemDataRole.UserRole)))
        return out

    def get_visible_paths(self) -> List[str]:
        if not self.table:
            return []
        out: List[str] = []
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it:
                out.append(str(it.data(Qt.ItemDataRole.UserRole)))
        return out


    def _detect_event_listener_count(self) -> int:
        if not self.app_context:
            return -1
        for attr in ("subscribers", "_subscribers", "event_subscribers", "_event_subscribers"):
            try:
                registry = getattr(self.app_context, attr, None)
                if isinstance(registry, dict):
                    listeners = registry.get(EVENT_NAME, [])
                    if isinstance(listeners, list):
                        return len(listeners)
            except Exception:
                pass
        return -1

    def _warn_if_bridge_missing(self, action: str):
        listeners = self._detect_event_listener_count()
        self._bridge_listener_count = listeners
        if listeners == 0:
            warn = (
                "MainController 브릿지가 연결되지 않아 요청이 처리되지 않을 수 있습니다. "
                "app_context.subscribe('prompt_library_event_requested', handler) 확인 필요"
            )
            self._write_fix_log("bridge_warning", "(none)", warn, {"action": action})
            QMessageBox.warning(self.widget, "브릿지 연결 필요", warn)

    def publish(self, payload: Dict[str, Any]):
        action = str(payload.get("action", "(unknown)"))
        self._warn_if_bridge_missing(action)
        if not self.app_context or not hasattr(self.app_context, "publish"):
            self._write_fix_log("error", "(none)", "AppContext.publish 없음", payload)
            QMessageBox.warning(self.widget, "오류", "AppContext.publish를 찾지 못했습니다.")
            return
        self.app_context.publish(EVENT_NAME, payload)
        self._write_fix_log("event_publish", "(none)", f"publish:{action}", {
            "action": action,
            "paths_count": len(payload.get("paths", [])) if isinstance(payload.get("paths", []), list) else 0,
            "run": payload.get("run"),
        })
        self.reload_log_list()
        if self._files:
            self.update_info(len(self._files), self.table.rowCount() if self.table else 0)

    def request_apply_replace(self):
        paths = self.get_selected_paths()
        if len(paths) != 1:
            QMessageBox.information(self.widget, "알림", "‘교체’는 1개만 선택하세요.")
            return
        self.publish({"action": "apply_replace", "paths": [paths[0]], "run": False})

    def request_generate_single(self):
        paths = self.get_selected_paths()
        if len(paths) != 1:
            QMessageBox.information(self.widget, "알림", "‘바로 생성’은 1개만 선택하세요.")
            return
        self.publish({"action": "generate_single", "paths": [paths[0]], "run": True})

    def request_queue_selected(self):
        paths = self.get_selected_paths()
        if not paths:
            QMessageBox.information(self.widget, "알림", "선택된 항목이 없습니다.")
            return
        self._append_queue_items(paths)
        self.publish({"action": "queue_sequence", "paths": paths, "run": False})

    def request_queue_filtered_all(self):
        paths = self.get_visible_paths()
        if not paths:
            QMessageBox.information(self.widget, "알림", "필터 결과가 비어 있습니다.")
            return
        # 요청사항: 전체 대기열은 즉시 실행이 아니라 큐에만 적재
        self._append_queue_items(paths)
        self.publish({"action": "queue_sequence", "paths": paths, "run": False})

    def _append_queue_items(self, paths: List[str]):
        if not self.queue_list:
            return
        existing = {
            str(self.queue_list.item(i).data(Qt.ItemDataRole.UserRole))
            for i in range(self.queue_list.count())
        }
        for p in paths:
            if p in existing:
                continue
            item = QListWidgetItem(Path(p).name)
            item.setToolTip(p)
            item.setData(Qt.ItemDataRole.UserRole, p)
            self.queue_list.addItem(item)

    def request_queue_run_next(self):
        self.publish({"action": "queue_run_next", "run": True})

    def request_queue_run_all(self):
        self.publish({"action": "queue_run_all", "run": True})

    def request_queue_stop(self):
        self.publish({"action": "queue_stop", "run": False})

    def request_queue_remove_selected(self):
        if not self.queue_list:
            return
        rows = sorted({idx.row() for idx in self.queue_list.selectedIndexes()}, reverse=True)
        if not rows:
            QMessageBox.information(self.widget, "대기열", "제거할 항목을 선택하세요.")
            return
        paths: List[str] = []
        for r in rows:
            item = self.queue_list.item(r)
            paths.append(str(item.data(Qt.ItemDataRole.UserRole)))
            self.queue_list.takeItem(r)
        self.publish({"action": "queue_remove", "paths": paths, "run": False})

    def request_queue_clear(self):
        if self.queue_list:
            self.queue_list.clear()
        self.publish({"action": "queue_clear", "run": False})

    def test_api_auth(self):
        judge_mode = self.judge_mode_combo.currentText() if self.judge_mode_combo else "api_openai_or_gemini"
        if judge_mode != "api_openai_or_gemini":
            QMessageBox.information(self.widget, "검수", "현재 Judge 모드는 로컬 추론 모드입니다. API 인증 테스트는 건너뜁니다.")
            return

        provider = self.provider_combo.currentText() if self.provider_combo else "openai"
        api_key = (self.api_key_edit.text() if self.api_key_edit else "").strip()
        base_url = (self.base_url_edit.text() if self.base_url_edit else "").strip()

        if not api_key:
            QMessageBox.warning(self.widget, "인증", "API Key를 입력하세요.")
            return

        try:
            ok, msg = self._probe_api(provider, api_key, base_url)
            self._write_fix_log("api_auth_test", "(none)", msg, {"provider": provider, "ok": ok})
            self.reload_log_list()
            QMessageBox.information(self.widget, "인증 결과", msg)
        except Exception as e:
            err = f"API 인증 실패: {e}"
            self._write_fix_log("api_auth_test", "(none)", err, {"provider": provider, "ok": False})
            self.reload_log_list()
            QMessageBox.warning(self.widget, "인증 결과", err)


    def _build_local_options(self, judge_mode: str) -> Dict[str, Any]:
        mapping = {
            "local_yolo_anatomy": "yolo_anatomy_check",
            "local_mediapipe_pose_hand": "mediapipe_pose_hand_check",
            "local_aesthetic_clip": "aesthetic_clip_check",
        }
        options = {
            "yolo_anatomy_check": False,
            "mediapipe_pose_hand_check": False,
            "aesthetic_clip_check": False,
        }
        key = mapping.get(judge_mode)
        if key:
            options[key] = True
        options["aesthetic_threshold"] = float(self.aesthetic_threshold_spin.value()) if self.aesthetic_threshold_spin else 5.0
        options["anatomy_error_limit"] = int(self.anatomy_error_limit_spin.value()) if self.anatomy_error_limit_spin else 1
        options["anatomy_fail_condition"] = "detected_errors_gt_limit"
        return options

    def _probe_api(self, provider: str, api_key: str, base_url: str) -> Tuple[bool, str]:
        if provider == "openai":
            url = (base_url.rstrip("/") + "/models") if base_url else "https://api.openai.com/v1/models"
            req = urllib.request.Request(url, method="GET")
            req.add_header("Authorization", f"Bearer {api_key}")
        else:
            model = "gemini-2.0-flash"
            if self.model_combo and self.model_combo.currentText():
                model = self.model_combo.currentText()
            root = base_url.rstrip("/") if base_url else "https://generativelanguage.googleapis.com/v1beta"
            url = f"{root}/models/{model}:generateContent?key={api_key}"
            body = json.dumps({"contents": [{"parts": [{"text": "ping"}]}]}).encode("utf-8")
            req = urllib.request.Request(url, data=body, method="POST")
            req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                code = getattr(resp, "status", 200)
                if 200 <= int(code) < 300:
                    return True, f"API 인증 성공: {provider} ({code})"
                return False, f"API 인증 실패: {provider} ({code})"
        except urllib.error.HTTPError as e:
            return False, f"API 인증 실패: {provider} ({e.code})"

    def request_auto_refine_generate(self):
        paths = self.get_selected_paths()
        if len(paths) != 1:
            QMessageBox.information(self.widget, "알림", "자동 점검은 프롬프트 1개를 선택하세요.")
            return

        judge_mode = self.judge_mode_combo.currentText() if self.judge_mode_combo else "api_openai_or_gemini"
        api_key = (self.api_key_edit.text() if self.api_key_edit else "").strip()
        if judge_mode == "api_openai_or_gemini" and not api_key:
            QMessageBox.warning(self.widget, "입력 오류", "API Key를 먼저 입력하세요.")
            return

        provider = self.provider_combo.currentText() if self.provider_combo else "openai"
        model = self.model_combo.currentText() if self.model_combo else "gpt-4.1"
        base_url = (self.base_url_edit.text() if self.base_url_edit else "").strip()
        fix_note = (self.fix_log_edit.toPlainText() if self.fix_log_edit else "").strip()

        latest = self._find_latest_image_path()
        image_path = str(latest) if latest else ""
        random_seed = random.randint(1, 2_147_483_647)

        local_options = self._build_local_options(judge_mode)

        payload = {
            "action": "auto_refine_generate",
            "paths": [paths[0]],
            "run": True,
            "image_path": image_path,
            "judge": {
                "mode": judge_mode,
                "provider": provider,
                "model": model,
                "api_key": api_key if judge_mode == "api_openai_or_gemini" else "",
                "base_url": base_url,
                "fail_if": "output_is_weird_or_unnatural_for_prompt_intent",
                "local_options": local_options,
                "backend_hints": {
                    "expected_controller": "generation_controller_or_judge_manager",
                    "yolo_reference_model": "person_yolov8n-seg.pt",
                },
            },
            "retry_policy": {
                "mode": "random_until_pass",
                "seed": random_seed,
                "max_attempts": 0,
            },
            "prompt_adjustment": {
                "remove_or_add_tokens": True,
                "goal": "make_output_natural_and_matching_intent",
            },
        }

        self.publish(payload)
        self._write_fix_log(
            "auto_refine_generate",
            paths[0],
            fix_note or "의도와 다르거나 부자연스러우면 퇴짜 후 랜덤 재시도",
            {
                "judge_mode": judge_mode,
                "provider": provider,
                "model": model,
                "image_path": image_path,
                "random_seed": random_seed,
                "mode": "random_until_pass",
                "max_attempts": 0,
            },
        )
        self.reload_log_list()
        self._refresh_latest_image_label()
        QMessageBox.information(self.widget, "완료", "자동 점검 요청 전송 + 로그 저장 완료")

    def save_fix_log_only(self):
        paths = self.get_selected_paths()
        prompt_path = paths[0] if paths else "(none)"
        summary = (self.fix_log_edit.toPlainText() if self.fix_log_edit else "").strip()
        if not summary:
            QMessageBox.information(self.widget, "로그", "수정 로그가 비어 있습니다.")
            return
        self._write_fix_log("manual_fix_note", prompt_path, summary, {})
        self.reload_log_list()
        QMessageBox.information(self.widget, "저장", "수정 로그를 저장했습니다.")

    def _save_api_settings(self):
        if not self.api_settings_path:
            return
        data = {
            "judge_mode": self.judge_mode_combo.currentText() if self.judge_mode_combo else "api_openai_or_gemini",
            "provider": self.provider_combo.currentText() if self.provider_combo else "openai",
            "model": self.model_combo.currentText() if self.model_combo else "gpt-4.1",
            "api_key": self.api_key_edit.text() if self.api_key_edit else "",
            "base_url": self.base_url_edit.text() if self.base_url_edit else "",
            "aesthetic_threshold": float(self.aesthetic_threshold_spin.value()) if self.aesthetic_threshold_spin else 5.0,
            "anatomy_error_limit": int(self.anatomy_error_limit_spin.value()) if self.anatomy_error_limit_spin else 1,
        }
        self.api_settings_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        QMessageBox.information(self.widget, "저장", f"API 설정 저장됨\n{self.api_settings_path}")

    def _load_api_settings(self):
        if not self.api_settings_path or not self.api_settings_path.exists():
            return
        try:
            data = json.loads(self.api_settings_path.read_text(encoding="utf-8"))
        except Exception:
            return

        judge_mode = str(data.get("judge_mode", "api_openai_or_gemini"))
        if self.judge_mode_combo:
            idx = self.judge_mode_combo.findText(judge_mode)
            self.judge_mode_combo.setCurrentIndex(0 if idx < 0 else idx)

        provider = str(data.get("provider", "openai"))
        if self.provider_combo:
            idx = self.provider_combo.findText(provider)
            self.provider_combo.setCurrentIndex(0 if idx < 0 else idx)
        self.on_provider_changed(provider)

        if self.model_combo:
            model = str(data.get("model", "gpt-4.1"))
            idx = self.model_combo.findText(model)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
        if self.api_key_edit:
            self.api_key_edit.setText(str(data.get("api_key", "")))
        if self.base_url_edit:
            self.base_url_edit.setText(str(data.get("base_url", "")))
        if self.aesthetic_threshold_spin:
            self.aesthetic_threshold_spin.setValue(float(data.get("aesthetic_threshold", 5.0)))
        if self.anatomy_error_limit_spin:
            self.anatomy_error_limit_spin.setValue(int(data.get("anatomy_error_limit", 1)))

    def _write_fix_log(self, title: str, prompt_path: str, summary: str, detail: Dict[str, Any]) -> Path:
        target = _next_numbered_txt(self.log_dir or (self.library_dir / "fix_logs"))
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [f"[{ts}] {title}", f"prompt={prompt_path}", f"summary={summary}", "details="]
        for k, v in detail.items():
            lines.append(f"- {k}: {v}")
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return target

    def reload_log_list(self):
        if not self.log_list:
            return
        self.log_list.clear()
        if not self.log_dir:
            return

        logs = sorted(self.log_dir.glob("*.txt"), key=_natural_key, reverse=True)
        for p in logs:
            item = QListWidgetItem(p.name)
            item.setData(Qt.ItemDataRole.UserRole, str(p))
            self.log_list.addItem(item)

    def on_log_selected(self, item: QListWidgetItem):
        if not self.log_preview:
            return
        path = Path(str(item.data(Qt.ItemDataRole.UserRole)))
        if not path.exists():
            self.log_preview.setPlainText("로그 파일을 찾을 수 없습니다.")
            return
        self.log_preview.setPlainText(_read_text_file(path))


def setup(app_context=None):
    m = PromptLibraryModule()
    if app_context is not None:
        try:
            m.initialize_with_context(app_context)
        except Exception:
            pass
        try:
            m.on_initialize()
        except Exception:
            pass
    return m
