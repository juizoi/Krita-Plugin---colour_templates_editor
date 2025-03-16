from __future__ import annotations
import time
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from krita import *

from typing import *

import json

json_path = "colour_templates_editor/saved_templates.json"

# This is the first class krita calls when launching the tool
class ColourTemplatesEditorUI(DockWidget):
    # This is where it all starts, using a dockWidget (so you can move the tool wherever you want and dock it to your window)
    # def __init__ is the initialisation method, that is where it start
    def __init__(self):
        # super().__init__() takes the parent class of this class (for this it's DockWidget) and does all of it's setup.
        # Essentially, it's growing the parent so that the child can copy and become better
        super().__init__()
        # A swanky title for our docker
        self.setWindowTitle("Tom's Colour Templates Editor")
        # instancing a GridUI widget, this is a new class I made that pretty much holds all our UI (the list and button)
        grid_widget = GridUI(self)
        # When instanced, the widget isn't sized and adapted to the DockWidget, we have to do setWidget to allow that to happen
        self.setWidget(grid_widget)

    # This is here for some reason, it's a virtual function that overrides when anything happens to the docker
    def canvasChanged(self, canvas):
        pass

# The GridUI class holds a dictionary that can be referenced via layer name that holds a big ol value that holds all these useful values
class PresetItem():
    # This is the UI item the widget list spawns, it's an "element" from the list
    item: QListWidgetItem
    # This is the little file icon that tells the user when data has been saved to the save file
    icon_widget: QLabel
    # This is the colour picker
    colour_button: ColourButtonUI
    # This is the parent of the layer this list item belongs to
    parent: GroupLayer
    # This is the paint layer this list item belongs to
    node: Node

