from botocore.config import Config
from dataclasses import dataclass
from loglib import logger
from taglib import retrieve_metadata, retrieve_volume_data
import boto3

# Configuration for retries
config = Config(
    retries={
        'max_attempts': 10,
        'mode': 'standard'
    }
)


@dataclass
class AlarmData:
    """
    Data class representing a CloudWatch alarm configuration.
    """
    thresholds: list
    comparison_operator: str
    evaluation_periods: int
    datapoints_to_alarm: int
    metric_name: str
    namespace: str
    period: int
    statistic: str
    extended_statistic: str
    actions_enabled: bool
    alarm_description: str
    treat_missing_data: str
    dimensions: dict


class Alarms:
    """
    Class representing the overall alarm data for the resource being monitored. 

    Args:
        event (dict): Event data with resource and alarm information.
    
    Attributes:
        meta_data (dict): Alarm dimension data to be used against the DynamoDB object.
        volume_data (dict: Volume data (where applicable) to be used against the DynamoDB object.
        alarm_list (list): List of alarm names that have been created for the resource.
    """
    def __init__(self, event: dict):
        # Retrieve metadata and volume data from the event
        self.meta_data: dict = retrieve_metadata(event)
        self.volume_data: dict = retrieve_volume_data(event)
        # Initialize the alarm list
        self.alarm_list: list = []



def for_each_threshold(event: dict, session: boto3.Session, alarm_object: AlarmData, alarms: object) -> list:
    """
    Processes each threshold in an AlarmData object and creates corresponding CloudWatch alarms.

    Args:
        event (dict): Event data with resource and alarm information.
        session (boto3.Session): Boto3 session object for AWS interactions.
        alarm_object (AlarmData): AlarmData object containing configuration details.

    Returns:
        list: A list of created alarm names.
    """
    cloudwatch: boto3.client = start_cloudwatch_session(event, session)
    for threshold in alarm_object.thresholds:
        severity, threshold_value, level = retrieve_criticality_values(threshold)
        action_topic_arn = build_action_topic_arn(event, level)
        alarm_name = build_alarm_name(event, alarm_object, severity)
        if alarm_name not in alarms.alarm_list:
            alarms.alarm_list.append(alarm_name)
            create_alarm(event, cloudwatch, alarm_name, alarm_object, threshold_value, level, action_topic_arn)
        else:
            logger.info(f"Skipping alarm: {alarm_name}")

    return alarms.alarm_list


def retrieve_criticality_values(threshold: list) -> tuple:
    """
    Extracts criticality values (severity, threshold value, and level) from a threshold list.

    Args:
        threshold (list): A list containing threshold data.

    Returns:
        tuple: Severity, threshold value as float, and level.
    """
    try:
        severity, threshold_value, level = threshold
        logger.info(f"Retrieved criticality values: {severity}, {threshold_value}, {level}")
        return severity, float(threshold_value), level
    except ValueError as e:
        logger.error(f"Threshold list does not match expected format: {threshold}. Error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in retrieve_criticality_values: {e}")
        raise


def build_alarm_name(event: dict, alarm_object: AlarmData, severity: str) -> str:
    """
    Constructs the name for a CloudWatch alarm.

    Args:
        event (dict): Event data with resource and account information.
        alarm_object (AlarmData): AlarmData object containing configuration details.
        severity (str): The severity level of the alarm.

    Returns:
        str: Constructed alarm name.
    """
    try:
        dimension_data: str = loop_through_dimensions(alarm_object)
        alarm_name: str = (
            f"{event['account_alias']}-{event['account']}-{event['service']}-"
            f"{event['resource_type']}{dimension_data}-{alarm_object.metric_name}-"
            f"Severity: {severity}"
        )
        logger.info(f"Built alarm name: {alarm_name}")
        return alarm_name
    except KeyError as e:
        logger.error(f"Missing required event data for alarm name: {e}")
        raise


def loop_through_dimensions(alarm_object: AlarmData) -> str:
    """
    Retrives the dimension values from the alarm object to pass to the name builder.

    Args:
        alarm_object (AlarmData): AlarmData object containing configuration details.
    
    Returns:
        str: Dimensions string.
    """ 
    try:
        dimension_data: str = ""
        for dimension in alarm_object.dimensions:
            dimension_data = dimension_data + f"-{dimension['Value']}"
        return dimension_data
    except KeyError as e:
        logger.error(f"Missing alarm dimension data for alarm name: {e}")
        raise


