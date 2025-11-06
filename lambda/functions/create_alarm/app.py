import boto3
from typing import Any
from botocore.config import Config
from rolelib import assume_role, retrieve_session_credentials
from alarmlib import Alarms, AlarmData, for_each_threshold
from loglib import logger, tracer, log_event
from aws_lambda_powertools.utilities.typing import LambdaContext

# Configuration for retries
config = Config(
    retries={
        'max_attempts': 10,
        'mode': 'standard'
    }
)

@logger.inject_lambda_context(log_event=log_event)
@tracer.capture_lambda_handler
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    """
    AWS Lambda handler to generate alarms based on metric data.

    Args:
        event (dict): Input event data.
        context (LambdaContext): AWS Lambda context object.

    Returns:
        dict: Updated event with alarms added.
    """
    try:
        session = retrieve_session_credentials(event, assume_role(event))
        for alarm in event["alarm_config"]:
            create_alarm(event, session, alarm)
        return event
    except Exception as e:
        logger.error(f"Error in lambda_handler: {e}")
        raise

def create_alarm(event, session, alarm) -> None:
    """
    Creates a CloudWatch alarm based on the given parameters.

    Args:
        event (dict): Event data with account and resource information.
        cloudwatch (boto3.client): CloudWatch client instance.
        alarm_name (str): Name of the alarm.
        alarm_object (AlarmData): AlarmData configuration object.
        threshold_value (float): Threshold value for the alarm.
        level (str): Severity level of the alarm.
        action_topic_arn (list): List of action topic ARNs.

    Returns:
        None
    """
    try:
        cloudwatch: boto3.client = start_cloudwatch_session(event, session)
        cloudwatch.put_metric_alarm(
            AlarmName = alarm["alarm_name"],
            ComparisonOperator = alarm["comparison_operator"],
            EvaluationPeriods = int(alarm["evaluation_periods"]),
            DatapointsToAlarm = int(alarm["datapoints_to_alarm"]),
            MetricName = alarm["metric"],
            Namespace = alarm["namespace"],
            Period = int(alarm["period"]),
            Statistic = alarm["statistic"],
            Threshold = int(alarm["threshold"]),
            ActionsEnabled = alarm["actions_enabled"],
            OKActions = alarm["action_topic_arn"],
            AlarmActions = alarm["action_topic_arn"],
            AlarmDescription = alarm["alarm_description"],
            TreatMissingData = alarm["treat_missing_data"],
            Dimensions = alarm["dimensions"]
        )
        logger.info(f"Created alarm: {alarm["alarm_name"]}")
        # retrieve_alarm_arn(event, cloudwatch, alarm)
    except Exception as e:
        logger.error(f"Failed to create alarm {alarm["alarm_name"]}: {e}")
        raise


# def retrieve_alarm_arn(event, cloudwatch, alarm) -> None:
#     """
#     Retrieves the ARN of a created alarm and tags it.

#     Args:
#         event (dict): Event data with tagging information.
#         alarm_name (str): Name of the alarm.
#         cloudwatch (boto3.client): CloudWatch client instance.
#         alarm (AlarmData): AlarmData configuration object.
#         alarm.priority (str): Severity alarm.priority of the alarm.

#     Returns:
#         None
#     """
#     try:
#         response: dict = cloudwatch.describe_alarms(AlarmNames=[alarm["alarm_name"]])
#         alarm_arn: str = response['MetricAlarms'][0]['AlarmArn']
#         logger.info(f"Retrieved alarm ARN: {alarm_arn}")
#         tag_alarm(event, cloudwatch, alarm, alarm_arn)
#     except IndexError:
#         logger.error(f"Alarm {alarm["alarm_name"]} not found in describe_alarms response.")
#         raise
#     except Exception as e:
#         logger.error(f"Failed to retrieve alarm ARN for {alarm["alarm_name"]}: {e}")
#         raise


# def tag_alarm(event, cloudwatch, alarm, alarm_arn) -> None:
#     """
#     Tags a CloudWatch alarm with metadata.

#     Args:
#         event (dict): Event data for resource and alarm tagging.
#         alarm_name (str): Name of the alarm.
#         cloudwatch (boto3.client): CloudWatch client instance.
#         alarm (AlarmData): AlarmData configuration object.
#         alarm.priority (str): Severity alarm.priority of the alarm.
#         alarm_arn (str): ARN of the alarm to tag.

#     Returns:
#         None
#     """
#     try:
#         tag_list = [
#                 {'Key': 'Rebura:Alarm:Description', 'Value': alarm["alarm_description"]},
#                 {'Key': 'Rebura:Alarm:Service', 'Value': event['service']},
#                 {'Key': 'Rebura:Alarm:Type', 'Value': event['resource_type']},
#                 {'Key': 'Rebura:Alarm:Identifier', 'Value': event['resource_id']},
#                 {'Key': 'Rebura:Alarm:Namespace', 'Value': alarm["namespace"]},
#                 {'Key': 'Rebura:Alarm:Metric', 'Value': alarm["metric"]},
#                 {'Key': 'Rebura:Alarm:Priority', 'Value': alarm["priority"]}
#             ]
#         logger.info(tag_list)
#         cloudwatch.tag_resource(
#             ResourceARN=alarm_arn,
#             Tags=[
#                 {'Key': 'Rebura:Alarm:Description', 'Value': alarm["alarm_description"]},
#                 {'Key': 'Rebura:Alarm:Service', 'Value': event['service']},
#                 {'Key': 'Rebura:Alarm:Type', 'Value': event['resource_type']},
#                 {'Key': 'Rebura:Alarm:Identifier', 'Value': event['resource_id']},
#                 {'Key': 'Rebura:Alarm:Namespace', 'Value': alarm["namespace"]},
#                 {'Key': 'Rebura:Alarm:Metric', 'Value': alarm["metric"]},
#                 {'Key': 'Rebura:Alarm:Priority', 'Value': alarm["priority"]}
#             ]
#         )
#         logger.info(f"Tagged alarm: {alarm["alarm_name"]}")
#     except Exception as e:
#         logger.error(f"Failed to tag alarm {alarm["alarm_name"]}: {e}")
#         raise


def start_cloudwatch_session(event: dict, session: boto3.Session) -> boto3.client:
    """
    Initializes a CloudWatch client session.

    Args:
        event (dict): Event data with region information.
        session (boto3.Session): Boto3 session object for AWS interactions.

    Returns:
        boto3.client: A CloudWatch client.
    """
    try:
        cloudwatch: boto3.client = session.client('cloudwatch', region_name=event['region'], config=config)
        logger.info("Started CloudWatch Boto3 session")
        return cloudwatch
    except KeyError as e:
        logger.error(f"Missing region in event data: {e}")
        raise
