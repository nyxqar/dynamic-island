import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from config import load_config, tr
from window import IslandWindow


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


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    config = load_config()
    modules = config["modules"]

    media = lyrics = spectrum = None
    if modules["media"]:
        from modules.media import MediaController

        media = MediaController()
        if modules["lyrics"]:
            from modules.lyrics import LyricsProvider

            lyrics = LyricsProvider(config["lyrics"])
        if modules["visualizer"]:
            from modules.visualizer import AudioSpectrum

            spectrum = AudioSpectrum()

    window = IslandWindow(config, media, lyrics, spectrum)

    menu = QMenu()
    menu.addAction(tr(config, "toggle"), window.toggle_user_visibility)
    menu.addAction(tr(config, "quit"), app.quit)
    tray = QSystemTrayIcon(make_tray_icon(), app)
    tray.setToolTip("Dynamic Island")
    tray.setContextMenu(menu)
    tray.show()

    def shutdown():
        if media:
            media.stop()
        if spectrum:
            spectrum.stop()

    app.aboutToQuit.connect(shutdown)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
