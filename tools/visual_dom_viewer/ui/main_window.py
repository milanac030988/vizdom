"""
Main Window for Visual DOM Viewer.

PyQt5-based application window with:
- Screenshot canvas with element highlighting
- Element tree view
- Property inspector panel
- Toolbar with actions
"""

import sys
from typing import Optional, List
from pathlib import Path

try:
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QSplitter, QTreeView, QTableWidget, QTableWidgetItem, QToolBar,
        QAction, QFileDialog, QLabel, QStatusBar, QMessageBox,
        QHeaderView, QAbstractItemView, QMenu, QLineEdit, QCheckBox,
        QPushButton, QGroupBox, QFormLayout, QListWidget, QListWidgetItem,
        QFrame, QTabWidget, QScrollArea, QProgressBar, QComboBox,
        QSizePolicy, QStyle, QToolButton
    )
    from PyQt5.QtCore import Qt, QAbstractItemModel, QModelIndex, pyqtSignal, QPoint, QSize
    from PyQt5.QtGui import (
        QPixmap, QPainter, QPen, QColor, QBrush, QImage,
        QStandardItemModel, QStandardItem, QIcon, QFont
    )
    HAS_PYQT5 = True
except ImportError:
    HAS_PYQT5 = False
    print("PyQt5 not available. Install with: pip install PyQt5")

from ..core.model import DOMViewerModel
from ..core.tree import DOMTree, DOMElement, ElementType
from ..core.state import ViewerMode, ViewerState
from ..core.element_definition import ElementDefinition
from ..export.robot_exporter import RobotResourceExporter
from ..plugins.platform_manager import PlatformManager, PlatformConfig


class ScreenshotCanvas(QWidget):
    """
    Canvas widget for displaying screenshot with element highlighting.

    Features:
    - Display screenshot image
    - Draw element bounding boxes
    - Handle mouse events for selection
    - Zoom and pan support
    """

    element_clicked = pyqtSignal(str)  # element_id
    element_hovered = pyqtSignal(str)  # element_id
    point_clicked = pyqtSignal(int, int)  # x, y

    # Colors for different states
    HOVER_COLOR = QColor(255, 0, 0, 180)      # Red, semi-transparent
    SELECT_COLOR = QColor(0, 120, 255, 200)   # Blue
    MULTI_SELECT_COLOR = QColor(0, 200, 0, 180)  # Green

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self._model = DOMViewerModel.get_instance()
        self._pixmap: Optional[QPixmap] = None
        self._scale = 1.0
        self._offset_x = 0
        self._offset_y = 0

        # Connect to model events
        self._model.add_listener('screenshot_loaded', self._on_screenshot_loaded)
        self._model.add_listener('selection_changed', self._on_selection_changed)
        self._model.add_listener('hover_changed', self._on_hover_changed)
        self._model.add_listener('view_changed', self._on_view_changed)

    def _on_screenshot_loaded(self, path):
        """Handle screenshot loaded event."""
        self.load_image(str(path))

    def _on_selection_changed(self, element):
        """Handle selection changed event."""
        self.update()

    def _on_hover_changed(self, element):
        """Handle hover changed event."""
        self.update()

    def _on_view_changed(self, view_state):
        """Handle view changed event."""
        self._scale = view_state.scale
        self._offset_x = view_state.offset_x
        self._offset_y = view_state.offset_y
        self.update()

    def load_image(self, path: str) -> bool:
        """Load image from file."""
        try:
            self._pixmap = QPixmap(path)
            self.update()
            return True
        except Exception as e:
            print(f"Error loading image: {e}")
            return False

    def load_image_data(self, data: bytes) -> bool:
        """Load image from bytes data."""
        try:
            image = QImage()
            image.loadFromData(data)
            self._pixmap = QPixmap.fromImage(image)
            self.update()
            return True
        except Exception as e:
            print(f"Error loading image data: {e}")
            return False

    def paintEvent(self, event):
        """Paint the canvas with screenshot and highlights."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Fill background
        painter.fillRect(self.rect(), QColor(50, 50, 50))

        if self._pixmap:
            # Calculate scaled size
            scaled_width = int(self._pixmap.width() * self._scale)
            scaled_height = int(self._pixmap.height() * self._scale)

            # Draw scaled pixmap
            target_rect = self._pixmap.rect()
            target_rect.setWidth(scaled_width)
            target_rect.setHeight(scaled_height)
            target_rect.translate(int(self._offset_x), int(self._offset_y))

            painter.drawPixmap(target_rect, self._pixmap)

            # Draw element highlights
            self._draw_highlights(painter)

    def _draw_highlights(self, painter: QPainter):
        """Draw element highlighting rectangles."""
        state = self._model.state

        # Draw hovered element (dashed line)
        if state.selection.hovered_id and self._model.is_explore_mode:
            element = self._model.dom_tree.get_element_by_id(state.selection.hovered_id) if self._model.dom_tree else None
            if element and element.bbox:
                self._draw_element_rect(painter, element, self.HOVER_COLOR, Qt.DashLine, 2)

        # Draw multi-selected elements
        for elem_id in state.selection.multi_selected_ids:
            element = self._model.dom_tree.get_element_by_id(elem_id) if self._model.dom_tree else None
            if element and element.bbox:
                self._draw_element_rect(painter, element, self.MULTI_SELECT_COLOR, Qt.SolidLine, 2)

        # Draw selected element (solid line)
        if state.selection.selected_id:
            element = self._model.dom_tree.get_element_by_id(state.selection.selected_id) if self._model.dom_tree else None
            if element and element.bbox:
                self._draw_element_rect(painter, element, self.SELECT_COLOR, Qt.SolidLine, 3)

    def _draw_element_rect(self, painter: QPainter, element: DOMElement,
                           color: QColor, style: Qt.PenStyle, width: int):
        """Draw rectangle for an element."""
        if not element.bbox:
            return

        # Convert element coordinates to screen coordinates
        x = int(element.bbox.x * self._scale + self._offset_x)
        y = int(element.bbox.y * self._scale + self._offset_y)
        w = int(element.bbox.width * self._scale)
        h = int(element.bbox.height * self._scale)

        pen = QPen(color, width, style)
        painter.setPen(pen)
        painter.drawRect(x, y, w, h)

        # Draw label
        label = f"{element.type.value}"
        if element.text:
            label += f": {element.text[:15]}..."

        # Background for label
        font_metrics = painter.fontMetrics()
        label_rect = font_metrics.boundingRect(label)
        label_rect.translate(x, y - label_rect.height() - 2)

        painter.fillRect(label_rect.adjusted(-2, -2, 2, 2), QColor(0, 0, 0, 180))
        painter.setPen(Qt.white)
        painter.drawText(label_rect, Qt.AlignLeft, label)

    def mouseMoveEvent(self, event):
        """Handle mouse move for hover highlighting."""
        if self._model.is_explore_mode:
            # Convert screen to content coordinates
            content_x = int((event.x() - self._offset_x) / self._scale)
            content_y = int((event.y() - self._offset_y) / self._scale)

            element = self._model.hover_element_at_point(content_x, content_y)
            if element:
                self.element_hovered.emit(element.id)

    def mousePressEvent(self, event):
        """Handle mouse click for selection."""
        if event.button() == Qt.LeftButton:
            # Convert screen to content coordinates
            content_x = int((event.x() - self._offset_x) / self._scale)
            content_y = int((event.y() - self._offset_y) / self._scale)

            self.point_clicked.emit(content_x, content_y)

            # Toggle explore mode or select element
            if self._model.is_explore_mode:
                element = self._model.select_element_at_point(content_x, content_y)
                if element:
                    self.element_clicked.emit(element.id)
            else:
                self._model.set_explore_mode(True)

    def wheelEvent(self, event):
        """Handle mouse wheel for zoom."""
        delta = event.angleDelta().y()
        if delta > 0:
            self._model.zoom_in()
        else:
            self._model.zoom_out()


class ElementTreeModel(QStandardItemModel):
    """
    Qt Item Model for DOM tree display.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHorizontalHeaderLabels(['Element', 'Type', 'Text'])

    def load_dom_tree(self, dom_tree: DOMTree):
        """Load DOM tree into model."""
        self.clear()
        self.setHorizontalHeaderLabels(['Element', 'Type', 'Text'])

        if dom_tree and dom_tree.root:
            root_item = self._create_tree_item(dom_tree.root)
            self.appendRow(root_item)

    def _create_tree_item(self, element: DOMElement) -> List[QStandardItem]:
        """Create tree item for element."""
        # Create items for each column
        name_item = QStandardItem(element.id)
        name_item.setData(element.id, Qt.UserRole)  # Store ID for lookup

        type_item = QStandardItem(element.type.value)
        text_item = QStandardItem(element.text[:30] if element.text else "")

        # Set icon based on type
        # (Would need actual icons in production)

        # Add children recursively
        for child in element.children:
            child_items = self._create_tree_item(child)
            name_item.appendRow(child_items)

        return [name_item, type_item, text_item]


