"""
Connect Dialog - Platform and target selection.

Allows users to:
- Select platform (Windows, Android, etc.)
- Browse and select target applications
- Configure connection settings
"""

from typing import Optional, List

try:
    from PyQt5.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
        QListWidget, QListWidgetItem, QPushButton, QGroupBox,
        QFormLayout, QLineEdit, QDialogButtonBox, QMessageBox,
        QStackedWidget, QWidget, QProgressBar, QTextEdit,
        QSplitter, QFrame, QApplication
    )
    from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, QObject
    from PyQt5.QtGui import QFont
    HAS_PYQT5 = True
except ImportError:
    HAS_PYQT5 = False

from ..plugins.platform_manager import (
    PlatformManager, PlatformType, PlatformConfig, TargetApplication
)


class TargetRefreshWorker(QObject):
    """Worker for refreshing target list in background."""
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, manager: PlatformManager, platform: PlatformType):
        super().__init__()
        self._manager = manager
        self._platform = platform

    def run(self):
        try:
            targets = self._manager.list_targets(self._platform)
            self.finished.emit(targets)
        except Exception as e:
            self.error.emit(str(e))


class ConnectDialog(QDialog):
    """
    Dialog for selecting platform and target application.
    """

    connected = pyqtSignal(PlatformConfig)  # Emitted when connected

    def __init__(self, parent=None):
        super().__init__(parent)
        self._manager = PlatformManager.get_instance()
        self._current_platform: Optional[PlatformType] = None
        self._targets: List[TargetApplication] = []
        self._selected_target: Optional[TargetApplication] = None

        self.setWindowTitle("Connect to Target")
        self.setMinimumSize(600, 500)
        self._setup_ui()
        self._load_platforms()

    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)

        # Platform selection
        platform_group = QGroupBox("Platform")
        platform_layout = QFormLayout(platform_group)

        self._platform_combo = QComboBox()
        self._platform_combo.currentIndexChanged.connect(self._on_platform_changed)
        platform_layout.addRow("Select Platform:", self._platform_combo)

        self._platform_desc = QLabel("")
        self._platform_desc.setWordWrap(True)
        self._platform_desc.setStyleSheet("color: gray; font-style: italic;")
        platform_layout.addRow("", self._platform_desc)

        layout.addWidget(platform_group)

        # Target selection
        target_group = QGroupBox("Target Application")
        target_layout = QVBoxLayout(target_group)

        # Refresh button and progress
        refresh_layout = QHBoxLayout()
        self._refresh_btn = QPushButton("Refresh List")
        self._refresh_btn.clicked.connect(self._refresh_targets)
        refresh_layout.addWidget(self._refresh_btn)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # Indeterminate
        self._progress.hide()
        refresh_layout.addWidget(self._progress)

        refresh_layout.addStretch()
        target_layout.addLayout(refresh_layout)

        # Target list
        self._target_list = QListWidget()
        self._target_list.itemSelectionChanged.connect(self._on_target_selected)
        self._target_list.itemDoubleClicked.connect(self._on_target_double_clicked)
        target_layout.addWidget(self._target_list)

        layout.addWidget(target_group)

        # Platform-specific settings (stacked widget)
        self._settings_stack = QStackedWidget()

        # Windows settings
        self._windows_settings = self._create_windows_settings()
        self._settings_stack.addWidget(self._windows_settings)

        # Android settings
        self._android_settings = self._create_android_settings()
        self._settings_stack.addWidget(self._android_settings)

        # Empty placeholder
        self._empty_settings = QWidget()
        self._settings_stack.addWidget(self._empty_settings)

        layout.addWidget(self._settings_stack)

        # Target info
        info_group = QGroupBox("Target Information")
        info_layout = QVBoxLayout(info_group)

        self._target_info = QTextEdit()
        self._target_info.setReadOnly(True)
        self._target_info.setMaximumHeight(100)
        self._target_info.setPlaceholderText("Select a target to view information...")
        info_layout.addWidget(self._target_info)

        layout.addWidget(info_group)

        # Buttons
        button_box = QDialogButtonBox()

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setEnabled(False)
        self._connect_btn.clicked.connect(self._on_connect)
        button_box.addButton(self._connect_btn, QDialogButtonBox.AcceptRole)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_box.addButton(cancel_btn, QDialogButtonBox.RejectRole)

        layout.addWidget(button_box)

    def _create_windows_settings(self) -> QWidget:
        """Create Windows-specific settings panel."""
        widget = QWidget()
        layout = QFormLayout(widget)

        # Capture mode
        self._win_capture_mode = QComboBox()
        self._win_capture_mode.addItems(["Window Only", "Include Title Bar", "Client Area Only"])
        layout.addRow("Capture Mode:", self._win_capture_mode)

        return widget

    def _create_android_settings(self) -> QWidget:
        """Create Android-specific settings panel."""
        widget = QWidget()
        layout = QFormLayout(widget)

        # Activity filter
        self._android_activity = QLineEdit()
        self._android_activity.setPlaceholderText("e.g., com.example.app/.MainActivity")
        layout.addRow("Activity Filter:", self._android_activity)

        # Device info button
        self._android_info_btn = QPushButton("Device Info")
        self._android_info_btn.clicked.connect(self._show_android_info)
        layout.addRow("", self._android_info_btn)

        return widget

    def _load_platforms(self):
        """Load available platforms."""
        self._platform_combo.clear()
        platforms = self._manager.get_available_platforms()

        if not platforms:
            self._platform_combo.addItem("No platforms available", None)
            self._platform_desc.setText("Please install platform handlers.")
            return

        for platform_type, name, description in platforms:
            self._platform_combo.addItem(name, platform_type)

        # Select first platform
        if platforms:
            self._platform_combo.setCurrentIndex(0)

    def _on_platform_changed(self, index: int):
        """Handle platform selection change."""
        platform_type = self._platform_combo.itemData(index)

        if platform_type is None:
            self._current_platform = None
            self._settings_stack.setCurrentWidget(self._empty_settings)
            return

        self._current_platform = platform_type

        # Update description
        platforms = self._manager.get_available_platforms()
        for pt, name, desc in platforms:
            if pt == platform_type:
                self._platform_desc.setText(desc)
                break

        # Switch settings panel
        if platform_type == PlatformType.WINDOWS:
            self._settings_stack.setCurrentWidget(self._windows_settings)
        elif platform_type == PlatformType.ANDROID:
            self._settings_stack.setCurrentWidget(self._android_settings)
        else:
            self._settings_stack.setCurrentWidget(self._empty_settings)

        # Refresh targets
        self._refresh_targets()

    def _refresh_targets(self):
        """Refresh target list for current platform."""
        if not self._current_platform:
            return

        self._target_list.clear()
        self._selected_target = None
        self._connect_btn.setEnabled(False)
        self._target_info.clear()

        self._progress.show()
        self._refresh_btn.setEnabled(False)

        # Run in timer to not block UI
        QTimer.singleShot(100, self._do_refresh_targets)

    def _do_refresh_targets(self):
        """Actually refresh targets."""
        try:
            self._targets = self._manager.list_targets(self._current_platform)

            self._target_list.clear()
            for target in self._targets:
                item = QListWidgetItem()
                item.setText(str(target))
                item.setData(Qt.UserRole, target)

                # Add tooltip with more info
                tooltip = f"ID: {target.id}\n"
                if target.process_name:
                    tooltip += f"Process: {target.process_name}\n"
                if target.bounds[2] > 0:
                    tooltip += f"Size: {target.bounds[2]}x{target.bounds[3]}"
                item.setToolTip(tooltip)

                self._target_list.addItem(item)

            if not self._targets:
                self._target_list.addItem("No targets found")

        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to list targets: {e}")

        finally:
            self._progress.hide()
            self._refresh_btn.setEnabled(True)

    def _on_target_selected(self):
        """Handle target selection."""
        items = self._target_list.selectedItems()
        if not items:
            self._selected_target = None
            self._connect_btn.setEnabled(False)
            self._target_info.clear()
            return

        target = items[0].data(Qt.UserRole)
        if not isinstance(target, TargetApplication):
            self._selected_target = None
            self._connect_btn.setEnabled(False)
            return

        self._selected_target = target
        self._connect_btn.setEnabled(True)

        # Show target info
        info_lines = [
            f"Title: {target.title}",
            f"ID: {target.id}",
        ]
        if target.process_name:
            info_lines.append(f"Process: {target.process_name}")
        if target.pid:
            info_lines.append(f"PID: {target.pid}")
        if target.bounds[2] > 0:
            info_lines.append(f"Position: ({target.bounds[0]}, {target.bounds[1]})")
            info_lines.append(f"Size: {target.bounds[2]} x {target.bounds[3]}")

        self._target_info.setText('\n'.join(info_lines))

    def _on_target_double_clicked(self, item: QListWidgetItem):
        """Handle double-click on target."""
        target = item.data(Qt.UserRole)
        if isinstance(target, TargetApplication):
            self._selected_target = target
            self._on_connect()

    def _on_connect(self):
        """Handle connect button click."""
        if not self._current_platform or not self._selected_target:
            return

        # Build config
        config = PlatformConfig(
            platform=self._current_platform,
            target=self._selected_target,
        )

        # Add platform-specific settings
        if self._current_platform == PlatformType.ANDROID:
            config.activity_name = self._android_activity.text().strip()

        # Show connecting status
        self._connect_btn.setEnabled(False)
        self._connect_btn.setText("Connecting...")
        self._progress.show()
        QApplication.processEvents()

        # Try to connect
        try:
            if self._manager.connect(config):
                self.connected.emit(config)
                self.accept()
            else:
                QMessageBox.warning(
                    self, "Connection Failed",
                    f"Failed to connect to: {self._selected_target.title}\n\n"
                    "The window may have been closed or is no longer available."
                )
        finally:
            self._connect_btn.setEnabled(True)
            self._connect_btn.setText("Connect")
            self._progress.hide()

    def _show_android_info(self):
        """Show detailed Android device info."""
        if not self._selected_target or self._current_platform != PlatformType.ANDROID:
            return

        handler = self._manager.get_handler(PlatformType.ANDROID)
        if not handler:
            return

        # Temporarily connect to get info
        config = PlatformConfig(
            platform=PlatformType.ANDROID,
            target=self._selected_target,
        )

        if handler.connect(config):
            try:
                info = handler.get_device_info()
                if info:
                    info_text = '\n'.join(f"{k}: {v}" for k, v in info.items())
                    QMessageBox.information(self, "Device Information", info_text)
                else:
                    QMessageBox.information(self, "Device Information", "No info available")
            finally:
                handler.disconnect()

    def get_config(self) -> Optional[PlatformConfig]:
        """Get the configured connection."""
        if self._manager.is_connected:
            return self._manager.current_config
        return None
