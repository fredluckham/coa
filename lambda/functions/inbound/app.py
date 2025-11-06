import boto3
import json
from os import environ
from loglib import logger, tracer, log_event
from client_table_model import check_table
from aws_lambda_powertools.utilities.typing import LambdaContext
from pynamodb.models import Model
from pynamodb.attributes import UnicodeAttribute, MapAttribute, ListAttribute, BooleanAttribute, NumberAttribute
from pynamodb.indexes import GlobalSecondaryIndex, AllProjection
from pynamodb.exceptions import DoesNotExist

sfn     = boto3.client('stepfunctions')
SFN_ARN = environ.get('step_function_arn')
ENV = environ.get('env')


class ProvisioningParameter(MapAttribute):
    Key = UnicodeAttribute()
    Value = UnicodeAttribute()


class ProvisionedProduct(MapAttribute):
    ProvisionedProductId = UnicodeAttribute(null=True)
    ProvisionedProductName = UnicodeAttribute(null=True)
    ProductId = UnicodeAttribute(null=True)
    ProvisioningArtifactId = UnicodeAttribute(null=True)
    PathId = UnicodeAttribute(null=True)
    Region = UnicodeAttribute(null=True)

    ProvisioningParameters = ListAttribute(of=ProvisioningParameter, null=True)


class AccessConfiguration(MapAttribute):
    StackPrefixOverride = UnicodeAttribute(null=True)
    ReadOnlyRoleName = UnicodeAttribute()
    FullAccessRoleName = UnicodeAttribute(null=True)
    ServiceCatalogDeploymentRoleName = UnicodeAttribute(null=True)
    ExternalId = UnicodeAttribute()


class KeycloakConfiguration(MapAttribute):
    RoleArn = UnicodeAttribute()
    RoleType = UnicodeAttribute()
    SamlProviderArn = UnicodeAttribute()


class SpendDataEntry(MapAttribute):
    estimated = BooleanAttribute()
    amount = NumberAttribute()


class AccountConfigStatus(MapAttribute):
    RootMfaEnabled = BooleanAttribute(null=True)
    RootAccessKeyPresent = BooleanAttribute(null=True)
    RootAccessKeyUsed = BooleanAttribute(null=True)
    SsoEnabled = BooleanAttribute(null=True)
    ControlTowerEnabled = BooleanAttribute(null=True)
    ControlTowerLandingZone = UnicodeAttribute(null=True)
    AccountAlias = UnicodeAttribute(null=True)


class CustomerIDIndex(GlobalSecondaryIndex):
    class Meta:
        index_name = "CustomerID-index"
        projection = AllProjection()

    CustomerID = UnicodeAttribute(hash_key=True)


class ReburaManagedAccount(Model):

    class Meta:
        table_name = f"{ENV}-rebura-ops-hub-accounts"
        region = 'eu-west-1'

    customer_index = CustomerIDIndex()

    AWSAccountID = UnicodeAttribute(hash_key=True)
    CustomerID = UnicodeAttribute(range_key=True)

    EnrollmentTime = UnicodeAttribute(null=True)
    EnrollmentUpdateTime = UnicodeAttribute(null=True)
    OffboardingTime = UnicodeAttribute(null=True)

    Description = UnicodeAttribute(null=True)
    Name = UnicodeAttribute(null=True)
    SafeName = UnicodeAttribute(null=True)

    Status = UnicodeAttribute(null=True)

    Deployable = BooleanAttribute()
    KeycloakConfigured = BooleanAttribute()

    AccessConfiguration = AccessConfiguration(null=True)
    KeycloakConfiguration = ListAttribute(of=KeycloakConfiguration, null=True)

    ProvisionedProducts = ListAttribute(of=ProvisionedProduct, null=True)

    SpendData = MapAttribute(of=SpendDataEntry, null=True)
    SpendDataUpdated = UnicodeAttribute(null=True)

    CostByServiceData = UnicodeAttribute(null=True)
    CostByServiceDataUpdated = UnicodeAttribute(null=True)

    ConfigStatus = AccountConfigStatus(null=True)

    FinopsAuditData = UnicodeAttribute(null=True)
    FinopsAuditDataUpdated = UnicodeAttribute(null=True)