class PropertyTable(QTableWidget):
    """
    Table widget for displaying element properties with checkboxes for selection.
    """

    property_toggled = pyqtSignal(str, bool)  # property_name, is_selected

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(3)
        self.setHorizontalHeaderLabels(['Use', 'Property', 'Value'])
        self.horizontalHeader().setStretchLastSection(True)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setColumnWidth(0, 40)  # Checkbox column

        self._current_element: Optional[DOMElement] = None
        self._property_checkboxes: dict = {}

    def show_element(self, element: Optional[DOMElement], selected_props: set = None):
        """Display properties for an element with checkboxes."""
        self.setRowCount(0)
        self._property_checkboxes.clear()
        self._current_element = element

        if not element:
            return

        selected_props = selected_props or set()

        properties = [
            ('text', 'Text', element.text),
            ('type', 'Type', element.type.value),
            ('id', 'ID', element.id),
            ('confidence', 'Confidence', f"{element.confidence:.2f}"),
        ]

        if element.bbox:
            properties.extend([
                ('x', 'X', str(element.bbox.x)),
                ('y', 'Y', str(element.bbox.y)),
                ('width', 'Width', str(element.bbox.width)),
                ('height', 'Height', str(element.bbox.height)),
                ('center', 'Center', f"({element.bbox.center[0]}, {element.bbox.center[1]})"),
                ('bbox', 'BBox', f"[{element.bbox.x},{element.bbox.y},{element.bbox.width},{element.bbox.height}]"),
            ])

        # Add custom properties
        for key, value in element.properties.items():
            properties.append((key, key.title(), str(value)))

        # Populate table
        self.setRowCount(len(properties))
        for row, (prop_key, prop_label, value) in enumerate(properties):
            # Checkbox for selection
            checkbox = QCheckBox()
            checkbox.setChecked(prop_key in selected_props)
            checkbox.stateChanged.connect(
                lambda state, pk=prop_key: self._on_checkbox_changed(pk, state)
            )
            self._property_checkboxes[prop_key] = checkbox

            checkbox_widget = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_widget)
            checkbox_layout.addWidget(checkbox)
            checkbox_layout.setAlignment(Qt.AlignCenter)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            self.setCellWidget(row, 0, checkbox_widget)

            self.setItem(row, 1, QTableWidgetItem(prop_label))
            self.setItem(row, 2, QTableWidgetItem(value or ""))

    def _on_checkbox_changed(self, prop_key: str, state: int):
        """Handle checkbox state change."""
        is_checked = state == Qt.Checked
        self.property_toggled.emit(prop_key, is_checked)

    def get_selected_properties(self) -> set:
        """Get set of selected property keys."""
        selected = set()
        for prop_key, checkbox in self._property_checkboxes.items():
            if checkbox.isChecked():
                selected.add(prop_key)
        return selected

    def set_selected_properties(self, props: set):
        """Set which properties are selected."""
        for prop_key, checkbox in self._property_checkboxes.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(prop_key in props)
            checkbox.blockSignals(False)


