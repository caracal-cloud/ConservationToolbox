
import arcpy
from datetime import datetime, timedelta
from dateutil.parser import parse
import os
import sys


# TODO: only when distributing update this vvv
# TODO: you can import these files once, but they don't refresh when developing...
#tools_dir = os.path.join(os.path.dirname(__file__), 'tools')
#sys.path.append(tools_dir)
# Do not compile .pyc files for the tool modules.
sys.dont_write_bytecode = True

#from FindBursts import FindBursts


class Toolbox(object):
    def __init__(self):
        self.label = "Conservation Toolbox"
        self.alias = "Conservation Toolbox"
        self.tools = [FindBursts]


class FindBursts(object):
    def __init__(self):
        self.label = "Find Bursts"
        self.description = "Finds abnormal bursts over a specified period of time."
        self.canRunInBackground = False
        self.max_day_range = 60
        self.max_burst_period = self.max_day_range * 24
        self.template_layer = os.path.join(os.path.dirname(__file__), "templates", "bursts_template.lyr")

    def getParameterInfo(self):

        input_layer = arcpy.Parameter(
            displayName="Input Layer!!!",
            name="input_layer",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        input_layer.filter.list = ["POINT"]
        input_layer.value = "garambaElephantsPosition"

        individual_field = arcpy.Parameter(
            displayName="ID Field", # TODO: should only be string type
            name="individual_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        individual_field.parameterDependencies = [input_layer.name]
        individual_field.value = "Provider" # TODO: the value might be different from the database field name

        date_field = arcpy.Parameter(
            displayName="Date Field",
            name="date_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        date_field.parameterDependencies = [input_layer.name]
        date_field.value = "Datetime of Last Signal"

        start_date = arcpy.Parameter(
            displayName="Start Date",
            name="start_date",
            datatype="GPDate",
            parameterType="Required",
            direction="Input")
        start_date.value = "2020-02-17 9:55:58 AM"

        end_date = arcpy.Parameter(
            displayName="End Date",
            name="end_date",
            datatype="GPDate",
            parameterType="Required",
            direction="Input")
        end_date.value = "2020-02-20 9:55:58 AM"

        burst_period = arcpy.Parameter(
            displayName="Burst Period (Hours)",
            name="burst_period",
            datatype="GPLong",
            parameterType="Required",
            direction="Input")
        burst_period.value = 36

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

        return [
            input_layer,
            individual_field,
            date_field,
            start_date,
            end_date,
            burst_period,
            species,
            subspecies,
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

        input_layer, id_field, date_field, start_date, end_date, burst_period, species = (
            parameters[0].valueAsText,
            parameters[1].valueAsText,
            parameters[2].valueAsText,
            parameters[3].value,  # datetime
            parameters[4].value,  # datetime
            parameters[5].value,
            parameters[6].valueAsText,
        )

        for param in parameters:
            messages.addMessage(f"{param.name} = {param.valueAsText}")

        aprx = arcpy.mp.ArcGISProject('CURRENT')
        mxd = aprx.activeMap

        feature_class = self._create_bursts_feature_class()
        layer = self._create_bursts_feature_layer(burst_period, species, feature_class)

        unique_ids = self._get_unique_ids(id_field, input_layer)
        messages.addMessage(f'{unique_ids}')

        id_to_max_length = dict()

        # loop through each individual
        for _id in unique_ids:
            messages.addMessage(f'_id: {_id}')

            # get all positions between the start and end date
            id_positions_cursor = self._get_id_positions_cursor(_id, start_date, end_date, date_field, id_field, input_layer)
            for id_pos in id_positions_cursor:
                # convert the start date to a datetime object
                current_start_date, point = id_pos[1], id_pos[2]
                if isinstance(current_start_date, str):
                    current_start_date = parse(current_start_date)

                current_end_date = current_start_date + timedelta(hours=burst_period)

                # get positions between current position and burst time in the future
                current_positions_cursor = self._get_id_positions_cursor(_id, current_start_date, current_end_date, date_field, id_field, input_layer)
                positions = list()
                points_array = arcpy.Array()
                for row in current_positions_cursor:
                    row_id, row_date, row_geometry = row[0], row[1], row[2]
                    positions.append(row_geometry)
                    points_array.add(row_geometry.firstPoint)

                if points_array.count > 0:

                    spatial_reference = arcpy.SpatialReference(4326)
                    polyline = arcpy.Polyline(points_array, spatial_reference)

                    if _id not in id_to_max_length.keys():
                        id_to_max_length[_id] = {
                            'distance': -1,
                            'insert_row': list()
                        }

                    distance = round(self._calculate_distance(positions), 2)
                    if distance > id_to_max_length[_id]['distance']:
                        messages.addMessage(f'{_id} - new longest burst - {distance}')
                        id_to_max_length[_id]['distance'] = distance
                        id_to_max_length[_id]['insert_row'] = [polyline, _id, current_start_date, distance]

                else:
                    messages.addMessage('no positions')

        insert_cursor = arcpy.da.InsertCursor(feature_class, ["SHAPE@", "Individual", "DatetimeStart", "DistanceKm"])
        for _id, value in id_to_max_length.items():
            if value['distance'] > 0:
                insert_cursor.insertRow(value['insert_row'])

        mxd.addLayer(layer)

        return

    def _add_message(self, message):
        # adds a message
        arcpy.AddMessage(message)

    # TODO: add typed arguments
    def _calculate_distance(self, ordered_list):
        """
        Calculates distance in meters of the ordered list of PointGeometry objects
        :param ordered_list: list of PointGeometry objects
        :return: distance in meters
        """

        total_distance = 0
        previous_point = None
        for point in ordered_list:
            if previous_point is not None:
                angle, distance = previous_point.angleAndDistanceTo(point)  # geodesic distance in meters
                total_distance += distance
            previous_point = point

        return total_distance

    def _create_bursts_feature_class(self):

        fc = arcpy.CreateFeatureclass_management(arcpy.env.workspace, "Bursts", "Polyline", spatial_reference=4326)[0]
        arcpy.AddField_management(fc, "Individual", "TEXT", field_length=200)
        arcpy.AddField_management(fc, "DatetimeStart", "DATE")
        arcpy.AddField_management(fc, "DistanceKm", "Double", field_precision=10, field_scale=2)
        return fc

    def _create_bursts_feature_layer(self, burst_period, species, feature_class):
        return arcpy.MakeFeatureLayer_management(feature_class, f"{species.title()} Bursts - {burst_period} hours")[0]

    def _get_unique_ids(self, id_field, input_layer):

        # TODO: possible issue with alias
        # TODO: testing
        id_field = 'provider'

        sql_clause = ('DISTINCT', f'ORDER BY {id_field} DESC')
        cursor = arcpy.da.SearchCursor(
            input_layer,
            field_names=[id_field],
            sql_clause=sql_clause,
        )

        unique_ids = [row[0] for row in cursor]
        return unique_ids


    def _get_id_positions_cursor(self, id, start_date, end_date, date_field, id_field, input_layer):

        # TODO: testing!
        date_field = 'lastsignal'
        id_field = 'provider'

        sql_clause = (None, f'ORDER BY {date_field} ASC')

        # TODO: is BETWEEN inclusive?
        where_clause = f'{id_field} = \'{id}\' AND {date_field} BETWEEN TIMESTAMP \'{str(start_date)}\' AND TIMESTAMP \'{str(end_date)}\''
        return arcpy.da.SearchCursor(
            input_layer,
            field_names=[id_field, date_field, 'SHAPE@'],
            sql_clause=sql_clause,
            where_clause=where_clause
        )