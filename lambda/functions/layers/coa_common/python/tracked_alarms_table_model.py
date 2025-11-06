from os import environ
from pynamodb.models import Model
from pynamodb.attributes import (
    UnicodeAttribute,
    BooleanAttribute,
    NumberAttribute,
    ListAttribute
)

# Retrieve environment variables with defaults
app_name: str        = environ.get('app', 'default_app')
dynamo_table: str    = environ.get('tracked_alarms_table', 'default_table')
region: str          = environ.get('region', 'eu-west-1')

# Define the PynamoDB model for the DynamoDB table
class TrackedAlarmsTable(Model):
    class Meta:
        table_name = dynamo_table
        region = region

    account_id = UnicodeAttribute(hash_key=True)
    alarm_name = UnicodeAttribute(range_key=True)
    alarm_description = UnicodeAttribute(null=True)
    alarm_arn = UnicodeAttribute(null=False)
    service = UnicodeAttribute(null=False)
    region = UnicodeAttribute(null=True)
    resource_type = UnicodeAttribute(null=False)
    namespace = UnicodeAttribute(null=False)
    metric = UnicodeAttribute(null=False)
    level = UnicodeAttribute(null=False)
    resource_id = UnicodeAttribute(null=False)
    resource_arn = UnicodeAttribute(null=False)
    state_value = UnicodeAttribute(null=True)
    ttl = NumberAttribute(null=True)