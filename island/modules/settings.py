from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QFontComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from config import save_config
from ui.card import CardWindow
from ui.theme import DEFAULT_FAMILIES, font
from ui.widgets import FIELD_STYLE, ColorButton, IconButton, Segmented, Swatch, Toggle, accent_of

ACCENTS = ["#ff4d6d", "#a0101e", "#ff8a3d", "#ffd166", "#3ddc97", "#4cc9f0", "#7b5cff", "#f15bb5"]

STYLE = "QWidget { color: white; background: transparent; }" + FIELD_STYLE + """
QPushButton#text {
    background: rgba(255,255,255,0.08); border: none; border-radius: 8px; padding: 6px 14px; font-weight: 600;
}
QPushButton#text:hover { background: rgba(255,255,255,0.16); }
QPushButton#text:pressed { background: rgba(255,255,255,0.22); }
"""


class NavButton(QAbstractButton):
    def __init__(self, scale, text):
        super().__init__()
        self.scale = scale
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedHeight(round(34 * scale))
        self._font = font(13 * scale, 600)

    def enterEvent(self, event):
        self.update()

    def leaveEvent(self, event):
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = self.scale
        r = QRectF(self.rect())
        if self.isChecked() or self.underMouse():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 24 if self.isChecked() else 10))
            p.drawRoundedRect(r, 9 * s, 9 * s)
        p.setFont(self._font)
        p.setPen(QColor(255, 255, 255, 240 if self.isChecked() else 150))
        p.drawText(r.adjusted(12 * s, 0, 0, 0), Qt.AlignLeft | Qt.AlignVCenter, self.text())


class Group(QWidget):
    """Rows on a faint rounded panel, separated by hairlines."""

    def __init__(self, scale):
        super().__init__()
        self.scale = scale
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(round(14 * scale), round(4 * scale), round(14 * scale), round(4 * scale))
        self.layout_.setSpacing(0)
        self.rows = []

    def add_row(self, label, control, hint=None):
        s = self.scale
        row = QWidget()
        row.setMinimumHeight(round(46 * s))
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, round(6 * s), 0, round(6 * s))
        text = QVBoxLayout()
        text.setSpacing(0)
        title = QLabel(label)
        title.setFont(font(13 * s, 500))
        text.addWidget(title)
        if hint:
            note = QLabel(hint)
            note.setFont(font(11 * s))
            note.setStyleSheet("color: rgba(255,255,255,0.42);")
            text.addWidget(note)
        layout.addLayout(text, 1)
        layout.addWidget(control, 0, Qt.AlignRight | Qt.AlignVCenter)
        self.layout_.addWidget(row)
        self.rows.append(row)
        return row

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = self.scale
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 9))
        p.drawRoundedRect(QRectF(self.rect()), 12 * s, 12 * s)
        p.setPen(QPen(QColor(255, 255, 255, 12), 1))
        for row in self.rows[1:]:
            y = row.geometry().top() + 0.5
            p.drawLine(QPointF(14 * s, y), QPointF(self.width() - 14 * s, y))


