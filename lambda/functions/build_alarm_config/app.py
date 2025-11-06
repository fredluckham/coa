from __future__ import annotations
import json
import re
import time
from os.path import basename
from os import environ
from typing import Any, Dict, List, Optional

import boto3
import jmespath
from aws_lambda_powertools.utilities.typing import LambdaContext
from loglib import logger, tracer, log_event
from pynamodb.attributes import (
    BooleanAttribute,
    ListAttribute,
    NumberAttribute,
    UnicodeAttribute,
)
from pynamodb.models import Model
from rolelib import assume_role, retrieve_session_credentials

# ---------------------------------------------------------------------------
# Environment variables & constants
# ---------------------------------------------------------------------------
COMPANY_TAG: Optional[str] = environ.get("company_tag")
SUPPORT_TAG: Optional[str] = environ.get("support_tag")
MONITOR_TAG: Optional[str] = environ.get("monitor_tag")
IDENTIFIER_TAG: Optional[str] = environ.get("identifier_tag")
CLOUDWATCH_TAG: Optional[str] = environ.get("cloudwatch_tag")
DIMENSIONS_TAG: Optional[str] = environ.get("dimensions_tag")
EC2LINUXDISK_TAG: Optional[str] = environ.get("ec2_linux_disk_tag")
EC2WINDOWSDISK_TAG: Optional[str] = environ.get("ec2_windows_disk_tag")


APP_NAME: str = environ.get("app", "default_app")
DYNAMO_TABLE: str = environ.get("alarm_table", "default_table")
AWS_REGION: str = environ.get("region", "eu-west-1")


# ---------------------------------------------------------------------------
# DynamoDB Table Model (PynamoDB)
# ---------------------------------------------------------------------------
class AlarmConfigTable(Model):
    """Alarm configuration table.

    Partition Key: service
    Sort Key:      metric_name

    Attributes are modeled after your previous schema. Thresholds/dimensions are
    stored as lists (see `get_alarms` for robust handling of their shapes).
    """

    class Meta:
        table_name = DYNAMO_TABLE
        region = AWS_REGION

    service: str = UnicodeAttribute(hash_key=True)
    metric_name: str = UnicodeAttribute(range_key=True)

    namespace: str = UnicodeAttribute(null=False)
    extended_statistic: Optional[str] = UnicodeAttribute(null=True)
    alarm_description: str = UnicodeAttribute(null=False)
    comparison_operator: str = UnicodeAttribute(null=False)
    actions_enabled: bool = BooleanAttribute(null=False)

    # Free-form structures coming from config; using ListAttribute for flexibility
    thresholds: list = ListAttribute(null=False)
    dimensions: list = ListAttribute(null=False)

    datapoints_to_alarm: int = NumberAttribute(null=False, default=15)
    evaluation_periods: int = NumberAttribute(null=False, default=15)
    period: int = NumberAttribute(null=False, default=60)
    treat_missing_data: str = UnicodeAttribute(null=False, default="breaching")
    statistic: Optional[str] = UnicodeAttribute(null=True, default="Average")


# ---------------------------------------------------------------------------
# Lambda Entrypoint
# ---------------------------------------------------------------------------
@logger.inject_lambda_context(log_event=log_event)
@tracer.capture_lambda_handler
def lambda_handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """Lambda entrypoint.

    - Assumes the target role using details in the event
    - Retrieves a boto3 session for that role
    - Extracts derived values (resource_id, identifier, account_alias, service, resource_type)
    - Builds and returns a structured payload
    """
    try:
        # Truncate raw event in logs to avoid exceeding CloudWatch size limits
        logger.info(f"Event: {json.dumps(event)[:1000]}")
        disks = []
        role_credentials = assume_role(event)
        session = retrieve_session_credentials(event, role_credentials)
        if event['service'] == 'ec2' and event['resource_type'] == 'instance' and event['cloudwatch'] == True:
            os_type = get_os_type(session, event['resource_id'])
            if os_type:
                logger.info(f"OS type: {os_type}")
                disks = discover_disks(session, event['resource_id'], os_type)
                if disks:
                    logger.info(f"Discovered disks: {disks}")
        event['alarm_config'] = get_alarms(event, disks)
        for alarm in event["alarm_config"]:
            for dimension in alarm["dimensions"]:
                if dimension["Name"] == dimension["Value"]:
                    alarm["dimensions"].remove(dimension)
        return event

    except Exception as exc:  # pragma: no cover - surface critical failures
        logger.exception("Unhandled error in lambda_handler")
        raise

