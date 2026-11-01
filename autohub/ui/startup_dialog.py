"""Loading dialog shown while AutoHub reads its settings and builds its modules."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from autohub.config import APP_NAME, APP_VERSION, LOGO_PATH
from autohub.ui.theme import set_muted


class StartupDialog(QWidget):
    """Frameless card with the logo, the current loading step and overall progress."""

    def __init__(self, total_steps: int):
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle(f"Starting {APP_NAME}")
        self.setFixedSize(420, 220)

        card = QFrame(self)
        card.setObjectName("startupCard")
        palette = self.palette()
        card.setStyleSheet(
            f"#startupCard {{ background-color: {palette.base().color().name()};"
            f" border: 1px solid {palette.mid().color().name()}; border-radius: 12px; }}"
        )

        logo = QLabel()
        if LOGO_PATH.exists():
            logo.setPixmap(QPixmap(str(LOGO_PATH)).scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        title = QLabel(APP_NAME)
        font = title.font()
        font.setPointSizeF(font.pointSizeF() * 1.7)
        font.setBold(True)
        title.setFont(font)
        version = QLabel(f"Version {APP_VERSION}")
        set_muted(version, True)
        heading = QVBoxLayout()
        heading.setSpacing(0)
        heading.addWidget(title)
        heading.addWidget(version)
        header = QHBoxLayout()
        header.setSpacing(14)
        header.addWidget(logo)
        header.addLayout(heading)
        header.addStretch(1)

        self._status = QLabel("Starting...")
        self._progress = QProgressBar()
        self._progress.setRange(0, total_steps)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(6)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.addLayout(header)
        layout.addStretch(1)
        layout.addWidget(self._status)
        layout.addSpacing(6)
        layout.addWidget(self._progress)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)

    @property
    def status(self) -> str:
        return self._status.text()

    @property
    def progress(self) -> int:
        return self._progress.value()

    def start(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is not None:
            self.move(screen.availableGeometry().center() - self.rect().center())
        self.show()
        self._repaint()

    def step(self, message: str) -> None:
        """Shows the step about to run; the bar fills as steps complete."""
        self._status.setText(message)
        self._repaint()

    def advance(self) -> None:
        self._progress.setValue(min(self._progress.value() + 1, self._progress.maximum()))
        self._repaint()

    def finish(self, window: QWidget) -> None:
        self._progress.setValue(self._progress.maximum())
        self._status.setText("Ready")
        self._repaint()
        window.show()
        window.raise_()
        window.activateWindow()
        self.close()

    def _repaint(self) -> None:
        if self.isVisible():
            self.repaint()
            QApplication.processEvents()
