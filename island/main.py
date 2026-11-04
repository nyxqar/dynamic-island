import sys

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from config import load_config, tr
from ui.theme import set_family
from window import IslandWindow

# Settings changes arrive in bursts (sliders); the island is rebuilt once they stop.
REBUILD_DELAY_MS = 350


def make_tray_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor(255, 255, 255), 4))
    painter.setBrush(QColor(0, 0, 0))
    painter.drawRoundedRect(4, 18, 56, 28, 14, 14)
    painter.end()
    return QIcon(pixmap)


class App:
    def __init__(self, app):
        self.app = app
        self.config = load_config()
        self.media = self.lyrics = self.spectrum = None
        self._lyrics_key = self._spectrum_key = None
        self.window = None
        self.settings = None
        self.rebuild_timer = QTimer(singleShot=True, interval=REBUILD_DELAY_MS, timeout=self.rebuild)
        self.menu = QMenu()
        self.tray = QSystemTrayIcon(make_tray_icon(), app)
        self.tray.setToolTip("Dynamic Island")
        self.tray.setContextMenu(self.menu)
        self.rebuild()
        self.tray.show()
        app.aboutToQuit.connect(self.shutdown)

    def _update_providers(self):
        modules = self.config["modules"]
        if modules["media"] and self.media is None:
            from modules.media import MediaController

            self.media = MediaController()
        elif not modules["media"] and self.media is not None:
            self.media.stop()
            self.media = None

        key = (self.config["lyrics"]["env_file"],) if self.media and modules["lyrics"] else None
        if key != self._lyrics_key:
            self._lyrics_key = key
            self.lyrics = None
            if key:
                from modules.lyrics import LyricsProvider

                self.lyrics = LyricsProvider(self.config["lyrics"])

        key = (self.config["visualizer"]["process"],) if self.media and modules["visualizer"] else None
        if key != self._spectrum_key:
            self._spectrum_key = key
            if self.spectrum:
                self.spectrum.stop()
            self.spectrum = None
            if key:
                from modules.visualizer import AudioSpectrum

                self.spectrum = AudioSpectrum(self.config["visualizer"]["process"])

    def rebuild(self):
        set_family(self.config["font"])
        self._update_providers()
        old = self.window
        if old:
            if old.notes:
                old.notes.flush()
                old.notes.close()
            old.close()
            old.deleteLater()
        self.window = IslandWindow(self.config, self.media, self.lyrics, self.spectrum)
        self.window.settings_requested.connect(self.show_settings)
        if old and old.user_hidden:
            self.window.toggle_user_visibility()
        self._build_menu()

    def _build_menu(self):
        self.menu.clear()
        self.menu.addAction(tr(self.config, "notes"), lambda: self.window.toggle_notes())
        self.menu.addAction(tr(self.config, "settings"), self.show_settings)
        self.menu.addAction(tr(self.config, "toggle"), lambda: self.window.toggle_user_visibility())
        self.menu.addAction(tr(self.config, "quit"), self.app.quit)

    def show_settings(self):
        if self.settings is None:
            from modules.settings import SettingsWindow

            self.settings = SettingsWindow(self.config)
            self.settings.changed.connect(self._on_settings_changed)
            self.settings.action.connect(self._on_settings_action)
        w = self.window
        size = w.sizes[w._shown]
        anchor = QRect(round(w.shape.cx - size.width() / 2), round(w._inset()), size.width(), size.height())
        self.settings.show_near(anchor.translated(w.pos()), w.screen())

    def _on_settings_changed(self, rebuild):
        if rebuild:
            self.rebuild_timer.start()
        else:
            self.window.update()

    def _on_settings_action(self, name):
        if name == "center":
            self.window.center_on_screen()
        elif name == "reset":
            self.window.reset_position()

    def shutdown(self):
        if self.window and self.window.notes:
            self.window.notes.flush()
        if self.media:
            self.media.stop()
        if self.spectrum:
            self.spectrum.stop()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    _app = App(app)  # noqa: F841  keeps the tray and windows alive
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
