import json
import time
import uuid

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config import BASE_DIR

NOTES_PATH = BASE_DIR / "notes.json"
SAVE_DELAY_MS = 500

STYLE = """
QWidget { color: white; background: transparent; font-family: 'Segoe UI'; }
QListWidget { background: rgba(255,255,255,0.05); border: none; border-radius: 10px; padding: 4px; outline: none; }
QListWidget::item { padding: 6px 8px; border-radius: 6px; color: #d0d0d0; }
QListWidget::item:selected { background: rgba(255,255,255,0.14); color: white; }
QPlainTextEdit { background: rgba(255,255,255,0.05); border: none; border-radius: 10px; padding: 8px;
    selection-background-color: %(accent)s; }
QPushButton { background: rgba(255,255,255,0.08); border: none; border-radius: 8px; padding: 4px 10px; }
QPushButton:hover { background: rgba(255,255,255,0.18); }
QScrollBar:vertical { width: 6px; background: transparent; }
QScrollBar::handle:vertical { background: rgba(255,255,255,0.25); border-radius: 3px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
"""


def load_notes():
    try:
        with NOTES_PATH.open(encoding="utf-8") as f:
            notes = json.load(f)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    if not isinstance(notes, list):
        return []
    return [n for n in notes if isinstance(n, dict) and isinstance(n.get("id"), str) and isinstance(n.get("text"), str)]


def save_notes(notes):
    tmp = NOTES_PATH.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)
    tmp.replace(NOTES_PATH)


def note_title(text, fallback):
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:60]
    return fallback


class NotesWindow(QWidget):
    def __init__(self, config):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.ru = config["language"] == "ru"
        self.setWindowTitle(self._t("Заметки", "Notes"))
        scale = config["scale"]
        self.resize(round(560 * scale), round(360 * scale))
        accent = config["accent"] if config["accent"] != "cover" else "#ff4d6d"
        self.setStyleSheet(STYLE % {"accent": accent})
        font = QFont("Segoe UI")
        font.setPixelSize(round(13 * scale))
        self.setFont(font)

        self.notes = load_notes()
        self._drag_offset = None
        self.save_timer = QTimer(self, singleShot=True, interval=SAVE_DELAY_MS, timeout=self._save)

        title = QLabel(self._t("Заметки", "Notes"))
        title_font = QFont(font)
        title_font.setWeight(QFont.DemiBold)
        title_font.setPixelSize(round(15 * scale))
        title.setFont(title_font)
        add = QPushButton("+", clicked=self.add_note, toolTip=self._t("Новая заметка", "New note"))
        delete = QPushButton(self._t("Удалить", "Delete"), clicked=self.delete_note)
        close = QPushButton("✕", clicked=self.hide)
        header = QHBoxLayout()
        header.addWidget(title)
        header.addStretch()
        for button in (add, delete, close):
            header.addWidget(button)

        self.list = QListWidget()
        self.list.setFixedWidth(round(170 * scale))
        self.list.currentRowChanged.connect(self._on_select)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText(self._t("Пиши здесь…", "Write here…"))
        self.editor.textChanged.connect(self._on_text_changed)
        body = QHBoxLayout()
        body.addWidget(self.list)
        body.addWidget(self.editor, 1)

        layout = QVBoxLayout(self)
        margin = round(14 * scale)
        layout.setContentsMargins(margin, round(10 * scale), margin, margin)
        layout.setSpacing(round(8 * scale))
        layout.addLayout(header)
        layout.addLayout(body, 1)

        self._fill_list()
        if not self.notes:
            self.editor.setEnabled(False)

    def _t(self, ru, en):
        return ru if self.ru else en

    def _fill_list(self, select=0):
        self.list.blockSignals(True)
        self.list.clear()
        for note in self.notes:
            self.list.addItem(QListWidgetItem(note_title(note["text"], self._t("Новая заметка", "New note"))))
        self.list.blockSignals(False)
        if self.notes:
            self.list.setCurrentRow(min(select, len(self.notes) - 1))
            self._on_select(self.list.currentRow())

    def _on_select(self, row):
        self.editor.blockSignals(True)
        if 0 <= row < len(self.notes):
            self.editor.setEnabled(True)
            self.editor.setPlainText(self.notes[row]["text"])
        else:
            self.editor.clear()
            self.editor.setEnabled(False)
        self.editor.blockSignals(False)

    def _on_text_changed(self):
        row = self.list.currentRow()
        if not 0 <= row < len(self.notes):
            return
        note = self.notes[row]
        note["text"] = self.editor.toPlainText()
        note["updated"] = time.time()
        self.list.item(row).setText(note_title(note["text"], self._t("Новая заметка", "New note")))
        self.save_timer.start()

    def add_note(self):
        now = time.time()
        self.notes.insert(0, {"id": uuid.uuid4().hex, "text": "", "created": now, "updated": now})
        self._fill_list(0)
        self.editor.setFocus()
        self.save_timer.start()

    def delete_note(self):
        row = self.list.currentRow()
        if not 0 <= row < len(self.notes):
            return
        del self.notes[row]
        self._fill_list(row)
        if not self.notes:
            self._on_select(-1)
        self.save_timer.start()

    def _save(self):
        try:
            save_notes(self.notes)
        except OSError:
            pass

    def show_near(self, anchor, screen):
        if not self.isVisible():
            screen = screen.availableGeometry()
            x = anchor.x() + (anchor.width() - self.width()) // 2
            y = anchor.y() + anchor.height() + 4
            x = min(max(x, screen.left()), screen.right() - self.width())
            y = min(max(y, screen.top()), screen.bottom() - self.height())
            self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.editor.setFocus()

    def toggle_near(self, anchor, screen):
        if self.isVisible():
            self.hide()
        else:
            self.show_near(anchor, screen)

    def flush(self):
        if self.save_timer.isActive():
            self.save_timer.stop()
            self._save()

    def hideEvent(self, event):
        self.flush()
        super().hideEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 18, 18)
        painter.fillPath(path, QColor(12, 14, 22, 245))
