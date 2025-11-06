import json
import jmespath
import boto3
from os import environ
from rolelib import assume_role, retrieve_session_credentials
from alarmlib import config
from loglib import logger, tracer, log_event
from aws_lambda_powertools.utilities.typing import LambdaContext

# Retrieve environment variables with fallbacks
sfn_arn = environ.get('step_function_arn', 'default_stepfunction_arn')

# Initialize the sfn boto3 client with config
sfn = boto3.client('stepfunctions', config=config)

@logger.inject_lambda_context(log_event=log_event)
@tracer.capture_lambda_handler
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    """
    AWS Lambda handler that processes the incoming event to delete alarms based on event data.

    Args:
        event (dict): The event data containing the service information.
        context (LambdaContext): The Lambda execution context.

    Returns:
        dict: The event with added deleted alarm list.
    """
    try:
        session = retrieve_session_credentials(event, assume_role(event))
        list_executions(event)
        delete_alarms(event, session)
        return event
    except Exception as e:
        logger.error(f"Error in lambda_handler: {e}")
        raise


def list_executions(event: dict) -> None:
    """
    Lists running Step Function executions and checks their relevance to the event.

    Args:
        event (dict): The event data containing resource information.
    """
    response = sfn.list_executions(
        stateMachineArn=sfn_arn,
        statusFilter='RUNNING',
        maxResults=1000,
    )
    logger.info(f"Running Executions: {response}")
    for execution in response['executions']:
        execution_details = describe_execution(execution['executionArn'])
        logger.info(f"Execution Details: {execution_details}")
        if event['resource_arn'] in execution_details['resources'] and "Tag Change on Resource" in execution_details['detail-type']:
            check_execution_tag(execution['executionArn'], execution_details)
        else:
            logger.info("No matching execution found")


def describe_execution(execution_arn: str) -> dict:
    """
    Describes a Step Function execution and returns its input.

    Args:
        execution_arn (str): The ARN of the Step Function execution.

    Returns:
        dict: The execution input details.
    """
    response = sfn.describe_execution(executionArn=execution_arn)
    return json.loads(response['input'])


def check_execution_tag(execution_arn: str, execution_details: dict) -> None:
    """
    Checks if the monitored tag value is set to 'Yes' and stops the execution if true.

    Args:
        execution_arn (str): The ARN of the Step Function execution.
        execution_details (dict): Details of the execution input.
    """
    tag_value = jmespath.search("detail.tags.IsMonitored", execution_details)
    logger.info(f"Tag Value: {tag_value}")
    if tag_value == 'Yes':
        logger.info(f"Stopping Execution: {execution_details}")
        stop_execution(execution_arn)


def stop_execution(execution_arn: str) -> None:
    """
    Stops a Step Function execution.

    Args:
        execution_arn (str): The ARN of the Step Function execution.
    """
    sfn.stop_execution(executionArn=execution_arn)


def delete_alarms(event: dict, session: boto3.Session) -> None:
    """
    Deletes CloudWatch alarms associated with the resource in the event.

    Args:
        event (dict): The event data containing resource information.
        session (boto3.Session): The session object to create AWS clients.
    """
    logger.info(f"Deleting alarms for: {event['resource_id']}")
    cloudwatch = session.client('cloudwatch', region_name=event['region'], config=config)
    response = cloudwatch.describe_alarms(
        AlarmNamePrefix=f"{event['account_alias']}-{event['account']}-{event['service']}-{event['resource_type']}-{event['resource_id']}",
        AlarmTypes=['MetricAlarm']
    )
    alarms = response['MetricAlarms']
    alarm_names = [alarm['AlarmName'] for alarm in alarms]
    logger.info(f"Deleting alarms: {alarm_names}")
    cloudwatch.delete_alarms(AlarmNames=alarm_names)
