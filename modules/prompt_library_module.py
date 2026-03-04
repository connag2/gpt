from __future__ import annotations

"""
NAIA Prompt Library Module

- prompt_library/*.txt 목록/검색/편집
- 단일 적용/생성/대기열 publish
- prompt.txt 분할(1.txt,2.txt...)
- 자연 정렬
- Auto Refine 요청 payload 발행
- API 설정 저장/불러오기
- 실행/오류 로그를 fix_logs/*.txt로 저장 + UI에서 조회
"""

import json
import re
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
)

try:
    from interfaces.base_module import BaseMiddleModule
except ImportError:
    from ..interfaces.base_module import BaseMiddleModule

EVENT_NAME = "prompt_library_event_requested"


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

        self.provider_combo: Optional[QComboBox] = None
        self.model_edit: Optional[QLineEdit] = None
        self.api_key_edit: Optional[QLineEdit] = None
        self.base_url_edit: Optional[QLineEdit] = None
        self.image_path_edit: Optional[QLineEdit] = None
        self.max_retry_edit: Optional[QLineEdit] = None
        self.seed_step_edit: Optional[QLineEdit] = None
        self.issue_hint_edit: Optional[QLineEdit] = None
        self.fix_log_edit: Optional[QTextEdit] = None

        self.log_list: Optional[QListWidget] = None
        self.log_preview: Optional[QTextEdit] = None

        self._files: List[Path] = []

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
        root = QVBoxLayout(self.widget)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self.info_label = QLabel("")
        self.info_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.info_label)

        top = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("검색(파일명) — 비우면 전체 표시")
        self.search_edit.textChanged.connect(self.apply_filter)
        top.addWidget(self.search_edit, 1)

        btn_clear = QPushButton("지우기")
        btn_clear.clicked.connect(lambda: self.search_edit.setText(""))
        top.addWidget(btn_clear)

        btn_refresh = QPushButton("새로고침")
        btn_refresh.clicked.connect(self.reload)
        top.addWidget(btn_refresh)

        btn_open = QPushButton("폴더 열기")
        btn_open.clicked.connect(self.open_folder)
        top.addWidget(btn_open)

        btn_split = QPushButton("prompt.txt 분할")
        btn_split.clicked.connect(self.split_prompt_txt)
        top.addWidget(btn_split)

        root.addLayout(top)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["이름", "경로"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(False)

        font = QFont()
        font.setPointSize(10)
        self.table.setFont(font)

        self.table.setStyleSheet(
            """
QTableWidget {
  border: 1px solid rgba(255,255,255,0.12);
  background: rgba(0,0,0,0.15);
  gridline-color: rgba(255,255,255,0.08);
  color: #EDEDED;
}
QHeaderView::section {
  background: rgba(255,255,255,0.06);
  color: #EDEDED;
  padding: 6px;
  border: 1px solid rgba(255,255,255,0.08);
}
QTableWidget::item:selected {
  background: rgba(120,160,255,0.35);
  color: #FFFFFF;
}
"""
        )
        self.table.itemSelectionChanged.connect(self.on_table_select)
        root.addWidget(self.table, 2)

        actions = QHBoxLayout()
        btn_apply = QPushButton("메인에 넣기(교체)")
        btn_apply.clicked.connect(self.request_apply_replace)
        actions.addWidget(btn_apply)

        btn_gen1 = QPushButton("선택 1개 바로 생성")
        btn_gen1.clicked.connect(self.request_generate_single)
        actions.addWidget(btn_gen1)

        btn_queue_sel = QPushButton("선택 여러개 대기열")
        btn_queue_sel.clicked.connect(self.request_queue_selected)
        actions.addWidget(btn_queue_sel)

        btn_queue_all = QPushButton("전체(필터 결과) 대기열")
        btn_queue_all.clicked.connect(self.request_queue_filtered_all)
        actions.addWidget(btn_queue_all)

        actions.addStretch(1)
        root.addLayout(actions)

        root.addWidget(self._build_auto_refine_box())
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
        self.name_edit.setPlaceholderText("파일명(확장자 제외)")
        row_name.addWidget(QLabel("이름"))
        row_name.addWidget(self.name_edit, 1)

        btn_new = QPushButton("새로")
        btn_new.clicked.connect(self.new_item)
        row_name.addWidget(btn_new)

        btn_save = QPushButton("저장")
        btn_save.clicked.connect(self.save_item)
        row_name.addWidget(btn_save)

        btn_delete = QPushButton("삭제")
        btn_delete.clicked.connect(self.delete_item)
        row_name.addWidget(btn_delete)

        editor_layout.addLayout(row_name)

        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("프롬프트 내용")
        self.text_edit.setMinimumHeight(120)
        editor_layout.addWidget(self.text_edit, 1)

        root.addWidget(self.editor_container, 1)

        self.search_edit.setText("")
        self._load_api_settings()
        self.reload()
        self.reload_log_list()
        return self.widget

    def _build_auto_refine_box(self) -> QGroupBox:
        box = QGroupBox("자동 점검 + 재생성 (API 설정 포함)")
        grid = QGridLayout(box)

        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["openai", "gemini"])
        self.model_edit = QLineEdit("gpt-4.1")
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("API Key")
        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText("선택: 커스텀 base_url")

        self.image_path_edit = QLineEdit()
        self.image_path_edit.setPlaceholderText("검수할 이미지 경로")
        self.max_retry_edit = QLineEdit("3")
        self.seed_step_edit = QLineEdit("97")
        self.issue_hint_edit = QLineEdit()
        self.issue_hint_edit.setPlaceholderText("문제 힌트(선택)")
        self.fix_log_edit = QTextEdit()
        self.fix_log_edit.setPlaceholderText("무엇을 고쳤는지/고칠지")
        self.fix_log_edit.setMaximumHeight(64)

        row = 0
        grid.addWidget(QLabel("Provider"), row, 0)
        grid.addWidget(self.provider_combo, row, 1)
        grid.addWidget(QLabel("Model"), row, 2)
        grid.addWidget(self.model_edit, row, 3)
        row += 1

        grid.addWidget(QLabel("API Key"), row, 0)
        grid.addWidget(self.api_key_edit, row, 1, 1, 3)
        row += 1

        grid.addWidget(QLabel("Base URL"), row, 0)
        grid.addWidget(self.base_url_edit, row, 1, 1, 3)
        row += 1

        grid.addWidget(QLabel("Image Path"), row, 0)
        grid.addWidget(self.image_path_edit, row, 1, 1, 3)
        row += 1

        grid.addWidget(QLabel("Max Retry"), row, 0)
        grid.addWidget(self.max_retry_edit, row, 1)
        grid.addWidget(QLabel("Seed Step"), row, 2)
        grid.addWidget(self.seed_step_edit, row, 3)
        row += 1

        grid.addWidget(QLabel("Issue Hint"), row, 0)
        grid.addWidget(self.issue_hint_edit, row, 1, 1, 3)
        row += 1

        grid.addWidget(QLabel("Fix Note"), row, 0)
        grid.addWidget(self.fix_log_edit, row, 1, 1, 3)
        row += 1

        btn_row = QHBoxLayout()
        btn_save_api = QPushButton("API 설정 저장")
        btn_save_api.clicked.connect(self._save_api_settings)
        btn_row.addWidget(btn_save_api)

        btn_load_api = QPushButton("API 설정 불러오기")
        btn_load_api.clicked.connect(self._load_api_settings)
        btn_row.addWidget(btn_load_api)

        btn_auto = QPushButton("자동 점검+재생성 요청")
        btn_auto.clicked.connect(self.request_auto_refine_generate)
        btn_row.addWidget(btn_auto)

        btn_log_only = QPushButton("수정 로그만 저장")
        btn_log_only.clicked.connect(self.save_fix_log_only)
        btn_row.addWidget(btn_log_only)

        btn_row.addStretch(1)
        grid.addLayout(btn_row, row, 0, 1, 4)
        return box

    def _build_logs_box(self) -> QGroupBox:
        box = QGroupBox("실행/오류 로그")
        v = QVBoxLayout(box)
        top = QHBoxLayout()

        btn_reload = QPushButton("로그 새로고침")
        btn_reload.clicked.connect(self.reload_log_list)
        top.addWidget(btn_reload)

        btn_open = QPushButton("로그 폴더 열기")
        btn_open.clicked.connect(self.open_log_folder)
        top.addWidget(btn_open)

        top.addStretch(1)
        v.addLayout(top)

        body = QHBoxLayout()
        self.log_list = QListWidget()
        self.log_list.itemClicked.connect(self.on_log_selected)
        body.addWidget(self.log_list, 1)

        self.log_preview = QTextEdit()
        self.log_preview.setReadOnly(True)
        body.addWidget(self.log_preview, 2)
        v.addLayout(body)
        return box

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
            self.table.setRowHeight(row, 28)

            name_item = QTableWidgetItem(p.stem)
            name_item.setForeground(fg)
            name_item.setData(Qt.ItemDataRole.UserRole, str(p))
            path_item = QTableWidgetItem(str(p))
            path_item.setForeground(fg)
            path_item.setData(Qt.ItemDataRole.UserRole, str(p))

            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, path_item)

        self.table.setColumnWidth(0, 240)
        self.table.horizontalHeader().setStretchLastSection(True)

    def update_info(self, scan_count: int, shown_count: int):
        if not self.info_label:
            return
        root = str(self.naia_root) if self.naia_root else "(none)"
        lib = str(self.library_dir) if self.library_dir else "(none)"
        self.info_label.setText(
            f"root={root} ({self.root_source}) | lib={lib} | scan={scan_count} shown={shown_count}"
        )

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
        out = []
        for r in sorted(rows):
            it = self.table.item(r, 0)
            if it:
                out.append(str(it.data(Qt.ItemDataRole.UserRole)))
        return out

    def get_visible_paths(self) -> List[str]:
        if not self.table:
            return []
        out = []
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it:
                out.append(str(it.data(Qt.ItemDataRole.UserRole)))
        return out

    def publish(self, payload: Dict[str, Any]):
        if not self.app_context or not hasattr(self.app_context, "publish"):
            self._write_fix_log("error", "(none)", "AppContext.publish 없음", payload)
            QMessageBox.warning(self.widget, "오류", "AppContext.publish를 찾지 못했습니다.")
            return
        self.app_context.publish(EVENT_NAME, payload)

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
        self.publish({"action": "queue_sequence", "paths": paths, "run": True})

    def request_queue_filtered_all(self):
        paths = self.get_visible_paths()
        if not paths:
            QMessageBox.information(self.widget, "알림", "필터 결과가 비어 있습니다.")
            return
        self.publish({"action": "queue_sequence", "paths": paths, "run": True})

    def request_auto_refine_generate(self):
        paths = self.get_selected_paths()
        if len(paths) != 1:
            QMessageBox.information(self.widget, "알림", "자동 점검은 프롬프트 1개를 선택하세요.")
            return

        api_key = (self.api_key_edit.text() if self.api_key_edit else "").strip()
        if not api_key:
            QMessageBox.warning(self.widget, "입력 오류", "API Key를 먼저 입력하세요.")
            return

        try:
            max_retry = max(1, int((self.max_retry_edit.text() if self.max_retry_edit else "3").strip()))
            seed_step = int((self.seed_step_edit.text() if self.seed_step_edit else "97").strip())
        except ValueError:
            QMessageBox.warning(self.widget, "입력 오류", "Max Retry / Seed Step은 숫자여야 합니다.")
            return

        provider = self.provider_combo.currentText() if self.provider_combo else "openai"
        model = (self.model_edit.text() if self.model_edit else "gpt-4.1").strip() or "gpt-4.1"
        image_path = (self.image_path_edit.text() if self.image_path_edit else "").strip()
        issue_hint = (self.issue_hint_edit.text() if self.issue_hint_edit else "").strip()
        fix_note = (self.fix_log_edit.toPlainText() if self.fix_log_edit else "").strip()
        base_url = (self.base_url_edit.text() if self.base_url_edit else "").strip()

        payload = {
            "action": "auto_refine_generate",
            "paths": [paths[0]],
            "run": True,
            "image_path": image_path,
            "judge": {
                "provider": provider,
                "model": model,
                "api_key": api_key,
                "base_url": base_url,
                "instruction": "이미지 이상 부위를 찾고 짧은 수정 프롬프트를 제안",
            },
            "retry_policy": {
                "max_attempts": max_retry,
                "seed_increment": seed_step,
                "fallback": "seed_only_then_prompt_plus_seed",
            },
            "issue_hint": issue_hint,
        }

        self.publish(payload)
        self._write_fix_log(
            "auto_refine_generate",
            paths[0],
            fix_note or "자동 점검+재생성 요청",
            {
                "provider": provider,
                "model": model,
                "image_path": image_path,
                "max_retry": max_retry,
                "seed_step": seed_step,
                "issue_hint": issue_hint,
            },
        )
        self.reload_log_list()
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
            "provider": self.provider_combo.currentText() if self.provider_combo else "openai",
            "model": self.model_edit.text() if self.model_edit else "",
            "api_key": self.api_key_edit.text() if self.api_key_edit else "",
            "base_url": self.base_url_edit.text() if self.base_url_edit else "",
            "max_retry": self.max_retry_edit.text() if self.max_retry_edit else "3",
            "seed_step": self.seed_step_edit.text() if self.seed_step_edit else "97",
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

        if self.provider_combo:
            idx = self.provider_combo.findText(str(data.get("provider", "openai")))
            self.provider_combo.setCurrentIndex(0 if idx < 0 else idx)
        if self.model_edit:
            self.model_edit.setText(str(data.get("model", "gpt-4.1")))
        if self.api_key_edit:
            self.api_key_edit.setText(str(data.get("api_key", "")))
        if self.base_url_edit:
            self.base_url_edit.setText(str(data.get("base_url", "")))
        if self.max_retry_edit:
            self.max_retry_edit.setText(str(data.get("max_retry", "3")))
        if self.seed_step_edit:
            self.seed_step_edit.setText(str(data.get("seed_step", "97")))

    def _write_fix_log(self, title: str, prompt_path: str, summary: str, detail: Dict[str, Any]) -> Path:
        target = _next_numbered_txt(self.log_dir or (self.library_dir / "fix_logs"))
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            f"[{ts}] {title}",
            f"prompt={prompt_path}",
            f"summary={summary}",
            "details=",
        ]
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