def build_action_topic_arn(event: dict, level: str) -> list:
    """
    Constructs the SNS topic ARN for alarm actions.

    Args:
        event (dict): Event data with region and account information.
        level (str): Severity level of the alarm.

    Returns:
        list: List containing the action topic ARN.
    """
    try:
        action_topic_arn: list = [
            f"arn:aws:sns:{event['region']}:{event['account']}:Rebura-CentralisedObservabilityAutomationTopic{level}-{event['region']}"
        ]
        logger.info(f"Built action topic ARN: {action_topic_arn}")
        return action_topic_arn
    except KeyError as e:
        logger.error(f"Missing required event data for action topic ARN: {e}")
        raise


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


def create_alarm(event: dict, cloudwatch: boto3.client, alarm_name: str, alarm_object: AlarmData,
                 threshold_value: float, level: str, action_topic_arn: list) -> None:
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
        cloudwatch.put_metric_alarm(
            AlarmName=alarm_name,
            ComparisonOperator=alarm_object.comparison_operator,
            EvaluationPeriods=alarm_object.evaluation_periods,
            MetricName=alarm_object.metric_name,
            Namespace=alarm_object.namespace,
            Period=alarm_object.period,
            Statistic=alarm_object.statistic,
            Threshold=threshold_value,
            ActionsEnabled=alarm_object.actions_enabled,
            OKActions=action_topic_arn,
            AlarmActions=action_topic_arn,
            AlarmDescription=alarm_object.alarm_description,
            TreatMissingData=alarm_object.treat_missing_data,
            Dimensions=alarm_object.dimensions
        )
        logger.info(f"Created alarm: {alarm_name}")
        retrieve_alarm_arn(event, alarm_name, cloudwatch, alarm_object, level)
    except Exception as e:
        logger.error(f"Failed to create alarm {alarm_name}: {e}")
        raise


def retrieve_alarm_arn(event: dict, alarm_name: str, cloudwatch: boto3.client,
                       alarm_object: AlarmData, level: str) -> None:
    """
    Retrieves the ARN of a created alarm and tags it.

    Args:
        event (dict): Event data with tagging information.
        alarm_name (str): Name of the alarm.
        cloudwatch (boto3.client): CloudWatch client instance.
        alarm_object (AlarmData): AlarmData configuration object.
        level (str): Severity level of the alarm.

    Returns:
        None
    """
    try:
        response: dict = cloudwatch.describe_alarms(AlarmNames=[alarm_name])
        alarm_arn: str = response['MetricAlarms'][0]['AlarmArn']
        logger.info(f"Retrieved alarm ARN: {alarm_arn}")
        tag_alarm(event, alarm_name, cloudwatch, alarm_object, level, alarm_arn)
    except IndexError:
        logger.error(f"Alarm {alarm_name} not found in describe_alarms response.")
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve alarm ARN for {alarm_name}: {e}")
        raise


def tag_alarm(event: dict, alarm_name: str, cloudwatch: boto3.client, alarm_object: AlarmData,
              level: str, alarm_arn: str) -> None:
    """
    Tags a CloudWatch alarm with metadata.

    Args:
        event (dict): Event data for resource and alarm tagging.
        alarm_name (str): Name of the alarm.
        cloudwatch (boto3.client): CloudWatch client instance.
        alarm_object (AlarmData): AlarmData configuration object.
        level (str): Severity level of the alarm.
        alarm_arn (str): ARN of the alarm to tag.

    Returns:
        None
    """
    try:
        cloudwatch.tag_resource(
            ResourceARN=alarm_arn,
            Tags=[
                {'Key': 'Rebura:Alarm:Name', 'Value': alarm_name},
                {'Key': 'Rebura:Alarm:Description', 'Value': alarm_object.alarm_description},
                {'Key': 'Rebura:Alarm:Service', 'Value': event['service']},
                {'Key': 'Rebura:Alarm:Type', 'Value': event['resource_type']},
                {'Key': 'Rebura:Alarm:Identifier', 'Value': event['resource_id']},
                {'Key': 'Rebura:Alarm:Namespace', 'Value': alarm_object.namespace},
                {'Key': 'Rebura:Alarm:Metric', 'Value': alarm_object.metric_name},
                {'Key': 'Rebura:Alarm:Level', 'Value': level}
            ]
        )
        logger.info(f"Tagged alarm: {alarm_name}")
    except Exception as e:
        logger.error(f"Failed to tag alarm {alarm_name}: {e}")
        raise
