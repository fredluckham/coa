from os import environ
from pynamodb.models import Model
from pynamodb.attributes import UnicodeAttribute
from pynamodb.exceptions import DoesNotExist
from loglib import logger

table_name: str = environ.get('client_table', 'keycloak-dev-clients')
region: str     = environ.get('region', 'eu-west-1')

class ClientTable(Model):
    """
    A DynamoDB Stack
    """
    class Meta:
        table_name  = table_name
        region      = region

    RoleARN         = UnicodeAttribute(hash_key=True)
    Access          = UnicodeAttribute()
    AccountID       = UnicodeAttribute()
    Client          = UnicodeAttribute()
    RoleType        = UnicodeAttribute()
    SAMLProvider    = UnicodeAttribute()

def check_table(account_id: str) -> bool:
    """
    Retrieve a single customer by account ID from the DynamoDB table.
    """
    try:
        role_arn = f"arn:aws:iam::{account_id}:role/reb-support-read-only"
        account = ClientTable.get(role_arn)
        logger.info(f"Account with ID: {account_id} is present in table: {account}")
        return True
    except DoesNotExist:
        logger.error(f"account with ID {account_id} not found.")
        return False
    except Exception as e:
        logger.error(f"Error fetching account with ID {account_id}: {e}")
        return False