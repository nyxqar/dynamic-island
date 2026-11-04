import json
import re
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QColor, QDesktopServices, QFontMetricsF, QImage, QPainter, QPainterPath, QPen, QPixmap, QTextCharFormat,
    QTextCursor, QTextDocument, QTextImageFormat,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStackedLayout,
    QStyle,
    QStyledItemDelegate,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import BASE_DIR
from ui.card import CardWindow
from ui.theme import font
from ui.widgets import SCROLLBAR_STYLE, IconButton, accent_of

NOTES_PATH = BASE_DIR / "notes.json"
SAVE_DELAY_MS = 500
# Pictures are kept as files next to notes.json; the note text holds a marker like ![image](name.png).
IMAGE_MARK = re.compile(r"!\[image\]\(([^)\s]+)\)")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
MAX_IMAGE_SIDE = 1600

STYLE = """
QWidget { color: white; background: transparent; }
QListWidget { border: none; outline: none; }
QTextEdit { border: none; selection-background-color: %(accent)s; }
""" + SCROLLBAR_STYLE

DIM = QColor(255, 255, 255, 120)
TEXT = QColor(255, 255, 255, 235)


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


def images_dir():
    return NOTES_PATH.parent / "notes_images"


def note_images(text):
    # Only bare file names: a marker must never point outside the images folder.
    return [name for name in IMAGE_MARK.findall(text) if Path(name).name == name]


