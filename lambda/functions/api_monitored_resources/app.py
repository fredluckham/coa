import json
import boto3
import time
from typing import Any
from rolelib import assume_role, retrieve_session_credentials
from loglib import logger, tracer, log_event
from monitored_resources_table_model import MonitoredResourcesTable
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.logging import correlation_paths

app = APIGatewayHttpResolver()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/resources/sync")
def sync_monitored_resources():
    try:
        body = app.current_event.json_body
        account_id = body["account"]

        logger.info("Syncing monitored resources for account", extra={"account_id": account_id})

        role_credentials = assume_role(body)
        session = retrieve_session_credentials(body, role_credentials)

        taggingapi = session.client('resourcegroupstaggingapi')

        parsed_arns = []
        pagination_token = ""

        while True:
            kwargs = {
                "TagFilters": [
                    {
                        'Key': 'Rebura:Monitored',
                        'Values': ['True']
                    }
                ]
            }
            if pagination_token:
                kwargs['PaginationToken'] = pagination_token

            response = taggingapi.get_resources(**kwargs)
            logger.info(response)

            for resource in response.get('ResourceTagMappingList', []):
                arn = resource.get('ResourceARN')
                if arn:
                    try:
                        parsed = parse_arn_resources(arn)
                        parsed_arns.append(parsed)
                    except ValueError as e:
                        # amazonq-ignore-next-line
                        logger.warning(f"Skipping invalid ARN: {arn} ({e})")

            pagination_token = response.get('PaginationToken')
            if not pagination_token:
                break

        batch_write_to_table_resources(parsed_arns)

        return _response(200, {"message": "Monitored resources updated successfully"})
    except Exception as e:
        logger.exception("Sync failed")
        return _response(500, {"error": str(e)})

@app.get("/resources/<account_id>")
def get_monitored_resources_by_account(account_id: str):
    try:
        resources = [item.attribute_values for item in MonitoredResourcesTable.query(account_id)]
        return _response(200, {"resources": resources})
    except Exception as e:
        logger.exception("Query error")
        return _response(500, {"error": str(e)})

def parse_arn_resources(arn: str) -> dict:
    try:
        parts = arn.split(":", 5)
        if len(parts) != 6:
            raise ValueError("Invalid ARN format")

        arn_prefix, partition, service, region, account_id, resource = parts

        if "/" in resource:
            resource_type, resource_id = resource.split("/", 1)
        elif ":" in resource:
            resource_type, resource_id = resource.split(":", 1)
        else:
            resource_type, resource_id = None, resource

        return {
            "arn": arn,
            "arn_prefix": arn_prefix,
            "partition": partition,
            "service": service,
            "region": region,
            "account_id": account_id,
            "resource_type": resource_type,
            "resource_id": resource_id
        }
    except Exception as e:
        raise ValueError(f"Failed to parse ARN: {e}")

def batch_write_to_table_resources(resources: list):
    with MonitoredResourcesTable.batch_write() as batch:
        for resource in resources:
            item = MonitoredResourcesTable(
                account_id=resource["account_id"],
                resource_id=resource["resource_id"]
            )
            item.arn = resource["arn"]
            item.arn_prefix = resource["arn_prefix"]
            item.partition = resource["partition"]
            item.service = resource["service"]
            item.region = resource["region"]
            item.resource_type = resource["resource_type"]
            item.ttl = int(time.time()) + 3600
            batch.save(item)

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
