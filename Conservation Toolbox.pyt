
import arcpy
#from tools import FindBursts --- this kind of import was not updating in ArcGIS Pro, grrr!


class Toolbox(object):
    def __init__(self):
        self.label = "Conservation Toolbox"
        self.alias = "ConservationToolbox"
        self.tools = [FindBursts]


class FindBursts(object):
    def __init__(self):
        self.label = "Find Bursts"
        self.description = "Finds abnormal bursts over a specified period of time."
        self.canRunInBackground = False
        self.max_day_range = 60
        self.max_burst_period = self.max_day_range * 24

    def getParameterInfo(self):

        input_layer = arcpy.Parameter(
            displayName="Input Layer",
            name="input_layer",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        input_layer.filter.list = ["POINT"]  # only point supported right, but could add polylines

        individual_field = arcpy.Parameter(
            displayName="ID Field",
            name="individual_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        individual_field.parameterDependencies = [input_layer.name]

        date_field = arcpy.Parameter(
            displayName="Date Field",
            name="date_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        date_field.parameterDependencies = [input_layer.name]

        start_date = arcpy.Parameter(
            displayName="Start Date",
            name="start_date",
            datatype="GPDate",
            parameterType="Required",
            direction="Input")

        end_date = arcpy.Parameter(
            displayName="End Date",
            name="end_date",
            datatype="GPDate",
            parameterType="Required",
            direction="Input")

        burst_period = arcpy.Parameter(
            displayName="Burst Period (Hours)",
            name="burst_period",
            datatype="GPLong",
            parameterType="Required",
            direction="Input")
        burst_period.value = 24

        species = arcpy.Parameter(
            displayName="Species",
            name="species",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        species.filter.type = "ValueList"
        species.filter.list = ['elephant']  # add other species later
        species.value = "elephant"  # temporary - elephant default to make testing faster

        subspecies = arcpy.Parameter(
            displayName="Subspecies",
            name="subspecies",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        subspecies.filter.type = "ValueList"
        subspecies.filter.list = []
        subspecies.value = "savannah" # temporary - savannah default to make testing faster

        output_layer = arcpy.Parameter(
            displayName="Output Layer",
            name="out_layer",
            datatype="GPFeatureLayer",
            parameterType="Derived",
            direction="Output")
        output_layer.parameterDependencies = [input_layer.name]

        return [
            input_layer,
            individual_field,
            date_field,
            start_date,
            end_date,
            burst_period,
            species,
            subspecies,
            output_layer
        ]

    def updateParameters(self, parameters):

        input_layer, id_field, date_field, start_date, end_date, burst_period, species, subspecies = (
            parameters[0],
            parameters[1],
            parameters[2],
            parameters[3],
            parameters[4],
            parameters[5],
            parameters[6],
            parameters[7],
        )

        # set the subspecies options based on species, only elephant support right now
        if species.valueAsText == 'elephant':
            subspecies.enabled = True
            subspecies.filter.list = ['forest', 'hybrid', 'savannah']
        else:
            subspecies.enabled = False
            subspecies.value = None

    def updateMessages(self, parameters):

        input_layer, id_field, date_field, start_date, end_date, burst_period, species = (
            parameters[0],
            parameters[1],
            parameters[2],
            parameters[3],
            parameters[4],
            parameters[5],
            parameters[6],
        )

        # make sure burst period does not exceed max_burst_period
        if burst_period.value and burst_period.value > self.max_burst_period:
            burst_period.setErrorMessage(f"Burst Period must be less than {self.max_burst_period} hours")
        else:
            burst_period.clearMessage()

        # make sure start is before end and difference does not exceed max_day_range
        if start_date.value and end_date.value:
            if end_date.value <= start_date.value:
                start_date.setErrorMessage("Start Date must be before End Date")
                end_date.setErrorMessage("End Date must be after Start Date")
            elif (end_date.value-start_date.value).days >= self.max_day_range:
                start_date.setErrorMessage(f"Start Date must be less than {self.max_day_range} days before End Date")
                end_date.setErrorMessage(f"End Date must be less than {self.max_day_range} days after Start Date")
            else:
                start_date.clearMessage()
                end_date.clearMessage()
        else:
            start_date.clearMessage()
            end_date.clearMessage()

    def execute(self, parameters, messages):

        input_layer, id_field, date_field, start_date, end_date, burst_period, species, output_layer = (
            parameters[0].valueAsText,
            parameters[1].valueAsText,
            parameters[2].valueAsText,
            parameters[3].value,  # datetime
            parameters[4].value,  # datetime
            parameters[5].valueAsText,
            parameters[6].valueAsText,
            parameters[7].valueAsText + ' (Bursts)'
        )

        # print parameters
        self._add_message(f'Input layer: {input_layer}')
        self._add_message(f'ID field: {id_field}')
        self._add_message(f'Date range: {str(start_date)} - {str(end_date)}')
        self._add_message(f'Date field: {date_field}')
        self._add_message(f'Burst period: {burst_period}')
        self._add_message(f'Species: {species}')
        self._add_message(f'Output layer: {output_layer}')

        # get project and active map
        aprx = arcpy.mp.ArcGISProject('CURRENT')
        map = aprx.activeMap  # map.listLayers

        # get ordered points with date ranges
        sql_clause = (None, f'ORDER BY {date_field} ASC')
        where_clause = f'{date_field} BETWEEN TIMESTAMP \'{str(start_date)}\' AND TIMESTAMP \'{str(end_date)}\''
        cursor = arcpy.da.SearchCursor(
            input_layer,
            field_names=[id_field, date_field, 'SHAPE@'],
            sql_clause=sql_clause,
            where_clause=where_clause
        )

        # create dictionary of individuals and their points
        individuals = dict()
        for row in cursor:
            _id, _datetime, geometry = row[0], row[1], row[2]
            if _id not in individuals.keys():
                individuals[_id] = list()

            individuals[_id].append({
                'id': _id,
                'datetime': _datetime,
                'geometry': geometry,  # PointGeometry
            })

        # temporarily just testing distance calculations
        for _id, points in individuals.items():
            ordered_points = [p['geometry'] for p in points]
            distance = self._calculate_distance(ordered_points)
            self._add_message(f"{_id} moved {round(distance/1000, 2)} kilometers")

 