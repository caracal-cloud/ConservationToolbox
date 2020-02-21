
import arcpy

class FindStuff(object):
    def __init__(self):
        self.label = "Find Stuff BOYYYY"
        self.description = "Finds stuff."
        self.canRunInBackground = False

    def getParameterInfo(self):

        input_layer = arcpy.Parameter(
            displayName="Input Layer",
            name="input_layer",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        input_layer.filter.list = ["POINT"]

        return [input_layer]

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        return