def check_table(account_id: str, customer_id: str) -> bool:
    """
    Retrieve a single customer by account ID from the DynamoDB table.
    """
    try:
        account = ReburaManagedAccount.get(account_id, customer_id)
        logger.info(f"Account with ID: {account_id} is present in table")
        return True
    except DoesNotExist:
        logger.error(f"account with ID {account_id} not found.")
        return False
    except Exception as e:
        logger.error(f"Error fetching account with ID {account_id}: {e}")
        return False

@logger.inject_lambda_context(log_event=log_event)
@tracer.capture_lambda_handler
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    results = []
    for record in event["Records"]:
        try:
            body = record["body"]
            data = json.loads(body)
            logger.info(data)
            if check_customer_table(data):
                enriched_event = extract_event_data(data, context)
                trigger_step_function(enriched_event, context)
                results.append({"messageId": record["messageId"], "status": "processed"})
            else:
                logger.warning(
                    f"Unable to locate account with ID {data.get('account', 'unknown')}. "
                    "Have you enrolled the client in KeyCloak yet?"
                )
                results.append({"messageId": record["messageId"], "status": "skipped"})
        except Exception as e:
            logger.error(f"Error processing record {record.get('messageId')}: {e}")
            results.append({"messageId": record.get("messageId"), "status": "error"})
            # Re-raise if you want the batch to be retried:
            raise

    return {"records": results}

def trigger_step_function(event: dict, context: LambdaContext) -> dict:
    """
    Triggers an AWS Step Functions execution with the provided event and context data.

    Args:
        event (dict): The incoming event data.
        context (LambdaContext): The Lambda execution context.

    Returns:
        dict: The event data with execution details if successful, or an error message.
    """
    try:
        service_name = extract_event_service_detail(event)
        execution_name = f"{event.get('account', 'unknown')}-{service_name}-{event.get('id', 'unknown')}"
        response = sfn.start_execution(
            stateMachineArn=SFN_ARN,
            name=execution_name,
            input=json.dumps(event)
        )
        logger.append_keys(statusCode=200, executionArn=response['executionArn'])
        logger.info("Step Function execution started successfully.")
        return event 
    except Exception as e:
        logger.error(f"Error starting Step Function execution: {e}")
        raise

def extract_event_data(event: dict, context: LambdaContext) -> dict:
    """
    Extracts and adds metadata to the event, such as requestId from the Lambda execution context.

    Args:
        event (dict): The incoming event data.
        context (LambdaContext): The Lambda execution context.

    Returns:
        dict: The event data with added metadata.
    """
    try:
        metadata = {'requestId': context.aws_request_id}
        event['metadata'] = metadata
        return event
    except Exception as e:
        logger.error(f"Error in extract_event_data: {e}")
        raise

def extract_event_service_detail(event: dict) -> str:
    """
    Extracts the service value from the event detail.

    Args:
        event (dict): The incoming event data.

    Returns:
        str: The name of the service.
    """
    try:
        service_name = event.get('detail', {}).get('service')
        return service_name
    except Exception as e:
        logger.error(f"Error in extract_event_service_detail: {e}")
        raise

def check_customer_table(event: dict) -> bool:
    """
    Checks the keycloak clients table for matching account IDs.

    Args:
        event (dict): The incoming event data.

    Returns:
        bool.
    """
    try:
        account_id = event.get('account', 'unknown')
        customer_id = event['detail'].get('customerId', 'unknown')
        logger.info(f"Account ID: {account_id}")
        logger.info(f"Customer ID: {customer_id}")
        return check_table(account_id, customer_id)
    except Exception as e:
        logger.error(f"Error in check_customer_table: {e}")
        raise