# The chunky one, holds our list and button    
class GridUI(QWidget):
    # Same init code here but instead of DockWidget, it's a lower level QWidget
    def __init__(self, parent):
        super(QWidget, self).__init__(parent=parent)

        # This holds info on each item in the list by layer name, each item holds a presetItem with all the variables stated above this class
        # This is kind of how it works:
        #     Dict Item (i.e. self.name_item_dict["SKIN"]):
        #       |_PresetItem:
        #           |_item: QListWidgetItem
        #           |_icon_widget: QLabel
        #           |_colour_button: ColourButtonUI
        #           |_parent: GroupLayer
        #           |_node: Node
        self.name_item_dict: Dict[str, PresetItem] = {}
        # A global variable to hold the group layer name
        self.group_node: Node = None

        # QtWidgets get aligned via layouts, a QVBoxLayout is just a container that says "Hey, stack these widgets on top of each other"
        self.main_layout = QVBoxLayout(self)
        
        # QListWidget is a container with a scrollbar that holds these widgets and adds clearing of said list easy, lots of selection logic too
        # Here self.widget_list will be the list with all the child layers
        self.widget_list = QListWidget()

        # set_colour_button will be our bottom button
        set_colour_button = QPushButton("Set Colour to Selected Layers")
        # This is what is known as a signal connection, it's me telling the program "When you hit the button, do this function"
        # This function being self.set_pressed() found below
        set_colour_button.pressed.connect(self.set_pressed)

        # And here we assemble all our widgets into the layout
        # The QListWidget and QPushButton lines were us making the building blocks
        # And the QVBoxLayout is the toddler putting them on top of each other
        self.main_layout.addWidget(self.widget_list)
        self.main_layout.addWidget(set_colour_button)

        # This is a little more complicated, these variables are where the already existing layer dock elements will be stored
        self.selection_model: None | QItemSelectionModel = None
        self.view_model: None | QAbstractListModel = None

        # And this timer fires every second to find these elements, once it finds it, it stops firing
        self.timer = QTimer()
        self.timer.moveToThread(self.thread())
        self.timer.timeout.connect(self.find_list)
        self.timer.start(1000)

    # When the user presses the "Set Colour to Slected Layers" button
    def set_pressed(self):
        # At this point, if self.name_item_dict has no entries and the group layer entity is not valid do not execute this code
        if not self.name_item_dict and not self.group_node:
            return

        # This function stops the signals that would fire when selecting a new layer in the viewport
        # We don't want the baggage that comes with it, as it generates that list over again if it isn't blocked
        self.selection_model.blockSignals(True)
        # This variable ensures the user colours stay after doing all the colour setting operations
        initial_fg_col = Krita.instance().activeWindow().activeView().foregroundColor()
        # This deselects everything, might not be useful, but I wanted the fill to be clean and not have any weird selections ruin the experience
        Krita.instance().action('deselect').trigger()
        # For every item in the main dictionary do...
        for item in self.name_item_dict.values():
            # If the item's colour is valid (so if it was set by the user)
            if item.colour_button.color():
                # Select the layer first
                Krita.instance().activeDocument().setActiveNode(item.node)
                # Lock that layer's alpha (Your alpha locking method was better Door, I was wrong, but masks are so much more powerful)
                item.node.setAlphaLocked(True)
                # Set the foreground colour to the colour specified in the UI for that layer
                Krita.instance().activeWindow().activeView().setForeGroundColor(ManagedColor.fromQColor(QColor(item.colour_button.color())))
                # Fill the layer with that foreground colour
                Krita.instance().action('fill_selection_foreground_color').trigger()
                # Now this was a headscratcher, apprarently, filling the foreground takes a little second
                # I was unlocking the layer before it finished
                # So the whole layer was filled, hence why we use a small timer (This could break if filling takes longer than half a second)
                
        # Set the foreground colour back to what the user initially had
        Krita.instance().activeWindow().activeView().setForeGroundColor(initial_fg_col)
        # And here's the fabled timer, after 500 milliseconds, do self.do_after_generation()
        QTimer().singleShot(500, self.do_after_generation)

    # The method called half a second after the filling
    def do_after_generation(self):
        # For every item in the main dictionary do...
        for item in self.name_item_dict.values():
            # Unlock the layer's alpha
            item.node.setAlphaLocked(False)
        # Unblock the signals (for some reason this just releases all the method calls that the op was blocking)
        self.selection_model.blockSignals(False)
        
        # Select the group layer again
        Krita.instance().activeDocument().setActiveNode(self.group_node)

    # This handy method only exists to get callback functions whenever someone changes their layer selection
    def find_list(self):
        # Find the layer dockwidget
        kis_layer_box = next((d for d in Krita.instance().dockers() if d.objectName() == 'KisLayerBox'), None)

        # If the dockwidget was found..
        if kis_layer_box:
            # Nab the QTreeView that renders the list of layers
            view = kis_layer_box.findChild(QTreeView, "listLayers")
            # Get its model, this is where all the logic happens in that tree
            self.view_model = view.model()
            # Get the selection logic
            self.selection_model = view.selectionModel()
            # Connect the signal when the layer selection changes to the self.populate_list() declared below
            self.selection_model.currentChanged.connect(self.populate_list)
            # When all of this is found, stop the timer
            self.timer.stop()
            # And do the initial list population
            self.populate_list()
    
    # This function spawns all the items in our list ui
    def populate_list(self):
        # Clear the widget_list ui and the self.name_item_dict
        self.widget_list.clear()
        self.name_item_dict = {}
        
        # if Krita does not have an active document stop executing this code
        if not Krita.instance().activeDocument():
            return
        # Get the selected layer node
        node: Node = Krita.instance().activeDocument().activeNode()
        # If this node is not a GroupLayer, stop executing the code
        if not node and not isinstance(node, GroupLayer):
            return
        # For each child of the group layer node, do..
        for child_node in node.childNodes():
            # If this child layer is not a paintlayer, hop to the next layer
            if not child_node.type() == 'paintlayer':
                continue
            # The layer's name, probably in capitals, like "TEETH"
            child_name = child_node.name()
            # This is to check if everything is uppercase, if it isn't, tough shit, stick to the workflow
            if child_name.upper() == child_name:
                # This is where the Dictionary item gets assigned to a PresetItem, along with all of its member variables
                self.name_item_dict[child_name] = PresetItem()
                self.name_item_dict[child_name].node = child_node
                self.name_item_dict[child_name].parent = node
                # And assigning the group layer to that global self.group_node
                self.group_node = node

                # This is the container for all list items
                item_widget = QListWidgetItem(self.widget_list)
                # Makes sure the user can't highlight the item list block, this tool doesn't need the user to do that
                item_widget.setFlags(item_widget.flags() & Qt.ItemIsSelectable & Qt.ItemIsEnabled)

                # PresetItem().item setting
                self.name_item_dict[child_name].item = item_widget

                # Create the little page icon using a label, because Qt logic is dumb
                icon_widget = QLabel()
                # Don't extend this widget to an even length as the other widgets in its layout
                icon_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Maximum)
                
                # PresetItem().icon_widget setting
                self.name_item_dict[child_name].icon_widget = icon_widget

                # Another QLabel, but this one makes more sense, it's the text, with the layer name
                label = QLabel(child_name)

                # The colour picker button, we're passing in the PresetItem, a few things that are needed in there for that class
                colour_box = ColourButtonUI(p_item=self.name_item_dict[child_name])
                # Extend the width of this widget to up to 200 pixels
                colour_box.setMaximumWidth(200)
                # Connect the signal for whenever the user changes the colour picker's colour
                colour_box.colorChanged.connect(self.colour_changed)

                # Instancing the widget the widget item will hold
                widget = QWidget()
                # This widget holds a horizontal layout to set its widget children right next to each other
                horizontal_layout = QHBoxLayout(widget)
                horizontal_layout.addWidget(icon_widget)
                horizontal_layout.addWidget(label)
                horizontal_layout.addWidget(colour_box)
                # This was a bugger, by default, the contentsmargin are way too big, so we removed the margin
                horizontal_layout.setContentsMargins(0,0,0,0)
                # this sets the instanced widget to the item
                self.widget_list.setItemWidget(item_widget, widget)
                # This scales the item to fit the widget, one of Qt's QTreeWidget's quirks
                item_widget.setSizeHint(widget.sizeHint())
        
        # Load all the colours from the save file to the newly added list
        self.load_colours_to_list()

    # Does what it says on the tin, loads the json file each time the list gets populated, might not be the best for performance
    # But honey, I don't give a damn
    def load_colours_to_list(self):
        # This path might need changing if the save file isn't behaving properly
        # Opens the json file
        with open(json_path, "r") as f:
            # Gets the inside of the json file and loads it into a "python friendly" dictionary
            data = json.loads(f.read())
            
            # For every item in the main dictionary do...
            for item in self.name_item_dict.values():
                # If the parent group layer does not exist in json, give up
                if not item.parent.name() in data:
                    return
                # If the parent exists in the json but the paint layer name doesn't, continue to the next paintlayer
                elif not item.node.name() in data[item.parent.name()]:
                    continue
                # If this is actually a valid value, set the colour to that value (this should be the hex code)
                elif data[item.parent.name()][item.node.name()]:
                    item.colour_button.setColor(data[item.parent.name()][item.node.name()], False)

    # This function calls whenever the signal calls colorChanged, autosaves the colour to the file
    def colour_changed(self, p_item: PresetItem):
        # the json data
        data = {}
        # the check to see if anything has changed from the ui to the file
        data_changed = False
        # Open the json file to read only
        with open(json_path, "r") as f:
            # Set the json file's guts to the data dict
            data = json.loads(f.read())
            # If the parent group layer doesn't exist in the json, create one
            if not p_item.parent.name() in data:
                data[p_item.parent.name()] = {}
                data_changed = True
            # If the paint layer doesn't exist under the parent in the json, create one
            if not p_item.node.name() in data[p_item.parent.name()]:
                data[p_item.parent.name()][p_item.node.name()] = ""
                data_changed = True
            # If the colour is not the same from the UI to the json, change it
            if not data[p_item.parent.name()][p_item.node.name()] == p_item.colour_button.color():
                data[p_item.parent.name()][p_item.node.name()] = p_item.colour_button.color()
                data_changed = True

        # If anything has changed
        if data_changed:
            # Open the json file in write, set it to the data we created and format it real pretty like
            with open(json_path, "w") as f:
                json.dump(data, f, indent=4)

