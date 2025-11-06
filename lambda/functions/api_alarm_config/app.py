import json
from pynamodb.exceptions import PutError, DeleteError
from alarm_table_model import AlarmConfigTable
from loglib import logger, tracer, log_event
from aws_lambda_powertools.tracing import Tracer
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.utilities.typing import LambdaContext

app = APIGatewayHttpResolver()

REQUIRED_FIELDS = [
    "service", "metric_name", "thresholds", "namespace", "statistic",
    "comparison_operator", "evaluation_periods", "period", "treat_missing_data", "dimensions"
]

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/alarms")
def create_alarm():
    body = app.current_event.json_body
    logger.info("Parsed body", extra={"body": body})

    missing = [f for f in REQUIRED_FIELDS if f not in body]
    if missing:
        return _response(400, {"error": f"Missing required fields: {missing}"})

    try:
        item = AlarmConfigTable(
            service=body["service"],
            metric_name=body["metric_name"],
            thresholds=body["thresholds"],
            namespace=body["namespace"],
            statistic=body["statistic"],
            comparison_operator=body["comparison_operator"],
            evaluation_periods=int(body["evaluation_periods"]),
            period=int(body["period"]),
            treat_missing_data=body["treat_missing_data"],
            dimensions=body["dimensions"],
            actions_enabled=body.get("actions_enabled", True),
            alarm_description=body.get("alarm_description", "")
        )
        item.save()
        logger.info("Alarm config saved", extra={"item": item.attribute_values})
        return _response(200, {"message": "Alarm config saved successfully"})

    except PutError as e:
        logger.exception("PynamoDB PutError")
        return _response(500, {"error": "Failed to write to DynamoDB"})

    except Exception as e:
        logger.exception("Unhandled error")
        return _response(500, {"error": str(e)})

@app.get("/alarms/<service>")
def get_alarms_by_service(service: str):
    try:
        alarms = [item.attribute_values for item in AlarmConfigTable.query(service)]
        return _response(200, {"alarms": alarms})
    except Exception as e:
        logger.exception("Query error")
        return _response(500, {"error": str(e)})

@app.get("/alarms/<service>/<metric_name>")
def get_alarm_by_service_and_metric(service: str, metric_name: str):
    try:
        item = AlarmConfigTable.get(service, metric_name)
        return _response(200, {"alarm": item.attribute_values})
    except AlarmConfigTable.DoesNotExist:
        return _response(404, {"error": "Alarm config not found"})
    except Exception as e:
        logger.exception("Unhandled error")
        return _response(500, {"error": str(e)})

@app.delete("/alarms/<service>/<metric_name>")
def delete_alarm(service: str, metric_name: str):
    try:
        item = AlarmConfigTable.get(service, metric_name)
        item.delete()
        logger.info("Deleted alarm config", extra={"service": service, "metric_name": metric_name})
        return _response(200, {"message": "Alarm config deleted successfully"})
    except AlarmConfigTable.DoesNotExist:
        return _response(404, {"error": "Alarm config not found"})
    except DeleteError:
        logger.exception("Failed to delete alarm config")
        return _response(500, {"error": "Failed to delete alarm config"})
    except Exception as e:
        logger.exception("Unhandled error")
        return _response(500, {"error": str(e)})

@logger.inject_lambda_context(log_event=log_event)
@tracer.capture_lambda_handler
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    return app.resolve(event, context)

def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body)
    }
