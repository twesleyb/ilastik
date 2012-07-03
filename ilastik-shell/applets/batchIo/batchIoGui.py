from PyQt4.QtCore import pyqtSignal, QTimer, QRectF, Qt, SIGNAL, QObject
from PyQt4.QtGui import *
from PyQt4 import uic

import threading

from functools import partial
import os
import sys
import copy
import utility # This is the ilastik shell utility module
from utility import bind
from utility import PathComponents

import ilastikshell.applet

import logging
logger = logging.getLogger(__name__)
traceLogger = logging.getLogger('TRACE.' + __name__)
from lazyflow.tracer import Tracer

class Column():
    """ Enum for table column positions """
    Dataset = 0
    ExportLocation = 1
    Action = 2

class BatchIoGui(QMainWindow):
    """
    Manages all GUI elements in the data selection applet.
    This class itself is the central widget and also owns/manages the applet drawer widgets.
    """
    ###########################################
    ### AppletGuiInterface Concrete Methods ###
    ###########################################
    
    def centralWidget( self ):
        return self

    def appletDrawers(self):
        return [ (self.title, self.drawer) ]

    def menuWidget( self ):
        return self.menuBar

    def viewerControlWidget(self):
        return None

    def setImageIndex(self, index):
        pass

    ###########################################
    ###########################################
    
    def __init__(self, dataSelectionOperator, guiControlSignal, title):
        with Tracer(traceLogger):
            super(BatchIoGui, self).__init__()
    
            self.title = title
            self.drawer = None
            self.mainOperator = dataSelectionOperator
            self.menuBar = QMenuBar()
            
            self.initAppletDrawerUic()
            self.initCentralUic()
            self.chosenExportDirectory = '/'
            
            self.guiControlSignal = guiControlSignal
            
            def handleNewDataset( multislot, index ):
                # Make room in the GUI table
                self.tableWidget.insertRow( index )
                
                # Update the table row data when this slot has new data
                # We can't bind in the row here because the row may change in the meantime.
                multislot[index].notifyDirty( bind( self.updateTableForSlot ) )
    
            self.mainOperator.OutputDataPath.notifyInserted( bind( handleNewDataset ) )
            
            def handleDatasetRemoved( multislot, index ):
                # Simply remove the row we don't need any more
                self.tableWidget.removeRow( index )
    
            self.mainOperator.OutputDataPath.notifyRemove( bind( handleDatasetRemoved ) )
            
            self.mainOperator.Suffix.notifyDirty( self.updateDrawerGuiFromOperatorSettings )
            self.mainOperator.ExportDirectory.notifyDirty( self.updateDrawerGuiFromOperatorSettings )
            self.updateDrawerGuiFromOperatorSettings()
        
    def initAppletDrawerUic(self):
        """
        Load the ui file for the applet drawer, which we own.
        """
        with Tracer(traceLogger):
            # Load the ui file (find it in our own directory)
            localDir = os.path.split(__file__)[0]+'/'
            # (We don't pass self here because we keep the drawer ui in a separate object.)
            self.drawer = uic.loadUi(localDir+"/batchIoDrawer.ui")
    
            # Set up our handlers
            self.drawer.saveWithInputButton.toggled.connect( self.handleExportLocationOptionChanged )
            self.drawer.saveToDirButton.toggled.connect( self.handleExportLocationOptionChanged )
            
            self.drawer.outputDirChooseButton.clicked.connect( self.chooseNewExportDirectory )        
            self.drawer.outputSuffixEdit.textEdited.connect( self.handleNewOutputSuffix )
            
            self.drawer.exportAllButton.clicked.connect( self.exportAllResults )
            self.drawer.deleteAllButton.clicked.connect( self.deleteAllResults )

    def initCentralUic(self):
        """
        Load the GUI from the ui file into this class and connect it with event handlers.
        """
        with Tracer(traceLogger):
            # Load the ui file into this class (find it in our own directory)
            localDir = os.path.split(__file__)[0]
            uic.loadUi(localDir+"/batchIo.ui", self)
    
            self.tableWidget.resizeRowsToContents()
            self.tableWidget.resizeColumnsToContents()
            self.tableWidget.setAlternatingRowColors(True)
            self.tableWidget.setShowGrid(False)
            self.tableWidget.horizontalHeader().setResizeMode(0, QHeaderView.Interactive)
            
            self.tableWidget.horizontalHeader().resizeSection(Column.Dataset, 200)
            self.tableWidget.horizontalHeader().resizeSection(Column.ExportLocation, 250)
            self.tableWidget.horizontalHeader().resizeSection(Column.Action, 100)
    
            self.tableWidget.verticalHeader().hide()
    
            # Set up handlers
            self.tableWidget.itemSelectionChanged.connect(self.handleTableSelectionChange)
        
    def handleExportLocationOptionChanged(self):
        """
        The user has changed the export directory option (radio buttons).
        """
        with Tracer(traceLogger):
            saveWithInput = self.drawer.saveWithInputButton.isChecked()
            if saveWithInput:
                # Set to '', which means export data is stored in the input data directory
                self.mainOperator.ExportDirectory.setValue('')
            else:
                self.mainOperator.ExportDirectory.setValue(self.chosenExportDirectory)
    
            for index, slot in enumerate(self.mainOperator.OutputDataPath):
                self.updateTableForSlot(slot)
    
    def chooseNewExportDirectory(self):
        """
        The user wants to choose a new export directory.
        """
        with Tracer(traceLogger):
            # Launch the "Open File" dialog
            directoryName = QFileDialog.getExistingDirectory(self, "Export Directory", os.path.abspath(__file__))
    
            # Stop now if the user canceled
            if directoryName.isNull():
                return
            
            self.chosenExportDirectory = str( directoryName )
            self.drawer.outputDirEdit.setText( directoryName )
    
            # Auto-check the radio button for this option if necessary
            if not self.drawer.saveToDirButton.isChecked():
                self.drawer.saveToDirButton.setChecked(True)
            else:
                self.handleExportLocationOptionChanged()
    
    def handleNewOutputSuffix(self):
        with Tracer(traceLogger):
            suffix = str( self.drawer.outputSuffixEdit.text() )
            
            self.mainOperator.Suffix.setValue( suffix )
    
            # Update every row of the GUI        
            for index, slot in enumerate(self.mainOperator.OutputDataPath):
                self.updateTableForSlot(slot)

    def getSlotIndex(self, multislot, subslot ):
        with Tracer(traceLogger):
            # Which index is this slot?
            for index, slot in enumerate(multislot):
                if slot == subslot:
                    return index
            return -1

    def updateTableForSlot(self, slot):
        with Tracer(traceLogger):
            """
            Update the table row that corresponds to the given slot of the top-level operator (could be either input slot)
            """
            row = self.getSlotIndex( self.mainOperator.OutputDataPath, slot )
            assert row != -1, "Unknown input slot!"
            
            datasetPath = self.mainOperator.DatasetPath[row].value
            outputDataPath = self.mainOperator.OutputDataPath[row].value
                    
            self.tableWidget.setItem( row, Column.Dataset, QTableWidgetItem(datasetPath) )
            self.tableWidget.setItem( row, Column.ExportLocation, QTableWidgetItem( outputDataPath ) )
    
            exportNowButton = QPushButton("Export")
            exportNowButton.clicked.connect( bind(self.exportResultsForSlot, self.mainOperator.ExportResult[row] ) )
            self.tableWidget.setCellWidget( row, Column.Action, exportNowButton )

    def updateDrawerGuiFromOperatorSettings(self, *args):
        with Tracer(traceLogger):
            if self.mainOperator.Suffix.ready():
                self.drawer.outputSuffixEdit.setText( self.mainOperator.Suffix.value )
            
            if self.mainOperator.ExportDirectory.ready():
                self.drawer.outputDirEdit.setText( self.mainOperator.ExportDirectory.value )
                self.drawer.saveToDirButton.setChecked( self.mainOperator.ExportDirectory.value != '' )        
                self.drawer.saveWithInputButton.setChecked( self.mainOperator.ExportDirectory.value == '' )        

    def handleTableSelectionChange(self):
        """
        Any time the user selects a new item, select the whole row.
        """
        with Tracer(traceLogger):
            # Figure out which dataset to remove
            selectedItemRows = set()
            selectedRanges = self.tableWidget.selectedRanges()
            for rng in selectedRanges:
                for row in range(rng.topRow(), rng.bottomRow()+1):
                    selectedItemRows.add(row)
            
            # Disconnect from selection change notifications while we do this
            self.tableWidget.itemSelectionChanged.disconnect(self.handleTableSelectionChange)
            for row in selectedItemRows:
                self.tableWidget.selectRow(row)
                
            # Reconnect now that we're finished
            self.tableWidget.itemSelectionChanged.connect(self.handleTableSelectionChange)
        
    def exportResultsForSlot(self, slot):
        with Tracer(traceLogger):
            result = slot.value
            if not result:
                print "Failed to export a result."
    
    def exportAllResults(self):
        with Tracer(traceLogger):
            def exportClosure():
                with Tracer(traceLogger):
                    # Don't let anyone change the classifier while we're exporting...
                    self.guiControlSignal.emit( ilastikshell.applet.ControlCommand.DisableUpstream )
                    
                    # Also disable this applet's controls
                    self.guiControlSignal.emit( ilastikshell.applet.ControlCommand.DisableSelf )
                    
                    for slot in self.mainOperator.ExportResult:
                        result = slot.value
                        if not result:
                            print "Failed to export a result:" + self.mainOperator.OutputDataPath
                    
                    # Now that we're finished, it's okay to use the other applets again.
                    self.guiControlSignal.emit( ilastikshell.applet.ControlCommand.Pop ) # Enable ourselves
                    self.guiControlSignal.emit( ilastikshell.applet.ControlCommand.Pop ) # Enable the others we disabled
    
            # Do this in a separate thread so the UI remains responsive
            exportThread = threading.Thread(target=exportClosure, name="BatchIOExportThread")
            exportThread.start()

    def deleteAllResults(self):
        with Tracer(traceLogger):
            for slot in self.mainOperator.OutputDataPath:
                os.remove(slot.value)