# This was totally not stolen from the great Martin Fitzpatrick https://www.pythonguis.com/widgets/qcolorbutton-a-color-selector-tool-for-pyqt/ 
# I swear
# They just write like me, great minds and all that
class ColourButtonUI(QPushButton):

    # Fancy Martin signal that will be used in the parent widget
    colorChanged = pyqtSignal(object)

    # Fancy init with fancy args, so pretentious and overkill
    def __init__(self, *args, p_item:PresetItem, color=None, **kwargs):
        super().__init__(*args, **kwargs)

        # This is a string representing the colour, or 'color' as Martin the smarty pants calls it
        self._color = None
        # This is me! I did this, brought in the preset item
        self._p_item = p_item
        # To then set the colour_button inside it to the colour_button ui
        p_item.colour_button = self

        # Connecting the "when the colour picker is pressed" signal to onColorPicker
        self.pressed.connect(self.onColorPicker)

        # Set the initial/default state.
        self.setColor()

    # Changed a small thing here, the default colour is now hard coded to 20,20,20
    def setColor(self, color=None, emit=True):
        # If the colour set is not the same as the current colour
        if color != self._color:
            # Set the colour
            self._color = color
            # If we want to emit the signal (this was my change)
            if emit:
                # Emit the signal, firing it once and calling the onColorPicker function
                self.colorChanged.emit(self._p_item)

        # If the color has been called in the function's arguments (if it's not None)
        if self._color:
            # Set the colour to the argument colour through a stylesheet
            self.setStyleSheet(
                f"background-color: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 {self._color}, stop: 1 {self._color});"
                )
            # Don't set any text to the box
            self.setText("")
            # Change the file icon to "Saved"
            self._p_item.icon_widget.setPixmap(Krita.instance().icon('document-save').pixmap(24))
        # If the colour has not been set yet
        else:
            # Set the stylesheet background to a default colour
            self.setStyleSheet("background-color: rgb(20,20,20); color: rgb(100,100,100);")
            # Set the colour picker's text to "empty"
            self.setText("empty")
            # Change the file icon to "Folder-Documents"
            self._p_item.icon_widget.setPixmap(Krita.instance().icon('folder-documents').pixmap(24))

    # Helper function to nab the colour string, used a few times in my code up above
    def color(self):
        return self._color

    # Function that calls whenever a colour picker has been clicked!
    def onColorPicker(self):
        # Open a floating window where the user can select a custom colour
        dlg = QColorDialog()
        if dlg.exec_():
            # Set the colour of the colour picker to the selected custom colour
            self.setColor(dlg.currentColor().name())

# And finally, this thing adds the Docker to the Krita family
Krita.instance().addDockWidgetFactory(DockWidgetFactory("colourTemplatesEditorUI", DockWidgetFactoryBase.DockRight, ColourTemplatesEditorUI))