class SettingsWindow(CardWindow):
    # rebuild: True when the island has to be rebuilt; False when a repaint is enough.
    changed = Signal(bool)
    # "center" / "reset": position actions the island performs itself.
    action = Signal(str)

    def __init__(self, config):
        scale = config["scale"]
        super().__init__(scale, 680, 470)
        self.config = config
        self.ru = config["language"] == "ru"
        self.accent = accent_of(config)
        self.setWindowTitle(self._t("Настройки", "Settings"))
        self.setStyleSheet(STYLE % {"accent": self.accent.name()})
        self.setFont(font(13 * scale))
        s = scale

        title = QLabel(self._t("Настройки", "Settings"))
        title.setFont(font(18 * s, 600))
        close = IconButton("close", s, self._t("Закрыть", "Close"))
        close.clicked.connect(self.animated_hide)
        header = QHBoxLayout()
        header.addWidget(title)
        header.addStretch()
        header.addWidget(close)

        self.pages = QStackedWidget()
        nav = QVBoxLayout()
        nav.setSpacing(round(2 * s))
        group = QButtonGroup(self)
        builders = [
            (self._t("Вид", "Appearance"), self._page_look),
            (self._t("Цвета и фон", "Colours"), self._page_colors),
            (self._t("Модули", "Modules"), self._page_modules),
            (self._t("Плеер", "Player"), self._page_player),
            (self._t("Положение", "Position"), self._page_position),
        ]
        for i, (name, build) in enumerate(builders):
            button = NavButton(s, name)
            group.addButton(button, i)
            nav.addWidget(button)
            self.pages.addWidget(self._page(name, build()))
        nav.addStretch()
        hint = QLabel(self._t("Изменения применяются сразу", "Changes apply right away"))
        hint.setWordWrap(True)
        hint.setFont(font(11 * s))
        hint.setStyleSheet("color: rgba(255,255,255,0.35);")
        nav.addWidget(hint)
        group.idClicked.connect(self.pages.setCurrentIndex)
        group.button(0).setChecked(True)
        nav_widget = QWidget()
        nav_widget.setFixedWidth(round(150 * s))
        nav_widget.setLayout(nav)
        nav.setContentsMargins(0, 0, 0, 0)

        body = QHBoxLayout()
        body.setSpacing(round(18 * s))
        body.addWidget(nav_widget)
        body.addWidget(self.pages, 1)

        layout = QVBoxLayout(self)
        inner = round(16 * s)
        layout.setContentsMargins(self.margin + inner, self.margin + round(12 * s), self.margin + inner,
                                  self.margin + inner)
        layout.setSpacing(round(12 * s))
        layout.addLayout(header)
        layout.addLayout(body, 1)

    def _t(self, ru, en):
        return ru if self.ru else en

    def _page(self, name, groups):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(round(10 * self.scale))
        title = QLabel(name)
        title.setFont(font(15 * self.scale, 600))
        layout.addWidget(title)
        for group in groups:
            layout.addWidget(group)
        layout.addStretch()
        return page

    def _commit(self, rebuild=True):
        try:
            save_config(self.config)
        except OSError:
            pass
        self.changed.emit(rebuild)

    # --- Controls -----------------------------------------------------------------------------------------------

    def _toggle(self, section, key, rebuild=True):
        target = self.config[section] if key else self.config
        name = key or section
        toggle = Toggle(self.scale, self.accent, bool(target[name]))

        def changed(on):
            target[name] = on
            self._commit(rebuild)

        toggle.toggled.connect(changed)
        return toggle

    def _slider(self, low, high, value, step, fmt, on_change):
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(round(10 * self.scale))
        slider = QSlider(Qt.Horizontal)
        slider.setRange(low, high)
        slider.setSingleStep(step)
        slider.setPageStep(step * 2)
        slider.setValue(value)
        slider.setFixedWidth(round(170 * self.scale))
        slider.setCursor(Qt.PointingHandCursor)
        label = QLabel(fmt(value))
        label.setFont(font(12 * self.scale, 600, True))
        label.setFixedWidth(round(42 * self.scale))
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        def changed(v):
            v = round(v / step) * step
            label.setText(fmt(v))
            on_change(v)

        slider.valueChanged.connect(changed)
        layout.addWidget(slider)
        layout.addWidget(label)
        return box

    def _line_edit(self, value, placeholder, on_change, width=170):
        edit = QLineEdit(value)
        edit.setPlaceholderText(placeholder)
        edit.setFixedWidth(round(width * self.scale))
        edit.editingFinished.connect(lambda: on_change(edit.text().strip()))
        return edit

    # --- Pages --------------------------------------------------------------------------------------------------

    def _page_look(self):
        s = self.scale
        c = self.config
        group = Group(s)

        language = Segmented(s, [("ru", "Русский"), ("en", "English")], c["language"])

        def set_language(value):
            c["language"] = value
            self._commit()

        language.changed.connect(set_language)
        group.add_row(self._t("Язык", "Language"), language)

        fonts = QFontComboBox()
        fonts.setFixedWidth(round(200 * s))
        fonts.setCurrentFont(QFont(c["font"] or DEFAULT_FAMILIES[0]))

        def set_font(f):
            family = f.family()
            c["font"] = "" if family in DEFAULT_FAMILIES[:2] else family
            self._commit()

        fonts.currentFontChanged.connect(set_font)
        group.add_row(self._t("Шрифт", "Font"), fonts)

        def set_scale(v):
            c["scale"] = v / 100
            self._commit()

        group.add_row(self._t("Масштаб", "Scale"),
                      self._slider(70, 200, round(c["scale"] * 100), 5, lambda v: f"{v}%", set_scale))

        opacity = Group(s)

        def opacity_setter(key):
            def setter(v):
                c["opacity"][key] = v / 100
                self._commit(rebuild=False)
            return setter

        opacity.add_row(self._t("Прозрачность свёрнутого", "Collapsed opacity"),
                        self._slider(20, 100, round(c["opacity"]["collapsed"] * 100), 5, lambda v: f"{v}%",
                                     opacity_setter("collapsed")))
        opacity.add_row(self._t("Прозрачность раскрытого", "Expanded opacity"),
                        self._slider(20, 100, round(c["opacity"]["expanded"] * 100), 5, lambda v: f"{v}%",
                                     opacity_setter("expanded")),
                        self._t("Фон острова, текст остаётся чётким", "The background only; text stays solid"))
        return [group, opacity]

    def _page_colors(self):
        s = self.scale
        c = self.config
        accent = Group(s)
        swatches = QWidget()
        row = QHBoxLayout(swatches)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(round(2 * s))
        buttons = QButtonGroup(self)
        custom = ColorButton(s, c["accent"] if c["accent"] != "cover" else ACCENTS[0],
                             self._t("Цвет акцента", "Accent colour"))
        options = [None] + ACCENTS
        for color in options:
            swatch = Swatch(s, color, self._t("Из обложки", "From album art") if color is None else color)
            buttons.addButton(swatch)
            row.addWidget(swatch)
            current = c["accent"]
            swatch.setChecked(current == "cover" if color is None else color.lower() == current.lower())

            def picked(_checked=False, color=color):
                c["accent"] = "cover" if color is None else color
                if color:
                    custom.set_color(color)
                self._commit()

            swatch.clicked.connect(picked)
        row.addSpacing(round(6 * s))
        row.addWidget(custom)

        def custom_picked(color):
            for button in buttons.buttons():
                button.setChecked(False)
            c["accent"] = color
            self._commit()

        custom.changed.connect(custom_picked)
        accent.add_row(self._t("Акцент", "Accent"), swatches,
                       self._t("Прогресс, волна и подсветка", "Progress bar, wave and highlights"))

        background = Group(s)
        bg = c["background"]
        top = ColorButton(s, bg["top"], self._t("Верх фона", "Background top"))
        bottom = ColorButton(s, bg["bottom"], self._t("Низ фона", "Background bottom"))
        source = Segmented(s, [("spicetify", "Spicetify"), ("manual", self._t("Свой", "Custom"))], bg["source"])

        def update_enabled():
            manual = bg["source"] != "spicetify"
            top.setEnabled(manual)
            bottom.setEnabled(manual)

        def set_source(value):
            bg["source"] = value
            update_enabled()
            self._commit()

        source.changed.connect(set_source)
        update_enabled()
        background.add_row(self._t("Фон", "Background"), source,
                           self._t("Цвета активной темы Spicetify или свои", "Spicetify theme colours or your own"))

        def color_setter(key):
            def setter(color):
                bg[key] = color
                self._commit()
            return setter

        top.changed.connect(color_setter("top"))
        bottom.changed.connect(color_setter("bottom"))
        background.add_row(self._t("Цвет сверху", "Top colour"), top)
        background.add_row(self._t("Цвет снизу", "Bottom colour"), bottom)
        background.add_row(self._t("Звёзды", "Stars"), self._toggle("background", "stars"))
        background.add_row(self._t("Падающие звёзды", "Shooting stars"), self._toggle("background", "shooting_stars"))
        return [accent, background]

    def _page_modules(self):
        s = self.scale
        c = self.config
        group = Group(s)
        group.add_row(self._t("Часы", "Clock"), self._toggle("modules", "clock"))
        group.add_row(self._t("Плеер", "Player"), self._toggle("modules", "media"),
                      self._t("Трек, обложка и управление", "Track, artwork and controls"))
        group.add_row(self._t("Тексты песен", "Lyrics"), self._toggle("modules", "lyrics"))
        group.add_row(self._t("Волна-эквалайзер", "Equalizer wave"), self._toggle("modules", "visualizer"))
        group.add_row(self._t("Танцующий Клод", "Dancing Claude"), self._toggle("dancer", None))

        weather = Group(s)

        def set_city(city):
            if city != c["weather"]["city"]:
                c["weather"]["city"] = city
                self._commit()

        weather.add_row(self._t("Погода", "Weather"),
                        self._line_edit(c["weather"]["city"], self._t("Город", "City"), set_city),
                        self._t("Пусто — погода скрыта", "Empty hides the weather"))
        return [group, weather]

    def _page_player(self):
        s = self.scale
        c = self.config
        group = Group(s)

        def set_process(name):
            if name != c["visualizer"]["process"]:
                c["visualizer"]["process"] = name
                self._commit()

        group.add_row(self._t("Звук для волны", "Wave audio source"),
                      self._line_edit(c["visualizer"]["process"], self._t("Весь звук", "All audio"), set_process),
                      self._t("Программа, например Spotify.exe", "A program, e.g. Spotify.exe"))

        offset = QSpinBox()
        offset.setRange(-5000, 5000)
        offset.setSingleStep(50)
        offset.setSuffix(self._t(" мс", " ms"))
        offset.setValue(c["lyrics"]["offset_ms"])
        offset.setFixedWidth(round(110 * s))

        def set_offset():
            if offset.value() != c["lyrics"]["offset_ms"]:
                c["lyrics"]["offset_ms"] = offset.value()
                self._commit()

        offset.editingFinished.connect(set_offset)
        group.add_row(self._t("Сдвиг текста", "Lyrics offset"), offset,
                      self._t("Если строки спешат или опаздывают", "If lines run early or late"))

        clock = Group(s)

        def format_setter(key):
            def setter(value):
                value = value or ("HH:mm" if key == "time_format" else "dddd, d MMMM")
                if value != c["clock"][key]:
                    c["clock"][key] = value
                    self._commit()
            return setter

        clock.add_row(self._t("Формат времени", "Time format"),
                      self._line_edit(c["clock"]["time_format"], "HH:mm", format_setter("time_format"), 130))
        clock.add_row(self._t("Формат даты", "Date format"),
                      self._line_edit(c["clock"]["date_format"], "dddd, d MMMM", format_setter("date_format"), 130))
        return [group, clock]

    def _page_position(self):
        s = self.scale
        group = Group(s)
        group.add_row(self._t("Закрепить", "Lock position"), self._toggle("position", "locked", rebuild=False),
                      self._t("Остров нельзя будет перетащить", "The island can't be dragged"))
        for text, name in ((self._t("По центру экрана", "Center on screen"), "center"),
                           (self._t("Сбросить положение", "Reset position"), "reset")):
            button = QPushButton(self._t("Применить", "Apply"))
            button.setObjectName("text")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, name=name: self.action.emit(name))
            group.add_row(text, button)
        return [group]