def save_image(image):
    """Stores a pasted picture as a PNG in the images folder and returns its file name."""
    if max(image.width(), image.height()) > MAX_IMAGE_SIDE:
        image = image.scaled(MAX_IMAGE_SIDE, MAX_IMAGE_SIDE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    folder = images_dir()
    folder.mkdir(exist_ok=True)
    name = uuid.uuid4().hex + ".png"
    if not image.save(str(folder / name), "PNG"):
        return None
    return name


def remove_unused_images(notes):
    folder = images_dir()
    if not folder.is_dir():
        return
    used = {name for note in notes for name in note_images(note["text"])}
    for path in folder.glob("*.png"):
        if path.name not in used:
            try:
                path.unlink()
            except OSError:
                pass


def _text_lines(text):
    return [line.strip() for line in IMAGE_MARK.sub("", text).splitlines() if line.strip()]


def note_title(text, fallback, image_title=None):
    lines = _text_lines(text)
    if lines:
        return lines[0][:60]
    return image_title if image_title and note_images(text) else fallback


def note_preview(text):
    lines = _text_lines(text)
    return lines[1][:80] if len(lines) > 1 else ""


class NoteEditor(QTextEdit):
    """Plain text plus pictures: paste one (Ctrl+V) or drop an image file; double-click opens it."""

    def __init__(self):
        super().__init__()
        self.setAcceptRichText(False)
        # Text typed right after a picture would inherit its format and turn into copies of it.
        self.currentCharFormatChanged.connect(self._plain_after_image)

    def _plain_after_image(self, fmt):
        if fmt.isImageFormat():
            self.setCurrentCharFormat(QTextCharFormat())

    def _max_width(self):
        return max(80, self.viewport().width() - 2 * self.document().documentMargin() - 4)

    def _insert_image(self, cursor, name):
        image = QImage(str(images_dir() / name))
        if image.isNull():
            # Keep the marker when the file is gone, so the note is not silently changed.
            cursor.insertText(f"![image]({name})")
            return
        self.document().addResource(QTextDocument.ImageResource, QUrl(name), image)
        fmt = QTextImageFormat()
        fmt.setName(name)
        width = min(image.width(), self._max_width())
        fmt.setWidth(width)
        fmt.setHeight(image.height() * width / image.width())
        cursor.insertImage(fmt)
        cursor.setCharFormat(QTextCharFormat())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if event.oldSize().width() != event.size().width():
            self._refit_images()

    def _refit_images(self):
        """Pictures are as wide as the editor at most; the width is only known once it is laid out."""
        limit = self._max_width()
        document = self.document()
        changes = []
        block = document.begin()
        while block.isValid():
            for it in block:
                fragment = it.fragment()
                fmt = fragment.charFormat()
                if not fmt.isImageFormat():
                    continue
                fmt = fmt.toImageFormat()
                image = document.resource(QTextDocument.ImageResource, QUrl(fmt.name()))
                if not isinstance(image, QImage) or image.isNull():
                    continue
                width = min(image.width(), limit)
                if abs(fmt.width() - width) >= 0.5:
                    fmt.setWidth(width)
                    fmt.setHeight(image.height() * width / image.width())
                    changes.append((fragment.position(), fragment.length(), fmt))
            block = block.next()
        if not changes:
            return
        # A layout change, not an edit: no textChanged (the note would look modified) and no undo step.
        self.blockSignals(True)
        undo = document.isUndoRedoEnabled()
        document.setUndoRedoEnabled(False)
        for position, length, fmt in changes:
            cursor = QTextCursor(document)
            cursor.setPosition(position)
            cursor.setPosition(position + length, QTextCursor.KeepAnchor)
            cursor.setCharFormat(fmt)
        document.setUndoRedoEnabled(undo)
        self.blockSignals(False)

    def set_note_text(self, text):
        self.clear()
        cursor = QTextCursor(self.document())
        position = 0
        for match in IMAGE_MARK.finditer(text):
            cursor.insertText(text[position:match.start()])
            name = match.group(1)
            if Path(name).name == name:
                self._insert_image(cursor, name)
            else:
                cursor.insertText(match.group(0))
            position = match.end()
        cursor.insertText(text[position:])
        self.moveCursor(QTextCursor.Start)
        self.document().clearUndoRedoStacks()

    def note_text(self):
        lines = []
        block = self.document().begin()
        while block.isValid():
            parts = []
            for it in block:
                fragment = it.fragment()
                fmt = fragment.charFormat()
                if fmt.isImageFormat():
                    # Identical pictures next to each other share one fragment, one character each.
                    parts.append(f"![image]({fmt.toImageFormat().name()})" * len(fragment.text()))
                else:
                    parts.append(fragment.text())
            lines.append("".join(parts))
            block = block.next()
        return "\n".join(lines)

    @staticmethod
    def _image_files(source):
        if not source.hasUrls():
            return []
        return [url.toLocalFile() for url in source.urls()
                if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in IMAGE_SUFFIXES]

    def canInsertFromMimeData(self, source):
        return source.hasImage() or bool(self._image_files(source)) or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        images = []
        if source.hasImage():
            data = source.imageData()
            images.append(data.toImage() if isinstance(data, QPixmap) else QImage(data))
        else:
            images = [QImage(path) for path in self._image_files(source)]
        images = [image for image in images if not image.isNull()]
        if not images:
            super().insertFromMimeData(source)
            return
        cursor = self.textCursor()
        for image in images:
            name = save_image(image)
            if name:
                self._insert_image(cursor, name)
        self.setTextCursor(cursor)

    def _image_at(self, pos):
        position = self.cursorForPosition(pos).position()
        # The click lands next to the picture's character; check the one after and the one before.
        for index in (position, position - 1):
            if index >= 0 and self.document().characterAt(index) == "￼":
                probe = QTextCursor(self.document())
                probe.setPosition(index + 1)
                fmt = probe.charFormat()
                if fmt.isImageFormat():
                    return fmt.toImageFormat().name()
        return None

    def mouseDoubleClickEvent(self, event):
        name = self._image_at(event.position().toPoint())
        if name and (images_dir() / name).is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(images_dir() / name)))
            return
        super().mouseDoubleClickEvent(event)


def note_date(timestamp, ru):
    if not isinstance(timestamp, (int, float)):
        return ""
    moment = datetime.fromtimestamp(timestamp)
    today = date.today()
    if moment.date() == today:
        return moment.strftime("%H:%M")
    if moment.date() == today - timedelta(days=1):
        return "вчера" if ru else "yesterday"
    months_ru = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
    months_en = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    month = (months_ru if ru else months_en)[moment.month - 1]
    return f"{moment.day} {month}" if ru else f"{month} {moment.day}"


