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
dynamo_table: str    = environ.get('monitored_resources_table', 'default_table')
region: str          = environ.get('region', 'eu-west-1')

# Define the PynamoDB model for the DynamoDB table
class MonitoredResourcesTable(Model):
    class Meta:
        table_name = dynamo_table
        region = region

    account_id = UnicodeAttribute(hash_key=True)
    resource_id = UnicodeAttribute(range_key=True)
    arn = UnicodeAttribute(null=False)
    arn_prefix = UnicodeAttribute(null=False)
    partition = UnicodeAttribute(null=False)
    service = UnicodeAttribute(null=False)
    region = UnicodeAttribute(null=True)
    resource_type = UnicodeAttribute(null=False)
    ttl = NumberAttribute(null=True)