@tracer.capture_method
def get_alarms(event: dict[str, Any], disks: Optional[List[Dict[str, str]]]) -> list[dict[str, Any]]:
    """Build a unique list of alarm definitions for the event resource."""
    alarms: list[dict[str, Any]] = []
    seen: set[str] = set()  # track unique alarm signatures

    tags: dict[str, Any] = event.get("detail", {}).get("tags", {})
    identifier: Optional[str] = event.get("identifier")
    resource_id: Optional[str] = event.get("resource_id")

    disk_meta_data = []

    if not identifier or not resource_id:
        logger.warning("get_alarms called without identifier/resource_id")
        return alarms

    for tag_key, tag_value in tags.items():
        parts = str(tag_key).split(":")
        if len(parts) < 3:
            continue

        service, metric, priority_token = parts[-3], parts[-2], parts[-1]
        if priority_token not in {"P1", "P2", "P3"}:
            continue

        if metric in [EC2LINUXDISK_TAG, EC2WINDOWSDISK_TAG]:
            disk_meta_data.append({"service": service, "metric": metric, "priority_token": priority_token, "tag_value": tag_value})
            continue

        alarm = get_table_item(
            service, metric, priority_token, tag_value,
            identifier, resource_id, event, None
        )
        if not alarm:
            continue
        alarms.append(alarm)

    if disks:
        for disk in disks:
            for meta_data in disk_meta_data:
                service = meta_data["service"]
                metric = meta_data["metric"]
                priority_token = meta_data["priority_token"]
                tag_value = meta_data["tag_value"]
                alarm = get_table_item(
                    service, metric, priority_token, tag_value,
                    identifier, resource_id, event, disk
                )
                if not alarm:
                    continue
                alarms.append(alarm)

    return alarms



def get_table_item(
    service: str,
    metric: str,
    priority_token: str,
    tag_value: Any,
    identifier: str,
    resource_id: str,
    event: dict[str, Any],
    disk: Optional[Dict[str, str]],
) -> Optional[dict[str, Any]]:
    """Construct an alarm definition from DynamoDB config + tag overrides."""

    table_item = load_table_item(service, metric)
    if table_item is None:
        logger.warning(
            "No DynamoDB config for service/metric",
            extra={"service": service, "metric": metric},
        )
        return None

    # Base alarm from table
    item: dict[str, Any] = {
        "priority": priority_token,
        "metric": metric,
        "service": service,
        "threshold": tag_value,
        "actions_enabled": table_item.actions_enabled,
        "comparison_operator": table_item.comparison_operator,
        "datapoints_to_alarm": table_item.datapoints_to_alarm,
        "dimensions": list(table_item.dimensions or []),
        "evaluation_periods": table_item.evaluation_periods,
        "namespace": table_item.namespace,
        "period": table_item.period,
        "statistic": table_item.statistic,
        "treat_missing_data": table_item.treat_missing_data,
        "alarm_description": getattr(table_item, "alarm_description", ""),
    }

    # Apply threshold overrides from table
    for t in list(table_item.thresholds or []):
        try:
            if isinstance(t, dict) and t.get("priority") == priority_token:
                if str(item["threshold"]).lower() == "true" and "threshold" in t:
                    item["threshold"] = t["threshold"]
                if "criticality" in t:
                    item["criticality"] = t["criticality"]
            elif isinstance(t, (list, tuple)) and len(t) >= 2:
                prio, value = t[0], t[1]
                if prio == priority_token and str(item["threshold"]).lower() == "true":
                    item["threshold"] = value
                    item.setdefault("criticality", priority_token)
        except Exception as exc:
            logger.warning(f"Failed to apply threshold entry: {t}. Error: {exc}")

    item.setdefault("criticality", priority_token)

    # Build new dimension list safely
    new_dimensions = []
    for dim in item["dimensions"]:
        if not isinstance(dim, dict):
            continue

        # Match identifier
        if dim.get("Name") == identifier:
            dim["Value"] = resource_id

        # Match metadata overrides
        elif dim.get("Name") in event.get("metadata", {}):
            dim["Value"] = event["metadata"][dim["Name"]]

        # Keep dimension only if it got a value
        if "Value" in dim:
            new_dimensions.append(dim)
        else:
            logger.info(f"Removed unused dimension: {dim}")
    
    if disk:
        if item["metric"] in [EC2LINUXDISK_TAG, EC2WINDOWSDISK_TAG]: 
            for key, value in disk.items():
                new_dimensions.append({"Name": key, "Value": value})

    item["dimensions"] = new_dimensions

    # Derived fields
    item["alarm_name"] = build_alarm_name(event, item)
    item["action_topic_arn"] = build_action_topic_arn(event, item)

    return item



