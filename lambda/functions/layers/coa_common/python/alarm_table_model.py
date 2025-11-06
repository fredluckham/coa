from os import environ
from pynamodb.models import Model
from pynamodb.attributes import (
    UnicodeAttribute,
    BooleanAttribute,
    NumberAttribute,
    ListAttribute
)
from loglib import logger

# Retrieve environment variables with defaults
app_name: str        = environ.get('app', 'default_app')
dynamo_table: str    = environ.get('alarm_table', 'default_table')
region: str          = environ.get('region', 'eu-west-1')

# Define the PynamoDB model for the DynamoDB table
class AlarmConfigTable(Model):
    """
    Represents the AlarmData Configuration DynamoDB Table using PynamoDB.
    """
    class Meta:
        table_name  = dynamo_table
        region      = region

    service             = UnicodeAttribute(hash_key=True)
    metric_name         = UnicodeAttribute(range_key=True)
    namespace           = UnicodeAttribute(null=False)
    extended_statistic  = UnicodeAttribute(null=True)
    alarm_description   = UnicodeAttribute(null=False)
    comparison_operator = UnicodeAttribute(null=False)
    actions_enabled     = BooleanAttribute(null=False)
    thresholds          = ListAttribute(null=False)
    dimensions          = ListAttribute(null=False)
    datapoints_to_alarm = NumberAttribute(null=False, default=15)
    evaluation_periods  = NumberAttribute(null=False, default=15)
    period              = NumberAttribute(null=False, default=60)
    treat_missing_data  = UnicodeAttribute(null=False, default="breaching")
    statistic           = UnicodeAttribute(null=True, default="Average")

def load_table_item(service_name: str, metric: str) -> object:
    """
    Loads an item from the AlarmConfigTable by service name and metric.
    
    Args:
        service_name (str): The name of the service.
        metric (str): The metric name.

    Returns:
        object: The item retrieved from the table, or None if not found or an error occurred.
    """
    try:
        logger.info(f"Fetching item for Service: {service_name}, Metric: {metric}")
        item = AlarmConfigTable.get(service_name, metric)
        logger.info(f"Retrieved item: {item}")
        return item
    except AlarmConfigTable.DoesNotExist:
        logger.error(f"Item does not exist for Service: {service_name}, Metric: {metric}")
        return None
    except Exception as e:
        logger.error(f"Failed to load item for Service: {service_name}, Metric: {metric} - Error: {e}")
        return None
