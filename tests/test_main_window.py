from PySide6.QtCore import QSize

from autohub.ui.main_window import MainWindow

_BASE_WIDTH = 1024
_BASE_HEIGHT = 700
_UNCONSTRAINED_MAX = QSize(16777215, 16777215)


def test_main_window_starts_at_base_size_and_keeps_it_as_minimum(qapp):
    window = MainWindow([])
    try:
        window.show()
        qapp.processEvents()

        assert window.size().width() == _BASE_WIDTH
        assert window.size().height() == _BASE_HEIGHT
        assert window.minimumSize().width() == _BASE_WIDTH
        assert window.minimumSize().height() == _BASE_HEIGHT
        assert window.maximumSize() == _UNCONSTRAINED_MAX
    finally:
        window.close()


def test_main_window_can_grow_but_not_shrink_below_base_size(qapp):
    window = MainWindow([])
    try:
        window.show()
        qapp.processEvents()

        window.resize(1400, 900)
        qapp.processEvents()
        assert window.size().width() == 1400
        assert window.size().height() == 900

        window.resize(900, 500)
        qapp.processEvents()
        assert window.size().width() == _BASE_WIDTH
        assert window.size().height() == _BASE_HEIGHT
    finally:
        window.close()
