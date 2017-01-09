###############################################################################
#   ilastik: interactive learning and segmentation toolkit
#
#       Copyright (C) 2011-2014, the ilastik developers
#                                <team@ilastik.org>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# In addition, as a special exception, the copyright holders of
# ilastik give you permission to combine ilastik with applets,
# workflows and plugins which are not covered under the GNU
# General Public License.
#
# See the LICENSE file for details. License information is also available
# on the ilastik web site at:
#           http://ilastik.org/license.html
###############################################################################
import numpy as np

from ilastik.workflow import Workflow

from ilastik.applets.dataSelection import DataSelectionApplet
from ilastik.applets.seeds.seedsApplet import SeedsApplet
from ilastik.applets.watershedSegmentation.watershedSegmentationApplet import WatershedSegmentationApplet
from ilastik.applets.dataExport.dataExportApplet import DataExportApplet
from ilastik.applets.batchProcessing import BatchProcessingApplet

from lazyflow.graph import Graph

class WatershedSegmentationWorkflow(Workflow):
    # name that will be displayed when opening a new project
    workflowName = "Watershed Segmentation ['Raw Data', 'Boundaries', 'Seeds (optional)']"
    workflowDescription = "A workflow that uses a seeded watershed applets for algorithmic calculations"
    defaultAppletIndex = 0 # show DataSelection (first applet) by default

    # give your input data a number, so the group can be found for them
    DATA_ROLE_RAW           = 0
    DATA_ROLE_BOUNDARIES    = 1
    DATA_ROLE_SEEDS         = 2
    ROLE_NAMES = ['Raw Data', 'Object Boundaries', 'Seeds']

    #define the names of the data, that can be exported in the DataExport Applet
    EXPORT_NAMES = ['Corrected Seeds', 'Watershed']

    @property
    def applets(self):
        return self._applets

    @property
    def imageNameListSlot(self):
        return self.dataSelectionApplet.topLevelOperator.ImageName

    def __init__(self, shell, headless, workflow_cmdline_args, project_creation_workflow, *args, **kwargs):
        # Create a graph to be shared by all operators
        graph = Graph()

        super(WatershedSegmentationWorkflow, self).__init__( \
                shell, headless, workflow_cmdline_args, project_creation_workflow, graph=graph, *args, **kwargs)
        ############################################################
        # Init and add the applets
        ############################################################
        self._applets = []

        # -- DataSelection applet
        #
        self.dataSelectionApplet = DataSelectionApplet(self, "Input Data", "Input Data", "Input Data")

        # Dataset inputs
        opDataSelection = self.dataSelectionApplet.topLevelOperator
        opDataSelection.DatasetRoles.setValue( self.ROLE_NAMES )

        # -- Seeds applet
        #
        self.seedsApplet = SeedsApplet(self, "Seeds", "SeedsGroup")

        # -- WatershedSegmentation applet
        #
        # ( workflow=self, guiName='', projectFileGroupName='' )
        self.watershedSegmentationApplet = WatershedSegmentationApplet(self, "Watershed", "WatershedSegmentation")

        # -- DataExport applet
        #
        self.dataExportApplet = DataExportApplet(self, "Data Export")

        # Configure global DataExport settings
        opDataExport = self.dataExportApplet.topLevelOperator
        opDataExport.WorkingDirectory.connect( opDataSelection.WorkingDirectory )
        opDataExport.SelectionNames.setValue( self.EXPORT_NAMES )

        #TODO add the labelNames and their colors for export as well
        '''
        self.dataExportApplet = PixelClassificationDataExportApplet(self, "Prediction Export")
        opDataExport = self.dataExportApplet.topLevelOperator
        opDataExport.PmapColors.connect( opClassify.PmapColors )
        opDataExport.LabelNames.connect( opClassify.LabelNames )
        opDataExport.WorkingDirectory.connect( opDataSelection.WorkingDirectory )
        opDataExport.SelectionNames.setValue( self.EXPORT_NAMES )        
        '''




        # -- BatchProcessing applet
        #
        self.batchProcessingApplet = BatchProcessingApplet(self,
                                                           "Batch Processing",
                                                           self.dataSelectionApplet,
                                                           self.dataExportApplet)

        # -- Expose applets to shell
        self._applets.append(self.dataSelectionApplet)
        self._applets.append(self.watershedSegmentationApplet)
        self._applets.append(self.dataExportApplet)
        self._applets.append(self.batchProcessingApplet)

        # -- Parse command-line arguments
        #    (Command-line args are applied in onProjectLoaded(), below.)
        if workflow_cmdline_args:
            self._data_export_args, unused_args = self.dataExportApplet.parse_known_cmdline_args( workflow_cmdline_args )
            self._batch_input_args, unused_args = self.dataSelectionApplet.parse_known_cmdline_args( unused_args, role_names )
        else:
            unused_args = None
            self._batch_input_args = None
            self._data_export_args = None

        if unused_args:
            logger.warn("Unused command-line args: {}".format( unused_args ))

    def connectLane(self, laneIndex):
        """
        Override from base class.
        Connect the output and the input of each applet with each other
        """

        # get the correct image-lane
        opDataSelection         = self.dataSelectionApplet.topLevelOperator.getLane(laneIndex)
        opSeeds                 = self.seedsApplet.topLevelOperator.getLane(laneIndex)
        opWatershedSegmentation = self.watershedSegmentationApplet.topLevelOperator.getLane(laneIndex)
        opDataExport            = self.dataExportApplet.topLevelOperator.getLane(laneIndex)

        # seeds inputs
        opSeeds.RawData.connect(    opDataSelection.ImageGroup[self.DATA_ROLE_RAW] )
        opSeeds.Boundaries.connect( opDataSelection.ImageGroup[self.DATA_ROLE_BOUNDARIES] )
        opSeeds.Seeds.connect(      opDataSelection.ImageGroup[self.DATA_ROLE_SEEDS] )

        # watershed inputs
        opWatershedSegmentation.RawData.connect(    opDataSelection.ImageGroup[self.DATA_ROLE_RAW] )
        opWatershedSegmentation.Boundaries.connect( opDataSelection.ImageGroup[self.DATA_ROLE_BOUNDARIES] )
        #TODO get the Seeds from opSeeds
        opWatershedSegmentation.Seeds.connect(      opDataSelection.ImageGroup[self.DATA_ROLE_SEEDS] )
        #TODO get the Seeds from opSeeds
        opWatershedSegmentation.CorrectedSeedsIn.connect( opDataSelection.ImageGroup[self.DATA_ROLE_SEEDS] )

        # DataExport inputs
        opDataExport.RawData.connect(       opDataSelection.ImageGroup[self.DATA_ROLE_RAW] )
        opDataExport.RawDatasetInfo.connect(opDataSelection.DatasetGroup[self.DATA_ROLE_RAW] )        


        # connect the output of the watershed-applet to the inputs of the data-export
        opDataExport.Inputs.resize( len(self.EXPORT_NAMES) )
        # 0. use the user manipulated seeds for this 
        # 1. use the cached output of the watershed algorithm, so that reloading the project 
        #    and exporting it will work without an additional calculation
        opDataExport.Inputs[0].connect( opWatershedSegmentation.CorrectedSeedsOut )
        opDataExport.Inputs[1].connect( opWatershedSegmentation.WSCCOCachedOutput )
        for slot in opDataExport.Inputs:
            assert slot.partner is not None
        #for more information, see ilastik.org/lazyflow/advanced.html OperatorWrapper class
        
    def onProjectLoaded(self, projectManager):
        """
        Overridden from Workflow base class.  Called by the Project Manager.
        
        If the user provided command-line arguments, use them to configure 
        the workflow inputs and output settings.
        """
        # Configure the data export operator.
        if self._data_export_args:
            self.dataExportApplet.configure_operator_with_parsed_args( self._data_export_args )

        if self._headless and self._batch_input_args and self._data_export_args:
            logger.info("Beginning Batch Processing")
            self.batchProcessingApplet.run_export_from_parsed_args(self._batch_input_args)
            logger.info("Completed Batch Processing")

    def handleAppletStateUpdateRequested(self):
        """
        Overridden from Workflow base class
        Called when an applet has fired the :py:attr:`Applet.appletStateUpdateRequested`
        """
        opDataSelection = self.dataSelectionApplet.topLevelOperator
        opDataExport = self.dataExportApplet.topLevelOperator
        opWatershedSegmentation = self.watershedSegmentationApplet.topLevelOperator

        # If no data, nothing else is ready.
        input_ready = len(opDataSelection.ImageGroup) > 0 and not self.dataSelectionApplet.busy

        # The user isn't allowed to touch anything while batch processing is running.
        batch_processing_busy = self.batchProcessingApplet.busy

        self._shell.setAppletEnabled( self.dataSelectionApplet,\
                not batch_processing_busy )
        self._shell.setAppletEnabled( self.watershedSegmentationApplet,\
                not batch_processing_busy and input_ready )
        self._shell.setAppletEnabled( self.dataExportApplet,\
                not batch_processing_busy and input_ready ) #TODO (add the watershedSegementation here)
                #and opWatershedSegmentation.Superpixels.ready())
        self._shell.setAppletEnabled( self.batchProcessingApplet,\
                not batch_processing_busy and input_ready )

        # Lastly, check for certain "busy" conditions, during which we
        #  should prevent the shell from closing the project.
        busy = False
        busy |= self.dataSelectionApplet.busy
        busy |= self.watershedSegmentationApplet.busy
        busy |= self.dataExportApplet.busy
        busy |= self.batchProcessingApplet.busy
        self._shell.enableProjectChanges( not busy )