@tracer.capture_method
def build_alarm_name(event: dict[str, Any], item: dict[str, Any]) -> str:
    """Construct a human-readable alarm name using account/service/resource details."""
    try:
        dims = item["dimensions"]
        target_names = {"path", "LogicalDisk"}

        found_value = next(
            (dim["Value"] for dim in dims if dim.get("Name") in target_names),
            None
        )

        if found_value:
            alarm_name = (
                f"{event.get('account_alias','')}-{event.get('account','')}-{event.get('service','')}-"
                f"{event.get('resource_type','')}-{event.get('resource_id','')}-{item.get('metric','')}-'{found_value}'-"
                f"Severity: {item.get('criticality','')}"
            )
        else:
            alarm_name = (
                f"{event.get('account_alias','')}-{event.get('account','')}-{event.get('service','')}-"
                f"{event.get('resource_type','')}-{event.get('resource_id','')}-{item.get('metric','')}-"
                f"Severity: {item.get('criticality','')}"
            )

        return alarm_name
    except Exception as exc:
        logger.error(f"Failed to build alarm name: {exc}")
        raise


@tracer.capture_method
def build_action_topic_arn(event: dict[str, Any], item: dict[str, Any]) -> list[str]:
    """Construct the SNS topic ARN list used for alarm actions."""
    try:
        arn = (
            f"arn:aws:sns:{event['region']}:{event['account']}:"
            f"Rebura-CentralisedObservabilityAutomationTopic{item['priority']}-{event['region']}"
        )

        return [arn]
    except KeyError as exc:
        logger.error(f"Missing required data for action topic ARN: {exc}")
        raise

@tracer.capture_method
def load_table_item(service_name: str, metric: str) -> Optional[AlarmConfigTable]:
    """Load a single configuration record from DynamoDB.

    Returns None if the record is missing or an error occurs.
    """
    try:
        return AlarmConfigTable.get(service_name, metric)
    except AlarmConfigTable.DoesNotExist:
        logger.warning(f"No config found for {service_name}:{metric}")
        return None
    except Exception as exc:
        logger.error(f"Error loading config for {service_name}:{metric}: {exc}")
        return None

def get_os_type(session: boto3.Session, instance_id: str) -> str:
    """Determine OS type via EC2 describe_instances."""
    try:
        ec2 = session.client("ec2")
        resp = ec2.describe_instances(InstanceIds=[instance_id])
        platform = resp["Reservations"][0]["Instances"][0].get("Platform", "Linux")
        return "Windows" if platform == "windows" else "Linux"
    except Exception as exc:
        logger.error(f"Error getting OS type for {instance_id}: {exc}")
        return None

def discover_disks(session: boto3.Session, instance_id: str, os_type: str) -> List[Dict[str, str]]:
    """
    Discover mounted volumes / logical disks via SSM.
    Returns list of dicts with keys needed for CloudWatch alarms:
      - Linux: device, fstype, path
      - Windows: LogicalDisk (drive letter)
    """
    ssm = session.client("ssm")

    if os_type.lower() == "linux":
        # df output: filesystem fstype 1K-blocks used available use% mounted_on
        cmd = "df -T -P | tail -n +2 | awk '{print $1,$2,$7}'"
        doc_name = "AWS-RunShellScript"
    else:
        # PowerShell: list filesystem drives
        cmd = 'Get-PSDrive -PSProvider FileSystem | ForEach-Object { $_.Name }'
        doc_name = "AWS-RunPowerShellScript"

    try:
        resp = ssm.send_command(
            InstanceIds=[instance_id],
            DocumentName=doc_name,
            Parameters={"commands": [cmd]},
        )
        cmd_id = resp["Command"]["CommandId"]
        # Wait for SSM command to complete (polling could be added for production)
        time.sleep(5)

        output = ssm.get_command_invocation(CommandId=cmd_id, InstanceId=instance_id)
        result = output.get("StandardOutputContent", "")
        logger.info(f"Command output for {instance_id} ({os_type}):\n{result}")

        disks = []
        for line in result.splitlines():
            line = line.strip()
            if not line:
                continue
            if os_type.lower() == "linux":
                try:
                    # split by whitespace
                    parts = line.split()
                    if len(parts) < 3:
                        logger.warning(f"Skipping line, unexpected format: {line}")
                        continue
                    device_full, fstype, path = parts[0], parts[1], parts[2]
                    device = basename(device_full)
                    disks.append({"device": device, "fstype": fstype, "path": path})
                except Exception as e:
                    logger.error(f"Error parsing line '{line}': {e}")
            else:
                # Windows drive letter
                disks.append({"LogicalDisk": line})

        return disks

    except Exception as e:
        logger.error(f"Error discovering disks for {instance_id}: {e}")
        return []