class NoteDelegate(QStyledItemDelegate):
    def __init__(self, scale, accent, parent):
        super().__init__(parent)
        self.scale = scale
        self.accent = accent
        self.title_font = font(13 * scale, 600)
        self.small_font = font(12 * scale)
        self.date_font = font(11 * scale, 500, True)
        self._thumbs = {}

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), round(56 * self.scale))

    def _thumb(self, name, side, dpr):
        key = (name, side)
        if key not in self._thumbs:
            image = QImage(str(images_dir() / name))
            pixmap = None
            if not image.isNull():
                px = round(side * dpr)
                image = image.scaled(px, px, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                pixmap = QPixmap(px, px)
                pixmap.fill(Qt.transparent)
                painter = QPainter(pixmap)
                painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
                clip = QPainterPath()
                clip.addRoundedRect(QRectF(0, 0, px, px), 7 * self.scale * dpr, 7 * self.scale * dpr)
                painter.setClipPath(clip)
                painter.drawImage((px - image.width()) // 2, (px - image.height()) // 2, image)
                painter.end()
                pixmap.setDevicePixelRatio(dpr)
            self._thumbs[key] = pixmap
        return self._thumbs[key]

    def paint(self, p, option, index):
        s = self.scale
        title, preview, stamp, image = index.data(Qt.UserRole)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(option.rect).adjusted(2 * s, 2 * s, -2 * s, -2 * s)
        selected = bool(option.state & QStyle.State_Selected)
        hover = bool(option.state & QStyle.State_MouseOver)
        if selected or hover:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 24 if selected else 10))
            p.drawRoundedRect(r, 10 * s, 10 * s)
        if selected:
            p.setBrush(self.accent)
            p.drawRoundedRect(QRectF(r.left() + 5 * s, r.top() + 14 * s, 3 * s, r.height() - 28 * s), 1.5 * s, 1.5 * s)

        left = r.left() + 16 * s
        right = r.right() - 10 * s
        thumb = self._thumb(image, round(36 * s), option.widget.devicePixelRatioF()) if image else None
        if thumb:
            side = 36 * s
            p.drawPixmap(QPointF(right - side, r.center().y() - side / 2), thumb)
            right -= side + 8 * s
        p.setFont(self.date_font)
        date_width = QFontMetricsF(self.date_font).horizontalAdvance(stamp)
        p.setPen(DIM)
        p.drawText(QRectF(right - date_width, r.top() + 8 * s, date_width, 20 * s), Qt.AlignRight | Qt.AlignVCenter,
                   stamp)

        width = right - left - date_width - 8 * s
        p.setFont(self.title_font)
        p.setPen(TEXT if selected else QColor(255, 255, 255, 205))
        elided = QFontMetricsF(self.title_font).elidedText(title, Qt.ElideRight, width)
        p.drawText(QRectF(left, r.top() + 8 * s, width, 20 * s), Qt.AlignLeft | Qt.AlignVCenter, elided)
        if preview:
            p.setFont(self.small_font)
            p.setPen(DIM)
            elided = QFontMetricsF(self.small_font).elidedText(preview, Qt.ElideRight, right - left)
            p.drawText(QRectF(left, r.top() + 28 * s, right - left, 18 * s), Qt.AlignLeft | Qt.AlignVCenter, elided)
        p.restore()


