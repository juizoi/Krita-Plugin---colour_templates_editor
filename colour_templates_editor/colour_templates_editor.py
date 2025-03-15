from __future__ import annotations
import time
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from krita import *

from typing import *

import json

class PresetItem():
    index: int
    item: QListWidgetItem
    icon_widget: QLabel
    colour_button: ColourButtonUI
    active_colour: QColor
    parent: GroupLayer
    node: Node

class ColourTemplatesEditorUI(DockWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tom's Colour Templates Editor")
        grid_widget = GridUI(self)
        self.setWidget(grid_widget)

    def canvasChanged(self, canvas):
        pass

class GridUI(QWidget):
    def __init__(self, parent):
        super(QWidget, self).__init__(parent=parent)


        self.name_item_dict: Dict[str, PresetItem] = {}
        self.group_node: Node = None

        self.main_layout = QVBoxLayout(self)
        self.widget_list = QListWidget()

        set_colour_button = QPushButton("Set Colour to Selected Layers")
        set_colour_button.pressed.connect(self.set_pressed)

        self.main_layout.addWidget(self.widget_list)
        self.main_layout.addWidget(set_colour_button)

        self.selection_model: None | QItemSelectionModel = None
        self.view_model: None | QAbstractListModel = None

        self.timer = QTimer()
        self.timer.moveToThread(self.thread())
        self.timer.timeout.connect(self.find_list)
        self.timer.start(1000)

    def set_pressed(self):
        print("SET PRESSED")
        if not self.name_item_dict:
            return
        if self.group_node:
            self.selection_model.blockSignals(True)
            initial_fg_col = Krita.instance().activeWindow().activeView().foregroundColor()
            Krita.instance().action('deselect').trigger()
            for item in self.name_item_dict.values():
                if item.colour_button.color():
                    Krita.instance().activeDocument().setActiveNode(item.node)
                    item.node.setAlphaLocked(True)
                    Krita.instance().activeDocument().setActiveNode(item.node)
                    Krita.instance().activeWindow().activeView().setForeGroundColor(ManagedColor.fromQColor(QColor(item.colour_button.color())))
                    Krita.instance().action('fill_selection_foreground_color').trigger()
                    
            Krita.instance().activeWindow().activeView().setForeGroundColor(initial_fg_col)
            QTimer().singleShot(500, self.do_after_generation)

    def do_after_generation(self):
        for item in self.name_item_dict.values():
            item.node.setAlphaLocked(False)
        self.selection_model.blockSignals(False)
        
        Krita.instance().activeDocument().setActiveNode(self.group_node)


    def find_list(self):
        kis_layer_box = next((d for d in Krita.instance().dockers() if d.objectName() == 'KisLayerBox'), None)

        if kis_layer_box:
            view = kis_layer_box.findChild(QTreeView, "listLayers")
            self.view_model = view.model()
            self.selection_model = view.selectionModel()
            self.selection_model.currentChanged.connect(self.populate_list)
            self.timer.stop()
            self.populate_list()
    
    def populate_list(self):
        print("POPULATING")
        self.widget_list.clear()
        self.name_item_dict = {}
        node: Node = Krita.instance().activeDocument().activeNode()
        if not node and not isinstance(node, GroupLayer):
            return
        for child_node in node.childNodes():
            if not child_node.type() == 'paintlayer':
                continue
            child_name = child_node.name()
            if child_name.upper() == child_name:
                self.name_item_dict[child_name] = PresetItem()
                self.name_item_dict[child_name].node = child_node
                self.name_item_dict[child_name].parent = node
                self.group_node = node

                item_widget = QListWidgetItem(self.widget_list)
                item_widget.setFlags(item_widget.flags() & Qt.ItemIsSelectable & Qt.ItemIsEnabled)

                self.name_item_dict[child_name].item = item_widget

                icon_widget = QLabel()
                icon_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Maximum)
                self.name_item_dict[child_name].icon_widget = icon_widget

                label = QLabel(child_name)

                colour_box = ColourButtonUI(p_item=self.name_item_dict[child_name])
                colour_box.setMaximumWidth(200)
                colour_box.colorChanged.connect(self.colour_changed)

                widget = QWidget()
                horizontal_layout = QHBoxLayout(widget)
                horizontal_layout.addWidget(icon_widget)
                horizontal_layout.addWidget(label)
                horizontal_layout.addWidget(colour_box)
                horizontal_layout.setContentsMargins(0,0,0,0)
                self.widget_list.setItemWidget(item_widget, widget)
                item_widget.setSizeHint(widget.sizeHint())
        
        self.load_colours_to_list()

    def load_colours_to_list(self):
        with open("saved_templates.json", "r") as f:
            data = json.loads(f.read())
            for item in self.name_item_dict.values():
                if not item.parent.name() in data:
                    return
                elif not item.node.name() in data[item.parent.name()]:
                    continue
                elif data[item.parent.name()][item.node.name()]:
                    item.colour_button.setColor(data[item.parent.name()][item.node.name()], False)

    def colour_changed(self, p_item: PresetItem):
        data = {}
        data_changed = False
        with open("saved_templates.json", "r") as f:
            data = json.loads(f.read())
            if not p_item.parent.name() in data:
                data[p_item.parent.name()] = {}
                data_changed = True
            if not p_item.node.name() in data[p_item.parent.name()]:
                data[p_item.parent.name()][p_item.node.name()] = ""
                data_changed = True
            if not data[p_item.parent.name()][p_item.node.name()] == p_item.colour_button.color():
                data[p_item.parent.name()][p_item.node.name()] = p_item.colour_button.color()
                data_changed = True

        if data_changed:
            with open("saved_templates.json", "w") as f:
                json.dump(data, f, indent=4)

class ColourButtonUI(QPushButton):

    colorChanged = pyqtSignal(object)

    def __init__(self, *args, p_item:PresetItem, color=None, **kwargs):
        super().__init__(*args, **kwargs)

        self._color = None
        self._p_item = p_item
        p_item.colour_button = self
        self._default = color

        self.pressed.connect(self.onColorPicker)

        # Set the initial/default state.
        self.setColor(self._default)

    def setColor(self, color, emit=True):
        if color != self._color:
            self._color = color
            if emit:
                self.colorChanged.emit(self._p_item)

        if self._color:
            self.setStyleSheet(
                f"background-color: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 {self._color}, stop: 1 {self._color});"
                )
            self.setText("")
            self._p_item.icon_widget.setPixmap(Krita.instance().icon('document-save').pixmap(24))
        else:
            self.setStyleSheet("background-color: rgb(20,20,20); color: rgb(100,100,100);")
            self.setText("empty")
            self._p_item.icon_widget.setPixmap(Krita.instance().icon('folder-documents').pixmap(24))

    def color(self):
        return self._color

    def onColorPicker(self, _p_item=None):
        dlg = QColorDialog()
        if dlg.exec_():
            self.setColor(dlg.currentColor().name())
            self._p_item.active_colour = dlg.currentColor()


Krita.instance().addDockWidgetFactory(DockWidgetFactory("colourTemplatesEditorUI", DockWidgetFactoryBase.DockRight, ColourTemplatesEditorUI))