class ElementDefinitionPanel(QWidget):
    """
    Panel for defining an element with custom name and selected properties.
    """

    element_defined = pyqtSignal(str, str, list)  # element_id, name, selected_properties

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_element: Optional[DOMElement] = None
        self._model = DOMViewerModel.get_instance()
        self._setup_ui()

    def _setup_ui(self):
        """Setup the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Element info header
        self._element_label = QLabel("No element selected")
        self._element_label.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(self._element_label)

        # Name input
        name_group = QGroupBox("Element Name")
        name_layout = QFormLayout(name_group)
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("e.g., Button_Number_4")
        name_layout.addRow("Name:", self._name_input)

        # Auto-generate name button
        self._auto_name_btn = QPushButton("Auto")
        self._auto_name_btn.setMaximumWidth(50)
        self._auto_name_btn.clicked.connect(self._auto_generate_name)
        name_layout.addRow("", self._auto_name_btn)

        layout.addWidget(name_group)

        # Description input
        self._description_input = QLineEdit()
        self._description_input.setPlaceholderText("Optional description...")
        layout.addWidget(QLabel("Description:"))
        layout.addWidget(self._description_input)

        # Buttons
        button_layout = QHBoxLayout()

        self._add_btn = QPushButton("Add to Export List")
        self._add_btn.setEnabled(False)
        self._add_btn.clicked.connect(self._on_add_clicked)
        button_layout.addWidget(self._add_btn)

        self._update_btn = QPushButton("Update")
        self._update_btn.setEnabled(False)
        self._update_btn.clicked.connect(self._on_update_clicked)
        button_layout.addWidget(self._update_btn)

        self._remove_btn = QPushButton("Remove")
        self._remove_btn.setEnabled(False)
        self._remove_btn.clicked.connect(self._on_remove_clicked)
        button_layout.addWidget(self._remove_btn)

        layout.addLayout(button_layout)

        # Spacer
        layout.addStretch()

    def set_element(self, element: Optional[DOMElement], selected_props: set = None):
        """Set the current element to define."""
        self._current_element = element

        if element:
            self._element_label.setText(f"{element.type.value}: {element.text[:30] if element.text else element.id}")
            self._add_btn.setEnabled(True)

            # Check if already defined
            definition = self._model.get_definition(element.id)
            if definition:
                self._name_input.setText(definition.name)
                self._description_input.setText(definition.description)
                self._update_btn.setEnabled(True)
                self._remove_btn.setEnabled(True)
                self._add_btn.setText("Already Defined")
                self._add_btn.setEnabled(False)
            else:
                self._name_input.clear()
                self._description_input.clear()
                self._update_btn.setEnabled(False)
                self._remove_btn.setEnabled(False)
                self._add_btn.setText("Add to Export List")
                self._add_btn.setEnabled(True)
                # Auto-suggest a name
                self._auto_generate_name()
        else:
            self._element_label.setText("No element selected")
            self._name_input.clear()
            self._description_input.clear()
            self._add_btn.setEnabled(False)
            self._update_btn.setEnabled(False)
            self._remove_btn.setEnabled(False)

    def _auto_generate_name(self):
        """Auto-generate a name based on element properties."""
        if not self._current_element:
            return

        elem = self._current_element
        type_name = elem.type.value.upper()

        if elem.text:
            # Clean text for variable name
            text_clean = ''.join(c if c.isalnum() else '_' for c in elem.text[:20])
            text_clean = '_'.join(filter(None, text_clean.split('_')))
            name = f"{type_name}_{text_clean}"
        else:
            name = f"{type_name}_{elem.id.replace('E', '')}"

        self._name_input.setText(name.upper())

    def _on_add_clicked(self):
        """Handle add button click."""
        if not self._current_element:
            return

        name = self._name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Please enter a name for the element")
            return

        self.element_defined.emit(
            self._current_element.id,
            name,
            []  # Will be filled by parent with property table selection
        )

        # Update UI state
        self._add_btn.setText("Already Defined")
        self._add_btn.setEnabled(False)
        self._update_btn.setEnabled(True)
        self._remove_btn.setEnabled(True)

    def _on_update_clicked(self):
        """Handle update button click."""
        if not self._current_element:
            return

        name = self._name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Please enter a name for the element")
            return

        self.element_defined.emit(
            self._current_element.id,
            name,
            []  # Will be filled by parent
        )

    def _on_remove_clicked(self):
        """Handle remove button click."""
        if not self._current_element:
            return

        self._model.remove_definition(self._current_element.id)

        # Update UI state
        self._add_btn.setText("Add to Export List")
        self._add_btn.setEnabled(True)
        self._update_btn.setEnabled(False)
        self._remove_btn.setEnabled(False)
        self._name_input.clear()

    def get_name(self) -> str:
        """Get the entered name."""
        return self._name_input.text().strip()

    def get_description(self) -> str:
        """Get the entered description."""
        return self._description_input.text().strip()


class DefinedElementsList(QWidget):
    """
    List widget showing all defined elements for export.
    """

    element_selected = pyqtSignal(str)  # element_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = DOMViewerModel.get_instance()
        self._setup_ui()

        # Listen for definition changes
        self._model.add_listener('definition_changed', self._on_definitions_changed)

    def _setup_ui(self):
        """Setup the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Header
        header_layout = QHBoxLayout()
        header_label = QLabel("Defined Elements")
        header_label.setStyleSheet("font-weight: bold;")
        header_layout.addWidget(header_label)

        self._count_label = QLabel("(0)")
        header_layout.addWidget(self._count_label)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # List widget
        self._list_widget = QListWidget()
        self._list_widget.itemClicked.connect(self._on_item_clicked)
        self._list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list_widget)

        # Buttons
        button_layout = QHBoxLayout()

        clear_btn = QPushButton("Clear All")
        clear_btn.clicked.connect(self._on_clear_all)
        button_layout.addWidget(clear_btn)

        save_btn = QPushButton("Save...")
        save_btn.clicked.connect(self._on_save)
        button_layout.addWidget(save_btn)

        load_btn = QPushButton("Load...")
        load_btn.clicked.connect(self._on_load)
        button_layout.addWidget(load_btn)

        layout.addLayout(button_layout)

    def _on_definitions_changed(self, definition):
        """Handle definition changes."""
        self.refresh()

    def refresh(self):
        """Refresh the list from model."""
        self._list_widget.clear()

        definitions = self._model.get_all_definitions()
        self._count_label.setText(f"({len(definitions)})")

        for defn in definitions:
            item = QListWidgetItem()
            item.setText(f"{defn.name} ({defn.element_id})")
            item.setData(Qt.UserRole, defn.element_id)

            # Show selected properties in tooltip
            props = ', '.join(defn.selected_properties)
            item.setToolTip(f"Properties: {props}")

            self._list_widget.addItem(item)

    def _on_item_clicked(self, item: QListWidgetItem):
        """Handle item click."""
        element_id = item.data(Qt.UserRole)
        self.element_selected.emit(element_id)

    def _on_item_double_clicked(self, item: QListWidgetItem):
        """Handle item double-click to select in tree/canvas."""
        element_id = item.data(Qt.UserRole)
        self._model.select_element(element_id)

    def _on_clear_all(self):
        """Clear all definitions."""
        reply = QMessageBox.question(
            self, "Clear All",
            "Are you sure you want to clear all element definitions?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._model.definition_manager.clear()
            self.refresh()

    def _on_save(self):
        """Save definitions to file."""
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Element Definitions",
            "element_definitions.json", "JSON Files (*.json)"
        )
        if filepath:
            if self._model.save_definitions(filepath):
                QMessageBox.information(self, "Save", f"Saved to {filepath}")
            else:
                QMessageBox.warning(self, "Save", "Failed to save definitions")

    def _on_load(self):
        """Load definitions from file."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Load Element Definitions",
            "", "JSON Files (*.json)"
        )
        if filepath:
            if self._model.load_definitions(filepath):
                self.refresh()
                QMessageBox.information(self, "Load", f"Loaded from {filepath}")
            else:
                QMessageBox.warning(self, "Load", "Failed to load definitions")


class VisualDOMViewerWindow(QMainWindow):
    """
    Main application window for Visual DOM Viewer.
    """

    def __init__(self):
        if not HAS_PYQT5:
            raise ImportError("PyQt5 is required for the UI. Install with: pip install PyQt5")

        super().__init__()
        self.setWindowTitle("Visual DOM Viewer - Not Connected")
        self.setGeometry(100, 100, 1400, 900)

        # Set here as well as on the QApplication: the window keeps its identity
        # when it is constructed by something other than run_viewer() (a test, an
        # embedding host), and the child dialogs inherit it from the window.
        from .branding import app_icon
        self.setWindowIcon(app_icon())

        self._model = DOMViewerModel.get_instance()
        self._exporter = RobotResourceExporter()
        self._platform_manager = PlatformManager.get_instance()

        self._setup_ui()
        self._setup_toolbar()
        self._setup_statusbar()
        self._connect_signals()

        # Listen for platform events
        self._platform_manager.add_listener(self._on_platform_event)

    def _setup_ui(self):
        """Setup the main UI layout."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)

        # Create splitter for resizable panels
        splitter = QSplitter(Qt.Horizontal)

        # Left panel: Screenshot canvas
        self._canvas = ScreenshotCanvas()
        splitter.addWidget(self._canvas)

        # Middle panel: Tree view
        self._tree_view = QTreeView()
        self._tree_model = ElementTreeModel()
        self._tree_view.setModel(self._tree_model)
        self._tree_view.setHeaderHidden(False)
        self._tree_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        splitter.addWidget(self._tree_view)

        # Right panel: Properties and Definition
        right_splitter = QSplitter(Qt.Vertical)

        # Property table with checkboxes
        self._property_table = PropertyTable()
        right_splitter.addWidget(self._property_table)

        # Element definition panel
        self._definition_panel = ElementDefinitionPanel()
        right_splitter.addWidget(self._definition_panel)

        # Defined elements list
        self._defined_list = DefinedElementsList()
        right_splitter.addWidget(self._defined_list)

        right_splitter.setSizes([250, 150, 200])
        splitter.addWidget(right_splitter)

        splitter.setSizes([600, 350, 350])
        main_layout.addWidget(splitter)

    # ======================================================================
    # Menus and toolbar
    #
    # The toolbar used to carry 26 widgets in a single row: every pipeline knob
    # next to every verb, so the primary actions were hard to pick out. It now
    # carries VERBS only; the knobs live in Tools > Pipeline Settings, which
    # hosts the very same widget objects (see settings_dialog.py), so there is
    # still exactly one source of truth per setting.
    # ======================================================================

    def _pipeline_widgets(self) -> dict:
        """The live pipeline controls, keyed for PipelineSettingsDialog."""
        return {
            "capture_source": self._capture_source_combo,
            "capture_arg": self._capture_arg_edit,
            "camera_mode": self._camera_mode_checkbox,
            "detector": self._detector_combo,
            "grpc_target": self._grpc_target_edit,
            "merge": self._merge_checkbox,
            "ocr": self._ocr_combo,
            "text_ensemble": self._text_ensemble_checkbox,
            "slm": self._slm_checkbox,
            "slm_model": self._slm_model_combo,
        }

    def _create_pipeline_controls(self):
        """
        Create the pipeline controls, unparented until a dialog claims them.

        They keep their original member names because ~57 call sites read them
        directly (`self._detector_combo.currentText()` and friends); only their
        placement changes. Labels are now full sentences rather than the
        toolbar's cryptic abbreviations ("Det:", "Text+"), which a form has room
        for.
        """
        # ---- capture source (ADR-018) ----------------------------------
        self._capture_source_combo = QComboBox()
        # "window (handler)" = the existing platform-handler path (needs Connect).
        # Everything else is a pluggable CaptureStrategy: grab directly.
        self._capture_source_combo.addItem("window (handler)")
        try:
            from visual_dom.adapters.outbound.capture import list_captures
            for c in list_captures():
                label = c["name"] if c["available"] else f"{c['name']} (n/a)"
                self._capture_source_combo.addItem(label, c["name"])
        except Exception as e:
            print(f"[Viewer] capture strategy discovery failed: {e}")
        self._capture_source_combo.setToolTip(
            "Capture source (ADR-018):\n"
            "window (handler) = capture the connected target window (needs Connect)\n"
            "windows/linux = full-screen grab\n"
            "android = adb device (set arg = serial)\n"
            "camera = capture card / webcam (set arg = device index or URL)\n"
            "grpc = remote capture service (set arg = host:port)\n"
            "<plugin> = your custom strategy from plugins/capture/"
        )
        self._capture_source_combo.currentIndexChanged.connect(self._on_capture_source_changed)

        self._capture_arg_edit = QLineEdit("")
        self._capture_arg_edit.setToolTip(
            "Argument for the capture source:\n"
            "grpc -> host:port   camera -> device index or URL   android -> serial"
        )
        self._capture_arg_edit.setPlaceholderText("host:port / device / serial")

        self._camera_mode_checkbox = QCheckBox("Camera mode (rectify a photographed screen)")
        self._camera_mode_checkbox.setToolTip(
            "Camera mode: auto-detect and rectify the screen region\n"
            "in photos taken of a monitor/display"
        )

        # ---- detection (ADR-015 / ADR-017) -----------------------------
        self._detector_combo = QComboBox()
        self._detector_combo.addItems(["uied", "yolo", "hybrid", "omniparser", "grpc"])
        self._detector_combo.setToolTip(
            "Element detector:\n"
            "uied = traditional CV (no model needed)\n"
            "yolo = YOLOv8 model (needs .pt file)\n"
            "hybrid = YOLO + UIED merged\n"
            "omniparser = Microsoft OmniParser (needs repo+weights; set OMNIPARSER_* env vars)\n"
            "grpc = remote detector service (set the target host:port field)"
        )

        self._grpc_target_edit = QLineEdit("localhost:50051")
        self._grpc_target_edit.setToolTip(
            "Remote detector service host:port (for detector = grpc).\n"
            "Start one from Tools > Services."
        )
        self._grpc_target_edit.setPlaceholderText("host:port")

        self._merge_checkbox = QCheckBox("Smart-merge over-segmented elements")
        self._merge_checkbox.setChecked(True)
        self._merge_checkbox.setToolTip(
            "Smart-merge over-segmented elements:\n"
            "ON  = merge fragment boxes that form one element (multi-line button, split text line)\n"
            "OFF = keep raw detections"
        )

        # ---- text (ADR-012 / ADR-016) ----------------------------------
        self._ocr_combo = QComboBox()
        self._ocr_combo.addItems([
            "easyocr",      # Best text region detection, weaker on custom fonts
            "tesseract",    # Better for system/custom fonts, needs install
            "paddleocr",    # Fast, good for multi-language
        ])
        self._ocr_combo.setToolTip(
            "OCR engine for text detection:\n"
            "easyocr = best text regions; tesseract = better on system fonts;\n"
            "paddleocr = fast, multi-language"
        )

        self._text_ensemble_checkbox = QCheckBox("Text ensemble (OmniParser only)")
        self._text_ensemble_checkbox.setChecked(True)
        self._text_ensemble_checkbox.setToolTip(
            "Text ensemble (OmniParser only):\n"
            "ON  = feed our upscaling OCR into OmniParser (recovers missed text)\n"
            "OFF = OmniParser's original OCR only"
        )

        # ---- refinement (ADR-009) --------------------------------------
        self._slm_checkbox = QCheckBox("Enable small-model review (requires Ollama)")
        self._slm_checkbox.setToolTip("Use a language model to improve detection (requires Ollama)")

        self._slm_model_combo = QComboBox()
        self._slm_model_combo.addItems([
            "qwen2.5:3b",       # Text-only (fast, retype only)
            "minicpm-v",        # VLM (best for UI, ~5.5GB)
            "qwen2.5-vl:3b",   # VLM (small, ~2.4GB)
            "llava:7b",         # VLM (general purpose)
        ])
        self._slm_model_combo.setToolTip("SLM model (vision models can see the screenshot)")

    def _icon(self, standard_name: str) -> QIcon:
        """A themed icon from Qt's standard set - no asset files to ship."""
        return self.style().standardIcon(getattr(QStyle, standard_name))

    def _setup_toolbar(self):
        """Build the menu bar (discoverability) and a slim toolbar of verbs."""
        self._create_pipeline_controls()

        # ---------- actions, shared between the menus and the toolbar ----
        self._connect_action = QAction(self._icon("SP_ComputerIcon"), "&Connect...", self)
        self._connect_action.setShortcut("Ctrl+N")
        self._connect_action.setStatusTip("Choose a target window or device to inspect")
        self._connect_action.triggered.connect(self._show_connect_dialog)

        self._disconnect_action = QAction("&Disconnect", self)
        self._disconnect_action.setEnabled(False)
        self._disconnect_action.setStatusTip("Release the current target")
        self._disconnect_action.triggered.connect(self._disconnect)

        self._capture_action = QAction(self._icon("SP_MediaPlay"), "&Capture && Analyze", self)
        self._capture_action.setShortcut("F5")
        self._capture_action.setEnabled(False)
        self._capture_action.setStatusTip(
            "Grab the screen and build the Visual DOM with the current pipeline settings")
        self._capture_action.triggered.connect(self._capture_and_analyze)

        self._refresh_action = QAction(self._icon("SP_BrowserReload"), "Re-&Analyze", self)
        self._refresh_action.setShortcut("F6")
        self._refresh_action.setEnabled(False)
        self._refresh_action.setStatusTip(
            "Re-run the pipeline on the current screenshot (after changing settings)")
        self._refresh_action.triggered.connect(self._analyze_current_screenshot)

        open_action = QAction(self._icon("SP_DialogOpenButton"), "&Open Image...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.setStatusTip("Load an image onto the canvas without analysing it")
        open_action.triggered.connect(self._open_screenshot)

        analyze_image_action = QAction("Analyze &Image...", self)
        analyze_image_action.setShortcut("Ctrl+Shift+O")
        analyze_image_action.setStatusTip(
            "Open an image file and analyze it with the current pipeline settings "
            "(detector / OCR / SLM), no device connection needed")
        analyze_image_action.triggered.connect(self._open_and_analyze_image)

        open_dom_action = QAction(self._icon("SP_FileDialogContentsView"),
                                  "Open &DOM JSON...", self)
        open_dom_action.setShortcut("Ctrl+D")
        open_dom_action.setStatusTip(
            "Re-open a Visual DOM saved earlier (output/sessions/<id>/dom.json) "
            "to re-check an analysed result without capturing again")
        open_dom_action.triggered.connect(self._open_dom_json)

        export_action = QAction(self._icon("SP_DialogSaveButton"), "&Export to Robot...", self)
        export_action.setShortcut("Ctrl+E")
        export_action.setStatusTip("Write the defined elements as a Robot Framework resource")
        export_action.triggered.connect(self._export_to_robot)

        quit_action = QAction("E&xit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)

        self._explore_action = QAction("&Explore Mode", self)
        self._explore_action.setCheckable(True)
        self._explore_action.setChecked(True)
        self._explore_action.setStatusTip("Hover the canvas to highlight elements")
        self._explore_action.triggered.connect(self._toggle_explore_mode)

        zoom_in_action = QAction(self._icon("SP_ArrowUp"), "Zoom &In", self)
        zoom_in_action.setShortcut("Ctrl++")
        zoom_in_action.triggered.connect(self._model.zoom_in)

        zoom_out_action = QAction(self._icon("SP_ArrowDown"), "Zoom &Out", self)
        zoom_out_action.setShortcut("Ctrl+-")
        zoom_out_action.triggered.connect(self._model.zoom_out)

        settings_action = QAction(self._icon("SP_FileDialogDetailedView"),
                                  "&Pipeline Settings...", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.setStatusTip("Capture source, detector, OCR engine, refinement")
        settings_action.triggered.connect(self._show_pipeline_settings)

        config_action = QAction("Session &Configuration...", self)
        config_action.setStatusTip(
            "Edit the vizdom.config.json shared with the CLI and Robot Framework")
        config_action.triggered.connect(self._show_config_dialog)

        services_action = QAction("&Services...", self)
        services_action.setStatusTip(
            "Start, stop and monitor the detector / capture / actuator services")
        services_action.triggered.connect(self._show_services_dialog)

        about_action = QAction("&About VizDOM", self)
        about_action.triggered.connect(self._show_about)

        # ---------- menu bar --------------------------------------------
        bar = self.menuBar()

        file_menu = bar.addMenu("&File")
        file_menu.addAction(open_action)
        file_menu.addAction(analyze_image_action)
        file_menu.addAction(open_dom_action)
        file_menu.addSeparator()
        file_menu.addAction(export_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

        capture_menu = bar.addMenu("&Capture")
        capture_menu.addAction(self._connect_action)
        capture_menu.addAction(self._disconnect_action)
        capture_menu.addSeparator()
        capture_menu.addAction(self._capture_action)
        capture_menu.addAction(self._refresh_action)

        view_menu = bar.addMenu("&View")
        view_menu.addAction(self._explore_action)
        view_menu.addSeparator()
        view_menu.addAction(zoom_in_action)
        view_menu.addAction(zoom_out_action)

        tools_menu = bar.addMenu("&Tools")
        tools_menu.addAction(settings_action)
        tools_menu.addAction(config_action)
        tools_menu.addSeparator()
        tools_menu.addAction(services_action)

        help_menu = bar.addMenu("&Help")
        help_menu.addAction(about_action)

        # ---------- toolbar: verbs only ---------------------------------
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        toolbar.setIconSize(QSize(18, 18))
        self.addToolBar(toolbar)

        toolbar.addAction(self._connect_action)
        toolbar.addAction(self._capture_action)
        toolbar.addAction(self._refresh_action)
        toolbar.addSeparator()

        # Re-checking an earlier result is a first-class workflow - open a saved
        # image or a saved DOM instead of capturing again - so all three openers
        # stay one click away. They share a split button rather than three
        # buttons: same reachability, one toolbar slot.
        open_button = QToolButton()
        open_button.setPopupMode(QToolButton.MenuButtonPopup)
        open_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        open_menu = QMenu(open_button)
        open_menu.addAction(open_action)
        open_menu.addAction(analyze_image_action)
        open_menu.addAction(open_dom_action)
        open_button.setMenu(open_menu)
        open_button.setDefaultAction(open_action)   # click = Open Image, arrow = the rest
        toolbar.addWidget(open_button)
        self._open_button = open_button

        toolbar.addAction(export_action)
        toolbar.addSeparator()
        toolbar.addAction(settings_action)

        # Right-hand side: what the pipeline is set to right now. The toolbar
        # no longer shows the controls, so it has to show their effect -
        # otherwise a mis-set detector is invisible until the results look wrong.
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        self._pipeline_summary = QPushButton()
        self._pipeline_summary.setFlat(True)
        self._pipeline_summary.setCursor(Qt.PointingHandCursor)
        self._pipeline_summary.setToolTip("Active pipeline - click to change (Ctrl+,)")
        self._pipeline_summary.clicked.connect(self._show_pipeline_settings)
        toolbar.addWidget(self._pipeline_summary)

        for widget, signal in (
            (self._capture_source_combo, "currentIndexChanged"),
            (self._detector_combo, "currentIndexChanged"),
            (self._ocr_combo, "currentIndexChanged"),
            (self._slm_checkbox, "toggled"),
            (self._camera_mode_checkbox, "toggled"),
        ):
            getattr(widget, signal).connect(self._update_pipeline_summary)
        self._update_pipeline_summary()

    def _update_pipeline_summary(self, *_):
        """One line describing the active pipeline, shown at the toolbar's right."""
        source = (self._capture_source_combo.currentData()
                  or self._capture_source_combo.currentText())
        parts = [str(source), self._detector_combo.currentText(), self._ocr_combo.currentText()]
        if self._slm_checkbox.isChecked():
            parts.append("SLM")
        if self._camera_mode_checkbox.isChecked():
            parts.append("camera")
        self._pipeline_summary.setText("  |  ".join(parts) + "   [settings]")

    # ---------------- child windows ------------------------------------

    def _show_pipeline_settings(self):
        """Tools > Pipeline Settings: the controls that used to crowd the toolbar."""
        if getattr(self, "_settings_dialog", None) is None:
            from .settings_dialog import PipelineSettingsDialog
            self._settings_dialog = PipelineSettingsDialog(self, self._pipeline_widgets())
        self._raise(self._settings_dialog)

    def _show_config_dialog(self):
        """Tools > Session Configuration: edit vizdom.config.json (ADR-020)."""
        if getattr(self, "_config_dialog", None) is None:
            from .config_dialog import ConfigDialog
            default = Path.cwd() / "vizdom.config.json"
            self._config_dialog = ConfigDialog(
                self, path=str(default) if default.exists() else None)
            self._config_dialog.on_apply(self._apply_config_dict)
        self._raise(self._config_dialog)

    def _show_services_dialog(self):
        """Tools > Services: run the detector / capture / actuator servers."""
        if getattr(self, "_services_dialog", None) is None:
            from .services_dialog import ServicesDialog
            self._services_dialog = ServicesDialog(self, repo_root=self._repo_root())
        self._raise(self._services_dialog)

    @staticmethod
    def _raise(dialog):
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    @staticmethod
    def _repo_root() -> Path:
        """
        Repository root, so the services dialog can set PYTHONPATH=<root>/src.

        Derived from this file's location (tools/visual_dom_viewer/ui/) rather
        than the working directory, which is wherever the user launched from.
        """
        return Path(__file__).resolve().parents[3]

    def _apply_config_dict(self, data: dict):
        """
        Push a session config onto the pipeline controls.

        Only the fields the Viewer itself drives are mapped; the rest of the
        file still takes effect when that config is handed to the CLI or a test
        suite, which is the point of editing it here.
        """
        detector = data.get("detector") or {}
        ocr = data.get("ocr") or {}
        capture = data.get("capture") or {}
        refiner = data.get("refiner") or {}

        if detector.get("backend"):
            self._detector_combo.setCurrentText(detector["backend"])
        if detector.get("grpc_target"):
            self._grpc_target_edit.setText(detector["grpc_target"])
        if "omniparser_text_ensemble" in detector:
            self._text_ensemble_checkbox.setChecked(bool(detector["omniparser_text_ensemble"]))
        if ocr.get("engine"):
            self._ocr_combo.setCurrentText(ocr["engine"])
        if "camera_mode" in capture:
            self._camera_mode_checkbox.setChecked(bool(capture["camera_mode"]))
        if "enabled" in refiner:
            self._slm_checkbox.setChecked(bool(refiner["enabled"]))
        if refiner.get("model"):
            self._slm_model_combo.setCurrentText(refiner["model"])

        if capture.get("strategy"):
            index = self._capture_source_combo.findData(capture["strategy"])
            if index >= 0:
                self._capture_source_combo.setCurrentIndex(index)
            if capture.get("target"):
                self._capture_arg_edit.setText(str(capture["target"]))

        self._update_pipeline_summary()
        self._statusbar.showMessage("Session configuration applied", 5000)

    def _show_about(self):
        QMessageBox.about(
            self, "About VizDOM Viewer",
            "<b>VizDOM Viewer</b><br>"
            "Inspect a screenshot as a Visual DOM, define elements and export "
            "them as a Robot Framework resource.<br><br>"
            "Pipeline knobs live in <b>Tools &gt; Pipeline Settings</b>; the "
            "shared session config in <b>Tools &gt; Session Configuration</b>; "
            "the gRPC services in <b>Tools &gt; Services</b>."
        )

    def closeEvent(self, event):
        """Never leave services the Viewer started running after it exits."""
        dialog = getattr(self, "_services_dialog", None)
        if dialog is not None:
            try:
                dialog.shutdown()
            except Exception as exc:        # shutdown must not block the exit
                print(f"[Viewer] service shutdown: {exc}")
        super().closeEvent(event)


    def _setup_statusbar(self):
        """Setup the status bar with progress indicator."""
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)

        # Connection status label
        self._connection_label = QLabel("Not Connected")
        self._connection_label.setStyleSheet("color: gray; padding: 0 10px;")
        self._statusbar.addPermanentWidget(self._connection_label)

        # Progress bar (hidden by default)
        self._progress_bar = QProgressBar()
        self._progress_bar.setMaximumWidth(200)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.hide()
        self._statusbar.addPermanentWidget(self._progress_bar)

        self._statusbar.showMessage("Ready - Click 'Connect' to select a target application")

    def _connect_signals(self):
        """Connect signals between components."""
        # Canvas signals
        self._canvas.element_clicked.connect(self._on_element_clicked)
        self._canvas.element_hovered.connect(self._on_element_hovered)

        # Tree view signals
        self._tree_view.selectionModel().selectionChanged.connect(
            self._on_tree_selection_changed
        )

        # Definition panel signals
        self._definition_panel.element_defined.connect(self._on_element_defined)

        # Defined elements list signals
        self._defined_list.element_selected.connect(self._on_defined_element_selected)

        # Model events
        self._model.add_listener('dom_loaded', self._on_dom_loaded)
        self._model.add_listener('selection_changed', self._on_selection_changed)
        self._model.add_listener('state_changed', self._on_state_changed)

    def _on_dom_loaded(self, dom_tree: DOMTree):
        """Handle DOM tree loaded."""
        self._tree_model.load_dom_tree(dom_tree)
        self._tree_view.expandAll()
        self._statusbar.showMessage(f"Loaded {dom_tree.get_element_count()} elements")

    def _on_element_clicked(self, element_id: str):
        """Handle element clicked on canvas."""
        # Sync tree view selection
        self._select_tree_item(element_id)

    def _on_element_hovered(self, element_id: str):
        """Handle element hovered on canvas."""
        pass  # Could update status bar

    def _on_tree_selection_changed(self, selected, deselected):
        """
        Handle tree view selection change.

        The tree is ExtendedSelection (Ctrl/Shift multi-select), so push ALL
        selected ids to the model: the canvas highlights every one, and the last
        becomes the primary selection for the property panel. selectedIndexes()
        yields one index per (row, column), so de-duplicate by row.
        """
        seen, element_ids = set(), []
        for index in self._tree_view.selectedIndexes():
            key = (index.row(), index.parent())
            if key in seen:
                continue
            seen.add(key)
            item = self._tree_model.itemFromIndex(index)
            if not item:
                continue
            element_id = item.data(Qt.UserRole)
            if element_id and element_id not in element_ids:
                element_ids.append(element_id)

        if element_ids:
            self._model.select_elements(element_ids)
            if len(element_ids) > 1:
                self._statusbar.showMessage(f"{len(element_ids)} elements selected")
        else:
            self._model.clear_selection()

    def _on_selection_changed(self, element: Optional[DOMElement]):
        """Handle selection changed in model."""
        # Get existing definition if any
        selected_props = set()
        if element:
            definition = self._model.get_definition(element.id)
            if definition:
                selected_props = definition.selected_properties

        self._property_table.show_element(element, selected_props)
        self._definition_panel.set_element(element, selected_props)

        if element:
            self._statusbar.showMessage(f"Selected: {element.type.value} - {element.text[:30] if element.text else element.id}")

    def _on_element_defined(self, element_id: str, name: str, _):
        """Handle element definition from panel."""
        # Get the element
        if not self._model.dom_tree:
            return

        element = self._model.dom_tree.get_element_by_id(element_id)
        if not element:
            return

        # Get selected properties from property table
        selected_props = list(self._property_table.get_selected_properties())

        if not selected_props:
            # Default to text and type if nothing selected
            selected_props = ['text', 'type']
            QMessageBox.information(
                self, "Info",
                "No properties selected. Using 'text' and 'type' as default locators."
            )

        # Define the element
        self._model.define_element(element, name, selected_props)
        self._statusbar.showMessage(f"Defined: {name} with properties: {', '.join(selected_props)}")

    def _on_defined_element_selected(self, element_id: str):
        """Handle selection from defined elements list."""
        # Select the element in the model
        self._model.select_element(element_id)
        # Sync tree view
        self._select_tree_item(element_id)

    def _on_state_changed(self, state):
        """Handle state changed in model."""
        self._explore_action.setChecked(state.mode == ViewerMode.EXPLORE)

    def _select_tree_item(self, element_id: str):
        """Select item in tree view by element ID."""
        # Search for item with matching ID
        def find_item(parent_index, target_id):
            for row in range(self._tree_model.rowCount(parent_index)):
                index = self._tree_model.index(row, 0, parent_index)
                item = self._tree_model.itemFromIndex(index)
                if item and item.data(Qt.UserRole) == target_id:
                    return index
                # Search children
                child_result = find_item(index, target_id)
                if child_result:
                    return child_result
            return None

        index = find_item(QModelIndex(), element_id)
        if index:
            self._tree_view.setCurrentIndex(index)
            self._tree_view.scrollTo(index)

    def _open_screenshot(self):
        """Open screenshot file dialog."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Open Screenshot",
            "", "Images (*.png *.jpg *.jpeg *.bmp);;All Files (*)"
        )
        if filepath:
            self._model.load_screenshot(filepath)
            self._canvas.load_image(filepath)

    def _open_and_analyze_image(self):
        """Open an image file and run the Visual DOM pipeline on it (offline).

        Reuses the same analysis path as capture: the image is loaded, re-encoded
        to PNG bytes, shown on the canvas, and passed to _do_analyze_screenshot,
        which honours the current toolbar settings (detector / OCR / SLM / camera).
        No device connection is required.
        """
        import os
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Open Image to Analyze",
            "", "Images (*.png *.jpg *.jpeg *.bmp);;All Files (*)"
        )
        if not filepath:
            return

        # Session provenance: offline analysis of a file — no live window.
        self._capture_context = {
            "capture_source": f"file:{os.path.basename(filepath)}",
            "source_path": filepath,
            "window_title": None,
            "process_name": None,
        }

        try:
            import cv2
            img = cv2.imread(filepath)
            if img is None:
                QMessageBox.warning(self, "Open Failed",
                                    f"Could not read image:\n{filepath}")
                return
            ok, buf = cv2.imencode(".png", img)
            if not ok:
                QMessageBox.warning(self, "Open Failed", "Could not encode the image.")
                return
            screenshot = buf.tobytes()
        except Exception as e:
            QMessageBox.warning(self, "Open Failed", f"Error loading image: {e}")
            return

        h, w = img.shape[:2]
        self._show_progress(f"Loaded {os.path.basename(filepath)} ({w}x{h}); analyzing...", 40)
        self._model.set_screenshot_data(screenshot)
        self._canvas.load_image_data(screenshot)
        self._refresh_action.setEnabled(True)
        self._do_analyze_screenshot(screenshot)

    def _open_dom_json(self):
        """
        Re-open a saved Visual DOM, together with the screenshot it describes.

        A session directory holds `dom_result.json` next to `screenshot.png`, so
        picking the DOM alone used to draw last session's boxes over whatever
        image happened to be on the canvas. Pair them here: re-checking a result
        is one file dialog, not two, and the boxes are always over their own
        screenshot.
        """
        sessions = self._repo_root() / "output" / "sessions"
        start_dir = str(sessions if sessions.is_dir() else Path.cwd())
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Open DOM JSON", start_dir, "JSON Files (*.json);;All Files (*)"
        )
        if not filepath:
            return
        if not self._model.load_dom_from_file(filepath):
            return

        shot = self._sibling_screenshot(Path(filepath))
        if shot is not None and self._model.load_screenshot(str(shot)):
            self._canvas.load_image(str(shot))       # same path as Open Image
            self._statusbar.showMessage(
                f"Loaded {Path(filepath).name} with {shot.name}", 6000)
            return
        self._statusbar.showMessage(
            f"Loaded {Path(filepath).name} - no screenshot beside it; "
            f"open one with Ctrl+O to see the boxes in place", 8000)

    @staticmethod
    def _sibling_screenshot(dom_path: Path):
        """The screenshot in the DOM's own directory, if there is exactly one."""
        folder = dom_path.parent
        preferred = folder / "screenshot.png"
        if preferred.is_file():
            return preferred
        images = sorted(p for p in folder.glob("*")
                        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp"))
        return images[0] if len(images) == 1 else None

    def _show_connect_dialog(self):
        """Show the connect dialog to select platform and target."""
        from .connect_dialog import ConnectDialog

        dialog = ConnectDialog(self)
        dialog.connected.connect(self._on_connected)
        dialog.exec_()

    def _on_connected(self, config: PlatformConfig):
        """Handle successful connection."""
        target_name = config.target.title if config.target else "Unknown"
        self.setWindowTitle(f"Visual DOM Viewer - {target_name}")

        # Update status
        self._connection_label.setText(f"Connected: {target_name[:30]}")
        self._connection_label.setStyleSheet("color: green; font-weight: bold; padding: 0 10px;")
        self._statusbar.showMessage(f"Connected! Press F5 or click 'Capture & Analyze' to capture the target window.")

        # Update UI state
        self._connect_action.setEnabled(False)
        self._disconnect_action.setEnabled(True)
        self._capture_action.setEnabled(True)

    def _disconnect(self):
        """Disconnect from current target."""
        self._platform_manager.disconnect()
        self.setWindowTitle("Visual DOM Viewer - Not Connected")

        # Update status
        self._connection_label.setText("Not Connected")
        self._connection_label.setStyleSheet("color: gray; padding: 0 10px;")
        self._statusbar.showMessage("Disconnected - Click 'Connect' to select a new target")

        # Update UI state
        self._connect_action.setEnabled(True)
        self._disconnect_action.setEnabled(False)
        self._capture_action.setEnabled(False)
        self._refresh_action.setEnabled(False)

    def _show_progress(self, message: str, value: int = -1):
        """Show progress in status bar. value=-1 for indeterminate."""
        self._progress_bar.show()
        if value < 0:
            self._progress_bar.setRange(0, 0)  # Indeterminate
        else:
            self._progress_bar.setRange(0, 100)
            self._progress_bar.setValue(value)
        self._statusbar.showMessage(message)
        QApplication.processEvents()

    def _hide_progress(self):
        """Hide progress bar."""
        self._progress_bar.hide()
        self._progress_bar.setRange(0, 100)

    def _selected_capture_strategy(self):
        """Return (strategy_name, kwargs) for the toolbar selection, or (None, {})
        when the default window-handler path is selected."""
        idx = self._capture_source_combo.currentIndex()
        if idx <= 0:  # "window (handler)"
            return None, {}
        name = self._capture_source_combo.itemData(idx)
        arg = self._capture_arg_edit.text().strip()
        kwargs = {}
        if arg:
            if name == "grpc":
                kwargs["target"] = arg
            elif name == "camera":
                # numeric device index if it looks like one, else a stream URL
                kwargs["device"] = int(arg) if arg.isdigit() else arg
            elif name == "android":
                kwargs["serial"] = arg
        return name, kwargs

    def _on_capture_source_changed(self, _idx):
        """Enable Capture & Analyze for strategy sources (no Connect needed);
        for the window handler, fall back to the connection state."""
        name, _ = self._selected_capture_strategy()
        if name is None:
            self._capture_action.setEnabled(self._platform_manager.is_connected)
        else:
            self._capture_action.setEnabled(True)

    def _connected_target_title(self):
        """Title of the window connected via the platform handler, if any."""
        try:
            if not self._platform_manager.is_connected:
                return None
            cfg = self._platform_manager.current_config
            tgt = getattr(cfg, "target", None) if cfg else None
            title = getattr(tgt, "title", None)
            return title or None
        except Exception:
            return None

    def _capture_via_strategy(self, name, kwargs):
        """
        Grab one frame via a CaptureStrategy and return PNG bytes.

        When a target window is connected, ask the strategy to capture **only that
        window** (ADR-021). This is what makes "Connect to Calculator" meaningful on
        the strategy path — including via the gRPC capture service, where the crop
        is performed on the machine that owns the screen. If the strategy cannot do
        it, fall back to raising the window and grabbing the full screen, so the app
        is at least visible in the frame.

        Also records session provenance by asking the strategy itself
        (`describe_target()`, ADR-018): each strategy knows how to identify its
        own target — Win32/X11 window title, the Android resumed activity, a
        camera device, a remote endpoint — so this stays platform-agnostic here.
        """
        import cv2
        from visual_dom.adapters.outbound.capture import create_capture
        cap = create_capture(name, **kwargs)
        title = self._connected_target_title()
        try:
            try:
                target = cap.describe_target() or {}
            except Exception:
                target = {}
            self._capture_context = dict(target)
            self._capture_context["capture_source"] = f"strategy:{name}"

            captured = None
            if title:
                try:
                    captured = cap.capture_window(title)
                except Exception as e:
                    print(f"[Viewer] Window capture failed ({e}); using full screen")
                    captured = None
                if captured is None:
                    print(f"[Viewer] '{name}' cannot capture window {title!r} alone; "
                          f"raising it and capturing the full screen instead")
                    try:
                        cap.focus_target(title)
                    except Exception:
                        pass

            if captured is not None:
                frame = captured.image
                # Geometry is provenance AND the key to mapping DOM coordinates
                # back to the screen (a second monitor may start at a negative x).
                self._capture_context.update({
                    "capture_scope": "window",
                    "window_title": captured.window_title or title,
                    "capture_origin": list(captured.origin),
                    "device_origin": list(captured.device_origin),
                    "device_size": list(captured.device_size),
                })
                print(f"[Viewer] Captured window {captured.window_title!r}: "
                      f"{frame.shape[1]}x{frame.shape[0]} at origin {captured.origin}")
            else:
                frame = cap.capture()
                self._capture_context["capture_scope"] = "screen"
        finally:
            try:
                cap.close()
            except Exception:
                pass
        ok, buf = cv2.imencode(".png", frame)
        if not ok:
            raise RuntimeError("could not encode captured frame")
        return buf.tobytes()

    def _capture_and_analyze(self):
        """Capture screenshot and analyze with Visual DOM pipeline."""
        strategy_name, strategy_kwargs = self._selected_capture_strategy()

        # Pluggable capture strategy (ADR-018): grab directly, no window handler.
        if strategy_name is not None:
            try:
                self._show_progress(f"Capturing via '{strategy_name}'...", 30)
                QApplication.processEvents()
                screenshot = self._capture_via_strategy(strategy_name, strategy_kwargs)
            except Exception as e:
                self._hide_progress()
                QMessageBox.warning(self, "Capture Failed",
                                    f"Capture via '{strategy_name}' failed: {e}")
                return
            self._show_progress("Loading screenshot...", 50)
            self._model.set_screenshot_data(screenshot)
            self._canvas.load_image_data(screenshot)
            self._refresh_action.setEnabled(True)
            self._show_progress("Analyzing with Visual DOM...", 70)
            self._do_analyze_screenshot(screenshot)
            return

        # Default path: capture the connected target window via the platform handler.
        if not self._platform_manager.is_connected:
            QMessageBox.warning(self, "Not Connected", "Please connect to a target first.")
            return

        # Session provenance: the handler knows its connected target precisely.
        try:
            cfg = self._platform_manager.current_config
            tgt = getattr(cfg, "target", None) if cfg else None
            self._capture_context = {
                "capture_source": f"window-handler:{getattr(cfg, 'platform', '?')}" if cfg else "window-handler",
                "window_title": getattr(tgt, "title", None),
                "process_name": getattr(tgt, "process_name", None),
            }
        except Exception:
            self._capture_context = {"capture_source": "window-handler"}

        try:
            import time

            # Step 1: Minimize viewer window FIRST to not interfere
            self._show_progress("Step 1/3: Preparing capture...", 10)
            QApplication.processEvents()

            # Hide the viewer window completely
            self.hide()
            QApplication.processEvents()
            time.sleep(0.3)  # Wait for viewer to hide

            # Step 2: Bring target window to front
            self._show_progress("Step 2/3: Capturing screenshot...", 30)
            handler = self._platform_manager.current_handler

            # Retry, but stop as soon as the raise is CONFIRMED: bring_to_front
            # now verifies the foreground window (ADR-021) instead of reporting
            # success whenever it did not throw.
            for _ in range(3):
                if handler and hasattr(handler, 'bring_to_front'):
                    if handler.bring_to_front():
                        QApplication.processEvents()
                        break
                    time.sleep(0.3)  # not there yet - let the WM settle and retry
                QApplication.processEvents()

            # Additional delay to ensure window is fully rendered
            time.sleep(0.5)

            # Capture screenshot
            screenshot = self._platform_manager.capture_screenshot()

            # Restore viewer window
            self.show()
            self.activateWindow()
            self.raise_()
            QApplication.processEvents()

            if not screenshot:
                self._hide_progress()
                QMessageBox.warning(self, "Capture Failed", "Failed to capture screenshot from target window.")
                return

            # Display screenshot
            self._show_progress("Step 2/3: Loading screenshot...", 50)
            self._model.set_screenshot_data(screenshot)
            self._canvas.load_image_data(screenshot)
            self._refresh_action.setEnabled(True)

            # Step 3: Analyze with Visual DOM
            self._show_progress("Step 3/3: Analyzing with Visual DOM...", 70)
            self._do_analyze_screenshot(screenshot)

        except Exception as e:
            # Make sure to restore window on error
            self.show()
            self.activateWindow()
            self.raise_()
            self._hide_progress()
            QMessageBox.warning(self, "Error", f"Error during capture: {e}")

    def _analyze_current_screenshot(self):
        """Analyze current screenshot with Visual DOM pipeline."""
        screenshot = self._model.get_screenshot_data()
        if not screenshot:
            QMessageBox.warning(self, "No Screenshot", "Please capture a screenshot first.")
            return

        self._show_progress("Re-analyzing screenshot...", -1)
        self._do_analyze_screenshot(screenshot)

    def _do_analyze_screenshot(self, screenshot: bytes):
        """Internal method to analyze screenshot."""
        try:
            import tempfile
            import os
            import sys
            import json as _json
            from datetime import datetime

            # Fail fast on a missing OCR engine - the same ADR-020 probe that
            # guards connect(). Without it the Viewer once ran a whole session
            # with paddleocr configured but absent: the pipeline degraded to
            # 0 text boxes and nothing said why (session 20260806_195229).
            # Probed here, before a session directory exists and before the
            # heavy models load.
            try:
                from visual_dom.context import Session
                Session._probe_ocr_engine(self._ocr_combo.currentText())
            except ValueError as e:
                self._hide_progress()
                QMessageBox.warning(self, "OCR Engine Not Available", str(e))
                self._statusbar.showMessage(
                    "Analysis aborted - configured OCR engine is not installed")
                return
            except ImportError:
                pass    # visual_dom itself missing is reported by the code below

            # Generate session ID and create output folder
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
            session_dir = os.path.join(project_root, 'output', 'sessions', session_id)
            os.makedirs(session_dir, exist_ok=True)
            print(f"[Viewer] Session: {session_id}")
            print(f"[Viewer] Output folder: {session_dir}")

            # Save screenshot to session folder
            screenshot_path = os.path.join(session_dir, 'screenshot.png')
            with open(screenshot_path, 'wb') as f:
                f.write(screenshot)
            print(f"[Viewer] Screenshot saved: {screenshot_path}")

            # Also save as temp file for pipeline processing
            temp_path = screenshot_path

            try:
                # Add src to path if needed
                src_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src')
                src_path = os.path.abspath(src_path)
                if src_path not in sys.path:
                    sys.path.insert(0, src_path)

                # Run Visual DOM pipeline
                self._show_progress("Importing Visual DOM modules...", 70)
                print("[Viewer] Importing Visual DOM modules...")
                QApplication.processEvents()

                from visual_dom.core.domain.pipeline import VisualDOMPipeline
                from visual_dom.core.domain.compiler.dom_compiler import DOMCompiler
                from visual_dom.core.domain.hierarchy.coarse_builder import CoarseHierarchyBuilder
                print("[Viewer] Modules imported successfully")

                self._show_progress("Initializing pipeline (loading OCR model)...", 75)
                print("[Viewer] Initializing VisualDOMPipeline (this may take a while for OCR model loading)...")
                QApplication.processEvents()

                # Check GPU availability
                try:
                    import torch
                    gpu_available = torch.cuda.is_available()
                    if gpu_available:
                        gpu_name = torch.cuda.get_device_name(0)
                        print(f"[Viewer] GPU AVAILABLE: {gpu_name}")
                        print(f"[Viewer] CUDA version: {torch.version.cuda}")
                    else:
                        print("[Viewer] GPU NOT AVAILABLE - using CPU (slower)")
                except ImportError:
                    gpu_available = False
                    print("[Viewer] PyTorch not found - using CPU")

                # Get selected OCR engine
                ocr_engine = self._ocr_combo.currentText()
                print(f"[Viewer] OCR engine: {ocr_engine}")

                # Check if SLM review is enabled
                slm_backend = None
                slm_model = None
                if self._slm_checkbox.isChecked():
                    slm_backend = "ollama"
                    slm_model = self._slm_model_combo.currentText()
                    print(f"[Viewer] SLM review ENABLED (ollama, model={slm_model})")

                # Check camera mode
                camera_mode = self._camera_mode_checkbox.isChecked()
                if camera_mode:
                    print("[Viewer] Camera mode ENABLED (screen detection + rectification)")

                # Check detector mode
                detector_mode = self._detector_combo.currentText()
                yolo_model_path = None
                detector_kwargs = {}
                if detector_mode in ("yolo", "hybrid"):
                    # Look for YOLO model in standard locations
                    yolo_candidates = [
                        os.path.join(project_root, "models", "pretrained", "yolo_ui_best.pt"),
                        os.path.join(project_root, "models", "cv_detection", "vizdom_ui", "weights", "best.pt"),
                    ]
                    for candidate in yolo_candidates:
                        if os.path.exists(candidate):
                            yolo_model_path = candidate
                            break
                    if yolo_model_path:
                        print(f"[Viewer] YOLO model: {yolo_model_path}")
                    else:
                        print("[Viewer] Warning: No YOLO model found, falling back to UIED")
                        detector_mode = "uied"
                elif detector_mode == "omniparser":
                    # Resolve OmniParser weights from env vars, then standard locations.
                    icon_detect = os.environ.get("OMNIPARSER_ICON_DETECT")
                    icon_caption = os.environ.get("OMNIPARSER_ICON_CAPTION")
                    op_root = os.environ.get("OMNIPARSER_ROOT")
                    if not icon_detect:
                        cand = os.path.join(project_root, "models", "omniparser",
                                            "icon_detect", "model.pt")
                        if os.path.exists(cand):
                            icon_detect = cand
                    if not icon_caption:
                        cand = os.path.join(project_root, "models", "omniparser",
                                            "icon_caption_florence")
                        if os.path.isdir(cand):
                            icon_caption = cand
                    if not op_root:
                        cand = os.path.join(project_root, "third_party", "OmniParser")
                        if os.path.isdir(cand):
                            op_root = cand
                    if icon_detect and icon_caption:
                        if op_root:
                            detector_kwargs["omniparser_root"] = op_root
                        detector_kwargs["icon_detect_path"] = icon_detect
                        detector_kwargs["icon_caption_path"] = icon_caption
                        # Optional YOLO confidence cutoff override. Default 0.05
                        # misses faint glyphs (e.g. a minimize "-" button) on some
                        # captures; set OMNIPARSER_BOX_THRESHOLD=0.03 to recover them
                        # (at a small false-positive cost).
                        bt = os.environ.get("OMNIPARSER_BOX_THRESHOLD")
                        if bt:
                            try:
                                detector_kwargs["box_threshold"] = float(bt)
                                print(f"[Viewer] OmniParser box_threshold: {float(bt)}")
                            except ValueError:
                                print(f"[Viewer] Ignoring invalid OMNIPARSER_BOX_THRESHOLD={bt!r}")
                        print(f"[Viewer] OmniParser weights: {icon_detect}")
                    else:
                        print("[Viewer] Warning: OmniParser weights not found "
                              "(set OMNIPARSER_ICON_DETECT / OMNIPARSER_ICON_CAPTION), "
                              "falling back to UIED")
                        detector_mode = "uied"
                elif detector_mode == "grpc":
                    target = self._grpc_target_edit.text().strip() or "localhost:50051"
                    detector_kwargs["target"] = target
                    print(f"[Viewer] Remote gRPC detector target: {target}")

                pipeline = VisualDOMPipeline(
                    ocr_engine=ocr_engine,
                    use_gpu=gpu_available,
                    confidence_threshold=0.3,
                    slm_backend=slm_backend,
                    slm_model=slm_model,
                    camera_mode=camera_mode,
                    detector=detector_mode,
                    yolo_model_path=yolo_model_path,
                    detector_kwargs=detector_kwargs,
                    text_ensemble=self._text_ensemble_checkbox.isChecked(),
                    merge_oversegmented=self._merge_checkbox.isChecked(),
                )
                print(f"[Viewer] Pipeline initialized (Det={detector_mode}, OCR={ocr_engine}, GPU={gpu_available}, SLM={slm_model or 'off'})")

                self._show_progress("Running CV pipeline (OCR + Element Detection)...", 80)
                print("[Viewer] Running pipeline.process() - this may take 10-30 seconds...")
                QApplication.processEvents()

                result = pipeline.process(temp_path)
                print(f"[Viewer] Pipeline complete. Found {len(result.get('elements', []))} elements")

                # A runtime OCR death (engine present but failing) degrades the
                # run to 0 text, which looks exactly like a text-free screen.
                # The pipeline records it in stats; say it out loud here.
                text_error = (result.get("stats") or {}).get("text_error")
                if text_error:
                    print(f"[Viewer] WARNING: text detection failed: {text_error}")
                    QMessageBox.warning(
                        self, "Text Detection Failed",
                        "The OCR engine failed during this run, so the DOM "
                        f"contains no text elements:\n\n{text_error}\n\n"
                        "Element boxes are still available, but text= locators "
                        "will not resolve."
                    )

                # Save CV pipeline result (before hierarchy/SLM)
                try:
                    cv_result_path = os.path.join(session_dir, 'cv_pipeline_result.json')
                    with open(cv_result_path, 'w', encoding='utf-8') as f:
                        _json.dump(result, f, indent=2, ensure_ascii=False)
                    print(f"[Viewer] CV result saved: {cv_result_path}")
                except Exception as e:
                    print(f"[Viewer] Warning: could not save CV result: {e}")

                self._show_progress("Building element tree...", 90)
                QApplication.processEvents()

                if result and result.get("elements"):
                    elements = result.get("elements", [])
                    image_size = result.get("image_size", {})
                    width = image_size.get("width", 1920)
                    height = image_size.get("height", 1080)
                    print(f"[Viewer] Image size: {width}x{height}, Elements: {len(elements)}")

                    # Build hierarchy using CoarseHierarchyBuilder
                    self._show_progress("Building hierarchy...", 92)
                    print("[Viewer] Building hierarchy...")
                    QApplication.processEvents()

                    hierarchy_builder = CoarseHierarchyBuilder()
                    hierarchy_result = hierarchy_builder.build(elements)
                    hierarchy = hierarchy_result.get("root")  # Get the root tree
                    print("[Viewer] Hierarchy built")

                    # Compile DOM with full metadata (role, locators, flags)
                    self._show_progress("Compiling DOM with locators...", 95)
                    print("[Viewer] Compiling DOM...")
                    QApplication.processEvents()

                    compiler = DOMCompiler(generate_locators=True)
                    dom_result = compiler.compile(
                        elements=elements,
                        hierarchy=hierarchy,
                        image_size=(width, height),
                    )
                    print("[Viewer] DOM compiled")

                    # Convert to DOMTree format
                    from ..core.tree import DOMTree

                    dom_data = {
                        "image_size": image_size,
                        "source": "visual_dom",
                        "session_id": session_id,
                        "cv_stats": result.get("stats", {}),
                        "dom": dom_result
                    }

                    # Save final DOM result
                    try:
                        dom_result_path = os.path.join(session_dir, 'dom_result.json')
                        with open(dom_result_path, 'w', encoding='utf-8') as f:
                            _json.dump(dom_data, f, indent=2, ensure_ascii=False)
                        print(f"[Viewer] DOM result saved: {dom_result_path}")
                    except Exception as e:
                        print(f"[Viewer] Warning: could not save DOM result: {e}")

                    # Save session info
                    try:
                        session_info = {
                            "session_id": session_id,
                            "timestamp": datetime.now().isoformat(),
                            "image_size": image_size,
                            "ocr_engine": ocr_engine,
                            "camera_mode": camera_mode,
                            "slm_enabled": slm_backend is not None,
                            "slm_model": slm_model,
                            "gpu_available": gpu_available,
                            "element_count": len(elements),
                            "cv_stats": result.get("stats", {}),
                        }
                        # Session provenance: which app/window (or file) was
                        # analyzed — set at acquisition time by the capture /
                        # open-image paths.
                        session_info.update(getattr(self, "_capture_context", None) or {})
                        info_path = os.path.join(session_dir, 'session_info.json')
                        with open(info_path, 'w', encoding='utf-8') as f:
                            _json.dump(session_info, f, indent=2)
                        print(f"[Viewer] Session info saved: {info_path}")
                    except Exception as e:
                        print(f"[Viewer] Warning: could not save session info: {e}")

                    print("[Viewer] Creating DOMTree from compiled data...")
                    dom_tree = DOMTree.from_dict(dom_data)
                    self._model.set_dom_tree(dom_tree)
                    print(f"[Viewer] DOMTree created with {dom_tree.get_element_count()} elements")

                    stats = result.get("stats", {})
                    self._hide_progress()
                    self._statusbar.showMessage(
                        f"[{session_id}] {dom_tree.get_element_count()} elements "
                        f"(Text: {stats.get('text_detected', 0)}, UI: {stats.get('uied_detected', 0)}) "
                        f"— output/sessions/{session_id}/"
                    )
                else:
                    self._hide_progress()
                    self._statusbar.showMessage("Analysis completed but no elements were detected")
                    print("[Viewer] No elements detected in result")

            finally:
                pass  # Screenshot kept in session folder

        except ImportError as e:
            self._hide_progress()
            import traceback
            traceback.print_exc()
            QMessageBox.warning(
                self, "Visual DOM Not Available",
                f"Visual DOM Generator dependencies not available:\n{e}\n\n"
                "Required: pip install easyocr opencv-python\n\n"
                "You can still load DOM JSON files manually using 'Open DOM'."
            )
            self._statusbar.showMessage("Visual DOM not available - use 'Open DOM' to load a JSON file")

        except Exception as e:
            self._hide_progress()
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, "Analysis Failed", f"Error during analysis:\n{e}")
            self._statusbar.showMessage("Analysis failed - check console for details")

    def _on_platform_event(self, event: str, data):
        """Handle platform manager events."""
        if event == 'connected':
            pass  # Handled by _on_connected
        elif event == 'disconnected':
            self._disconnect()
        elif event == 'screenshot_captured':
            self._statusbar.showMessage("Screenshot captured")
        elif event == 'dom_generated':
            self._statusbar.showMessage("DOM generated")

    def _toggle_explore_mode(self, checked):
        """Toggle explore mode."""
        self._model.set_explore_mode(checked)

    def _export_to_robot(self):
        """Export defined elements to Robot Framework."""
        definitions = self._model.get_all_definitions()

        if not definitions:
            # No definitions, ask if user wants to export all elements
            reply = QMessageBox.question(
                self, "Export",
                "No elements have been defined.\n\n"
                "Would you like to export ALL elements instead?\n"
                "(Select 'No' to define elements first)",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                return

            # Export all elements with auto-generated names
            if self._model.dom_tree:
                elements = self._model.dom_tree.get_all_elements()
                if not elements:
                    QMessageBox.warning(self, "Export", "No elements to export")
                    return

                filepath, _ = QFileDialog.getSaveFileName(
                    self, "Export to Robot Framework",
                    "elements.resource", "Resource Files (*.resource);;Robot Files (*.robot)"
                )

                if filepath:
                    success = self._exporter.export(
                        elements, filepath,
                        self._model.dom_tree,
                        title="Exported Elements"
                    )

                    if success:
                        QMessageBox.information(
                            self, "Export",
                            f"Successfully exported {len(elements)} elements to:\n{filepath}"
                        )
                    else:
                        QMessageBox.warning(self, "Export", "Failed to export elements")
            return

        # Export user-defined elements
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export to Robot Framework",
            "elements.resource", "Resource Files (*.resource);;Robot Files (*.robot)"
        )

        if filepath:
            success = self._exporter.export_definitions(
                definitions, filepath,
                self._model.dom_tree,
                title="User Defined Elements"
            )

            if success:
                QMessageBox.information(
                    self, "Export",
                    f"Successfully exported {len(definitions)} defined elements to:\n{filepath}"
                )
            else:
                QMessageBox.warning(self, "Export", "Failed to export elements")


def run_viewer():
    """Run the Visual DOM Viewer application."""
    if not HAS_PYQT5:
        print("PyQt5 is required. Install with: pip install PyQt5")
        return 1

    from .branding import app_icon, set_windows_app_id

    # Before the first window exists, or Windows has already filed the process
    # under the interpreter and the taskbar keeps python.exe's icon.
    set_windows_app_id()

    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setApplicationName("VizDOM Viewer")
    app.setApplicationDisplayName("VizDOM Viewer")
    app.setWindowIcon(app_icon())

    window = VisualDOMViewerWindow()
    window.show()

    return app.exec_()


if __name__ == '__main__':
    sys.exit(run_viewer())