class NotesWindow(CardWindow):
    def __init__(self, config):
        scale = config["scale"]
        super().__init__(scale, 600, 380)
        self.ru = config["language"] == "ru"
        self.setWindowTitle(self._t("Заметки", "Notes"))
        self.accent = accent_of(config)
        self.setStyleSheet(STYLE % {"accent": self.accent.name()})
        self.setFont(font(13 * scale))

        self.notes = load_notes()
        # Pictures removed from notes in earlier sessions; nothing can bring them back by undo any more.
        remove_unused_images(self.notes)
        self.save_timer = QTimer(self, singleShot=True, interval=SAVE_DELAY_MS, timeout=self._save)

        title = QLabel(self._t("Заметки", "Notes"))
        title.setFont(font(18 * scale, 600))
        self.count = QLabel()
        self.count.setFont(font(13 * scale, 500, True))
        self.count.setStyleSheet("color: rgba(255,255,255,0.45);")
        add = IconButton("plus", scale, self._t("Новая заметка", "New note"))
        add.clicked.connect(self.add_note)
        self.delete_button = IconButton("trash", scale, self._t("Удалить", "Delete"), danger=True)
        self.delete_button.clicked.connect(self.delete_note)
        close = IconButton("close", scale, self._t("Закрыть", "Close"))
        close.clicked.connect(self.animated_hide)
        header = QHBoxLayout()
        header.setSpacing(round(4 * scale))
        header.addWidget(title)
        header.addSpacing(round(6 * scale))
        header.addWidget(self.count, 0, Qt.AlignBottom)
        header.addStretch()
        for button in (add, self.delete_button, close):
            header.addWidget(button)

        self.list = QListWidget()
        self.list.setMouseTracking(True)
        self.list.setItemDelegate(NoteDelegate(scale, self.accent, self.list))
        self.list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.currentRowChanged.connect(self._on_select)
        self.empty = QLabel(self._t("Пока пусто", "Nothing here yet"), alignment=Qt.AlignCenter)
        self.empty.setFont(font(13 * scale))
        self.empty.setStyleSheet("color: rgba(255,255,255,0.4);")
        self.list_column = QWidget()
        self.list_column.setFixedWidth(round(200 * scale))
        self.list_stack = QStackedLayout(self.list_column)
        self.list_stack.addWidget(self.list)
        self.list_stack.addWidget(self.empty)

        self.meta = QLabel()
        self.meta.setFont(font(11 * scale, 500))
        self.meta.setStyleSheet("color: rgba(255,255,255,0.4);")
        self.editor = NoteEditor()
        self.editor.setFont(font(14 * scale))
        self.editor.setPlaceholderText(self._placeholder())
        self.editor.textChanged.connect(self._on_text_changed)
        editor_column = QVBoxLayout()
        editor_column.setSpacing(round(4 * scale))
        editor_column.addWidget(self.meta)
        editor_column.addWidget(self.editor, 1)

        body = QHBoxLayout()
        body.setSpacing(round(16 * scale))
        body.addWidget(self.list_column)
        body.addLayout(editor_column, 1)

        layout = QVBoxLayout(self)
        inner = round(16 * scale)
        layout.setContentsMargins(self.margin + inner, self.margin + round(12 * scale), self.margin + inner,
                                  self.margin + inner)
        layout.setSpacing(round(10 * scale))
        layout.addLayout(header)
        layout.addLayout(body, 1)

        self._fill_list()
        if not self.notes:
            self._on_select(-1)

    def _t(self, ru, en):
        return ru if self.ru else en

    def _placeholder(self):
        return self._t("Пиши здесь… Картинку можно вставить через Ctrl+V или перетащить",
                       "Write here… Paste a picture with Ctrl+V or drop one in")

    def _item_data(self, note):
        images = note_images(note["text"])
        title = note_title(note["text"], self._t("Новая заметка", "New note"), self._t("Картинка", "Picture"))
        return title, note_preview(note["text"]), note_date(note.get("updated"), self.ru), (images or [None])[0]

    def _fill_list(self, select=0):
        self.list.blockSignals(True)
        self.list.clear()
        for note in self.notes:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, self._item_data(note))
            self.list.addItem(item)
        self.list.blockSignals(False)
        self._update_count()
        if self.notes:
            self.list.setCurrentRow(min(select, len(self.notes) - 1))
            self._on_select(self.list.currentRow())

    def _update_count(self):
        self.count.setText(str(len(self.notes)) if self.notes else "")
        self.list_stack.setCurrentWidget(self.list if self.notes else self.empty)
        self.delete_button.setEnabled(bool(self.notes))

    def _update_meta(self, note):
        stamp = note_date(note.get("updated"), self.ru)
        self.meta.setText(self._t("Изменено: ", "Edited: ") + stamp if stamp else "")

    def _on_select(self, row):
        self.editor.blockSignals(True)
        if 0 <= row < len(self.notes):
            self.editor.setEnabled(True)
            self.editor.setPlaceholderText(self._placeholder())
            self.editor.set_note_text(self.notes[row]["text"])
            self._update_meta(self.notes[row])
        else:
            self.editor.clear()
            self.editor.setEnabled(False)
            self.editor.setPlaceholderText(self._t("Нажми +, чтобы создать заметку", "Press + to create a note"))
            self.meta.setText("")
        self.editor.blockSignals(False)

    def _on_text_changed(self):
        row = self.list.currentRow()
        if not 0 <= row < len(self.notes):
            return
        note = self.notes[row]
        note["text"] = self.editor.note_text()
        note["updated"] = time.time()
        self.list.item(row).setData(Qt.UserRole, self._item_data(note))
        self._update_meta(note)
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

    def on_shown(self):
        self.editor.setFocus()

    def flush(self):
        if self.save_timer.isActive():
            self.save_timer.stop()
            self._save()

    def hideEvent(self, event):
        self.flush()
        super().hideEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        self.paint_card(p)
        # A hairline between the list and the editor.
        column = self.list_column.geometry()
        x = column.right() + 8 * self.scale
        p.setPen(QPen(QColor(255, 255, 255, 14), 1))
        p.drawLine(QPointF(x, column.top()), QPointF(x, column.bottom()))
