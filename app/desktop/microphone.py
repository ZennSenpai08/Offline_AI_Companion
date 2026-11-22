"""Microphone status and a small, replaceable transcription presentation surface."""
from dataclasses import replace
from queue import Queue, Empty
from threading import Thread

from PySide6.QtCore import QEvent, QTimer, Qt, Signal
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from app.audio.capture import input_devices


class MicrophonePanel(QWidget):
    toggle_requested = Signal()

    def __init__(self, overlay):
        super().__init__(overlay, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.overlay = overlay
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("Offline Companion — Microphone status")
        self.setObjectName("microphonePanel")
        self.setStyleSheet("#microphonePanel { background: #242d3c; border: 1px solid #8495b1; border-radius: 8px; } QLabel { color: #f3f5ff; } QPushButton { padding: 4px; }")
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.status = QLabel("Microphone Disabled")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        row.addWidget(self.status, 1)
        self.toggle = QPushButton("Enable")
        self.toggle.clicked.connect(lambda: self.toggle_requested.emit())
        row.addWidget(self.toggle)
        layout.addLayout(row)
        self.preview = QLabel()
        self.preview.setTextFormat(Qt.TextFormat.PlainText)
        self.preview.setWordWrap(True)
        self.preview.hide()
        layout.addWidget(self.preview)
        self.setFixedWidth(280)
        self._following = False
        self._top = None
        self._presented_text = ""
        self.expiry = QTimer(self)
        self.expiry.setSingleShot(True)
        self.expiry.timeout.connect(self.clear_preview)
        overlay.installEventFilter(self)
        overlay.settings_changed.connect(self.follow)

    def present(self, state, enabled, show_preview):
        self.status.setText(state["status"])
        self.setToolTip(state["detail"])
        self.toggle.setText("Disable" if enabled else "Enable")
        text = state["text"][:400] if show_preview else ""
        if text != self._presented_text:
            self._presented_text = text
            self.preview.setText(text)
            self.preview.setVisible(bool(text))
            if text:
                self.expiry.start(15000)
        self.adjustSize()
        self.follow()

    def clear_preview(self):
        self.preview.clear()
        self.preview.hide()
        self.adjustSize()
        self.follow()

    def follow(self):
        if self._following or not self.overlay.isVisible():
            return
        self._following = True
        try:
            top = self.overlay.settings.always_on_top
            if self._top != top:
                self._top = top
                self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, top)
            screen = QApplication.screenAt(self.overlay.frameGeometry().center()) or QApplication.primaryScreen()
            area = screen.availableGeometry()
            x = max(area.left(), min(self.overlay.x() + (self.overlay.width() - self.width()) // 2,
                                     area.right() - self.width() + 1))
            y = self.overlay.y() + self.overlay.height() + 4
            if y + self.height() > area.bottom() + 1:
                shift = y + self.height() - area.bottom() - 1
                self.overlay.move(self.overlay.x(), max(area.top(), self.overlay.y() - shift))
                y = min(self.overlay.y() + self.overlay.height() + 4, area.bottom() - self.height() + 1)
            self.move(x, max(area.top(), y))
            self.show()
        finally:
            self._following = False

    def eventFilter(self, watched, event):
        if watched is self.overlay:
            if event.type() in (QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.Show):
                self.follow()
            elif event.type() == QEvent.Type.Hide:
                self.hide()
        return False

    def closeEvent(self, event):
        self.expiry.stop()
        super().closeEvent(event)


