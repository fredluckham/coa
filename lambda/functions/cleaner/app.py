from __future__ import annotations
import json
from os import environ
from typing import Any, Optional
import boto3
import jmespath
from aws_lambda_powertools.utilities.typing import LambdaContext
from loglib import logger, tracer, log_event
from rolelib import assume_role, retrieve_session_credentials

COMPANY_TAG: Optional[str] = environ.get("company_tag")
SUPPORT_TAG: Optional[str] = environ.get("support_tag")
MONITOR_TAG: Optional[str] = environ.get("monitor_tag")
IDENTIFIER_TAG: Optional[str] = environ.get("identifier_tag")
CLOUDWATCH_TAG: Optional[str] = environ.get("cloudwatch_tag")
DIMENSIONS_TAG: Optional[str] = environ.get("dimensions_tag")

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

        role_credentials = assume_role(event)
        session = retrieve_session_credentials(event, role_credentials)

        # Derived values that are widely used
        account_alias = get_account_alias(session)

        # Attach derived values directly on the event for convenience during cleaning
        event["account_alias"] = account_alias
        event["service"] = jmes_search(event, "detail.service")
        event["resource_type"] = jmes_search(event, 'detail."resource-type"')
        event["resource_id"] = get_resource_id(event)
        event["identifier"] = get_identifier(event)
        event["resource_arn"] = jmes_search(event, "resources[0]")
        event["monitored"] = check_monitor_tag(event)
        event["cloudwatch"] = check_cloudwatch_tag(event)
        event["metadata"] = get_metadata(event)

        # Fallback for EC2 termination events lacking service/resource-type
        if not event["service"] and not event["resource_type"]:
            event = check_if_ec2_termination(event)

        return event

    except Exception as exc:  # pragma: no cover - surface critical failures
        logger.exception(f"Unhandled error in lambda_handler: {exc}")
        raise

@tracer.capture_method
def get_account_alias(session: boto3.Session) -> str:
    """Retrieve the account alias for the assumed session.

    Returns an empty string if no alias is configured.
    """
    iam = session.client("iam")
    alias = ""
    paginator = iam.get_paginator("list_account_aliases")
    for page in paginator.paginate():
        aliases: list[str] = page.get("AccountAliases", [])
        if len(aliases) == 1:
            alias = aliases[0]
            logger.info(f"Account alias: {alias}")
    return alias

@tracer.capture_method
def check_if_ec2_termination(event: dict[str, Any]) -> dict[str, Any]:
    """If the event represents an EC2 termination, fill missing fields appropriately."""
    try:
        if event.get("source") == "aws.ec2" and jmes_search(event, "detail.state") == "terminated":
            event["service"] = "ec2"
            event["resource_type"] = "instance"
        return event
    except Exception as exc:
        logger.error(f"Error in check_if_ec2_termination: {exc}")
        return event

@tracer.capture_method
def check_monitor_tag(event: dict[str, Any]) -> bool:
    """Return True/False for the company:monitor tag presence.

    The tag key is built as "{COMPANY_TAG}:{MONITOR_TAG}"; if env vars are missing,
    this returns False conservatively.
    """
    if not COMPANY_TAG or not MONITOR_TAG:
        return False
    tags: dict[str, Any] = event.get("detail", {}).get("tags", {})
    return bool(tags.get(f"{COMPANY_TAG}:{MONITOR_TAG}", False))

@tracer.capture_method
def check_cloudwatch_tag(event: dict[str, Any]) -> bool:
    """Return True/False for the company:cloudwatch tag presence."""
    if not COMPANY_TAG or not CLOUDWATCH_TAG:
        return False
    tags: dict[str, Any] = event.get("detail", {}).get("tags", {})
    return bool(tags.get(f"{COMPANY_TAG}:{CLOUDWATCH_TAG}", False))

@tracer.capture_method
def get_identifier(event: dict[str, Any]) -> Optional[str]:
    """Retrieve the identifier tag *name* from event tags.

    We look for tag keys containing "{COMPANY_TAG}:{MONITOR_TAG}:{IDENTIFIER_TAG}" and
    return the *value* of that tag. This matches your prior logic where the value is
    the CloudWatch Dimension Name to target (e.g., "InstanceId").
    """
    try:
        if not (COMPANY_TAG and MONITOR_TAG and IDENTIFIER_TAG):
            return None
        tags: dict[str, Any] = event.get("detail", {}).get("tags", {})
        needle = f"{COMPANY_TAG}:{MONITOR_TAG}:{IDENTIFIER_TAG}"
        for key, value in tags.items():
            if needle in key:
                logger.info(f"Identifier tag found: {value}")
                return str(value)
        return None
    except Exception as exc:
        logger.error(f"Error in get_identifier: {exc}")
        return None

@tracer.capture_method
def get_metadata(event: dict) -> dict:
    """
    Retrieves metadata from the event tags based on the dimensions tag.

    Args:
        event (dict): The event containing tags.

    Returns:
        dict: A dictionary of metadata.
    """
    try:
        metadata: dict = {}
        tags: dict[str, Any] = event.get("detail", {}).get("tags", {})
        for tag, value in tags.items():
            logger.info(f"Processing tag: {tag} {value}")
            if f"{COMPANY_TAG}:{MONITOR_TAG}:{DIMENSIONS_TAG}" in tag:
                split_string = tag.split(':')
                logger.info(f"Found dimensions tag: {split_string[3]} {value}")
                metadata[split_string[3]] = value

        if metadata:
            logger.info(f"Successfully retrieved metadata: {metadata}")
        else:
            logger.warning("No metadata found.")
        return metadata
    except Exception as e:
        logger.error(f"Error in retrieve_metadata: {e}")
        return {}

@tracer.capture_method
def jmes_search(event: dict[str, Any], pattern: str) -> Any:
    """Safe wrapper around `jmespath.search` with error logging."""
    try:
        result = jmespath.search(pattern, event)
        if result is not None:
            logger.info(f"JMESPath search result: {result}")
            return result
        else:
            logger.warning(f"JMESPath search returned None for pattern {pattern}")
            return None
    except Exception as exc:
        logger.error(f"JMESPath error for pattern {pattern}: {exc}")
        return None

@tracer.capture_method
def get_resource_id(event: dict[str, Any]) -> Optional[str]:
    """Extract a resource identifier from common event shapes.
    """
    try:
        raw = jmes_search(event, "resources[0]")
        if isinstance(raw, str) and raw:
            # Prefer split on '/' then fallback to the last ':'
            if "/" in raw:
                rid = raw.rsplit("/", 1)[-1]
            else:
                rid = raw.rsplit(":", 1)[-1]
            logger.info(f"Resource ID (from ARN): {rid}")
            return rid
    except Exception as exc:
        logger.error(f"Failed to parse resource ID from resources[0]: {exc}")

    logger.warning("Unable to determine resource_id from event")
    return None