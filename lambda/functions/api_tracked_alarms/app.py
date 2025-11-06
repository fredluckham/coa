import json
import boto3
import time
from tracked_alarms_table_model import TrackedAlarmsTable
from loglib import logger, tracer, log_event
from rolelib import retrieve_session_credentials, assume_role
from aws_lambda_powertools.tracing import Tracer
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.utilities.typing import LambdaContext

app = APIGatewayHttpResolver()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/alarms/<account_id>")
def get_alarms_by_account(account_id: str):
    try:
        alarms = [item.attribute_values for item in TrackedAlarmsTable.query(account_id)]
        return _response(200, {"alarms": alarms})
    except Exception as e:
        logger.exception("Query error")
        return _response(500, {"error": str(e)})

@app.post("/alarms/sync")
def sync_tracked_alarms():
    try:
        body = app.current_event.json_body
        account_id = body["account"]
        region = body["region"]

        logger.info("Syncing alarms for account", extra={"account": account_id})

        role_credentials = assume_role(body)
        session = retrieve_session_credentials(body, role_credentials)

        tagging_client = session.client("resourcegroupstaggingapi")
        cloudwatch_client = session.client("cloudwatch")

        paginator = tagging_client.get_paginator("get_resources")
        response_iterator = paginator.paginate(
            TagFilters=[{"Key": "Rebura:Alarm:Name"}],
            ResourceTypeFilters=["cloudwatch:alarm"]
        )

        for page in response_iterator:
            logger.info("Processing page", extra={"page": page})
            for resource in page.get("ResourceTagMappingList", []):
                tags = {t["Key"]: t["Value"] for t in resource.get("Tags", [])}

                alarm_name = tags.get("Rebura:Alarm:Name")
                alarm_description = tags.get("Rebura:Alarm:Description")
                resource_type = tags.get("Rebura:Alarm:Type")
                service = tags.get("Rebura:Alarm:Service")
                resource_id = tags.get("Rebura:Alarm:Identifier")
                namespace = tags.get("Rebura:Alarm:Namespace")
                metric = tags.get("Rebura:Alarm:Metric")
                level = tags.get("Rebura:Alarm:Level")
                resource_arn = resource.get("ResourceARN")

                cw_response = cloudwatch_client.describe_alarms(AlarmNames=[alarm_name])
                state = cw_response["MetricAlarms"][0].get("StateValue")
                alarm_arn = cw_response["MetricAlarms"][0].get("AlarmArn")

                item = TrackedAlarmsTable(
                    account_id=account_id,
                    alarm_name=alarm_name,
                    alarm_description=alarm_description,
                    alarm_arn=alarm_arn,
                    service=service,
                    region=region,
                    resource_type=resource_type,
                    namespace=namespace,
                    metric=metric,
                    level=level,
                    resource_id=resource_id,
                    resource_arn=resource_arn,
                    state_value=state,
                    ttl=int(time.time()) + 3600
                )
                item.save()
        return _response(200, {"message": "Tracked alarms updated successfully"})
    except Exception as e:
        logger.exception("Sync failed")
        return _response(500, {"error": str(e)})

@logger.inject_lambda_context(log_event=log_event, correlation_id_path=correlation_paths.API_GATEWAY_HTTP)
@tracer.capture_lambda_handler
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    return app.resolve(event, context)

def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body)
    }