class MicrophoneSettings(QDialog):
    def __init__(self, settings, parent):
        super().__init__(parent)
        self.original = settings
        self.setWindowTitle("Offline microphone settings")
        layout = QFormLayout(self)
        self.device = QComboBox()
        self.device.addItem("System default input", "")
        if settings.device:
            self.device.addItem(settings.device, settings.device)
            self.device.setCurrentIndex(1)
        layout.addRow("Input device", self.device)
        self.refresh = QPushButton("Refresh input list")
        self.refresh.clicked.connect(self.scan)
        layout.addRow(self.refresh)
        self.message = QLabel("Device enumeration does not record audio.")
        self.message.setWordWrap(True)
        layout.addRow(self.message)
        self.path = QLineEdit(settings.model_path)
        self.path.setPlaceholderText("Default: models/ggml-tiny-q5_1.bin")
        layout.addRow("Multilingual model", self.path)
        browse = QPushButton("Choose installed model…")
        browse.clicked.connect(self.browse)
        layout.addRow(browse)
        self.language = QComboBox()
        for label, code in (("Automatic (English / Tagalog / Taglish)", "auto"), ("English hint", "en"), ("Tagalog hint", "tl")):
            self.language.addItem(label, code)
        self.language.setCurrentIndex(self.language.findData(settings.language))
        layout.addRow("Language", self.language)
        self.sensitivity = QDoubleSpinBox()
        self.sensitivity.setRange(.25, 4)
        self.sensitivity.setSingleStep(.25)
        self.sensitivity.setValue(settings.sensitivity)
        layout.addRow("Sensitivity", self.sensitivity)
        self.mode = QSpinBox()
        self.mode.setRange(0, 3)
        self.mode.setValue(settings.vad_mode)
        layout.addRow("Noise rejection (0–3)", self.mode)
        self.silence = QSpinBox()
        self.silence.setRange(200, 2000)
        self.silence.setSingleStep(100)
        self.silence.setValue(settings.silence_ms)
        layout.addRow("Endpoint silence (ms)", self.silence)
        self.minimum = QSpinBox()
        self.minimum.setRange(100, 1000)
        self.minimum.setValue(settings.minimum_ms)
        layout.addRow("Minimum voiced time (ms)", self.minimum)
        self.maximum = QSpinBox()
        self.maximum.setRange(2, 25)
        self.maximum.setValue(settings.maximum_seconds)
        layout.addRow("Maximum segment (seconds)", self.maximum)
        self.preview = QCheckBox("Show local transcription preview")
        self.preview.setChecked(settings.preview)
        layout.addRow(self.preview)
        self.auto = QCheckBox("Listen automatically on future launches after consent")
        self.auto.setChecked(settings.auto_listen)
        layout.addRow(self.auto)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        self.scan_result = Queue(maxsize=1)
        self.poll = QTimer(self)
        self.poll.setInterval(100)
        self.poll.timeout.connect(self.scan_done)
        self.scan_thread = None
        self.finished.connect(lambda _code: self.poll.stop())

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Installed multilingual model", "", "whisper.cpp model (*.bin)")
        if path:
            self.path.setText(path)

    def scan(self):
        self.refresh.setEnabled(False)
        def query():
            try:
                self.scan_result.put(input_devices())
            except Exception as exc:
                self.scan_result.put(str(exc))
        self.scan_thread = Thread(target=query, daemon=True, name="input-device-list")
        self.scan_thread.start()
        self.poll.start()

    def scan_done(self):
        try:
            result = self.scan_result.get_nowait()
        except Empty:
            return
        self.poll.stop()
        self.refresh.setEnabled(True)
        if isinstance(result, str):
            self.message.setText("Cannot list inputs: " + result[:300])
            return
        selected = self.device.currentData()
        self.device.clear()
        self.device.addItem("System default input", "")
        for _index, name in result:
            self.device.addItem(name, name)
        if selected and self.device.findData(selected) < 0:
            self.device.addItem("Unavailable: " + selected, selected)
        self.device.setCurrentIndex(max(0, self.device.findData(selected)))
        self.message.setText(f"{len(result)} input entries; host APIs can list the same physical microphone more than once.")

    def value(self):
        return replace(self.original, device=self.device.currentData(), model_path=self.path.text().strip(),
                       language=self.language.currentData(), sensitivity=self.sensitivity.value(),
                       vad_mode=self.mode.value(), silence_ms=self.silence.value(),
                       minimum_ms=self.minimum.value(), maximum_seconds=self.maximum.value(),
                       preview=self.preview.isChecked(), auto_listen=self.auto.isChecked())
