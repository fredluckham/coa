import time
import boto3
import botocore.exceptions
from aws_lambda_powertools.utilities.typing import LambdaContext
from loglib import logger, tracer, log_event
from rolelib import assume_role, retrieve_session_credentials

SSM_DOC_MANAGE_AGENT = "AmazonCloudWatch-ManageAgent"


def wait_for_command(ssm, command_id, instance_id, timeout=180, poll=5):
    """Wait for SSM command to complete and return output."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = ssm.get_command_invocation(
                CommandId=command_id,
                InstanceId=instance_id
            )
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "InvocationDoesNotExist":
                # SSM hasn’t created the invocation yet – wait and retry
                time.sleep(poll)
                continue
            raise  # re-raise unexpected errors

        status = resp["Status"]
        if status == "Success":
            logger.info(f"SSM command {command_id} completed successfully")
            return resp
        if status in ("Failed", "Cancelled", "TimedOut"):
            logger.info(f"SSM command {command_id} failed: {status}")
            return resp
        # Still running → sleep and retry
        time.sleep(poll)

    raise TimeoutError(f"Timed out waiting for SSM command {command_id}")

@logger.inject_lambda_context(log_event=log_event)
@tracer.capture_lambda_handler
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    """
    Check if CloudWatch agent is running on an EC2 instance; install if missing.
    Event must include: { "resource_id": "i-...", "region": "eu-west-1" }
    """
    instance_id = event.get("resource_id")
    region = event.get("region")
    if not instance_id or not region:
        raise ValueError("Missing resource_id or region in event")

    # Assume role into target account
    assumed = assume_role(event)
    session = retrieve_session_credentials(event, assumed)
    ssm = session.client("ssm", region_name=region)
    event["os_type"] = check_os_type(event, ssm, instance_id)
    event["wait_for_metrics"] = check_cloudwatch_agent(event, ssm, instance_id, event["os_type"])
    return event

def check_os_type(event, ssm, instance_id):
    """Check OS type of instance and return event with wait_for_metrics flag."""
    logger.info(f"Checking OS type for instance {instance_id}")
    try:
        # --- Check SSM registration / OS type
        infos = ssm.describe_instance_information(
            Filters=[{"Key": "InstanceIds", "Values": [instance_id]}]
        )
        if not infos.get("InstanceInformationList"):
            raise RuntimeError(f"Instance {instance_id} not managed by SSM")

        os_type = infos["InstanceInformationList"][0]["PlatformType"]
        logger.info(f"Detected OS {os_type} for instance {instance_id}")
        return os_type
    except Exception as exc:
        logger.error(f"Failed to detect OS type: {exc}")


def check_cloudwatch_agent(event, ssm, instance_id, os_type):
    """Check CloudWatch agent status and install if missing."""
    logger.info(f"Checking CloudWatch agent for instance {instance_id}")

    try:
        # # --- Step 1: Check CloudWatch agent status
        # resp = ssm.send_command(
        #     InstanceIds=[instance_id],
        #     DocumentName=SSM_DOC_MANAGE_AGENT,
        #     Parameters={"action": ["status"]},
        #     CloudWatchOutputConfig={"CloudWatchOutputEnabled": True}
        # )
        # output = wait_for_command(ssm, resp["Command"]["CommandId"], instance_id)
        # if output:
        #     logger.info(f"CloudWatch agent status: {output}")
        # else:
        #     logger.info("CloudWatch agent status: Not found. Attempting install.")

        # if "running" in output.lower():
        #     event["wait_for_metrics"] = False
        #     return event

        # # --- Step 2: Install if not running
        if os_type.lower() == "windows":
            logger.info(f"Installing CloudWatch agent (Windows) on {instance_id}")
            resp = ssm.send_command(
                InstanceIds=[instance_id],
                DocumentName="AWS-ConfigureAWSPackage",
                Parameters={
                    "action": ["Install"],
                    "installationType": ["Uninstall and reinstall"],
                    "name": ["AmazonCloudWatchAgent"],
                },
                CloudWatchOutputConfig={"CloudWatchOutputEnabled": True}
            )
        else:
            logger.info(f"Installing CloudWatch agent (Linux) on {instance_id}")
            resp = ssm.send_command(
                InstanceIds=[instance_id],
                DocumentName=SSM_DOC_MANAGE_AGENT,
                Parameters={"action": ["install"], "mode": ["ec2"]},
                CloudWatchOutputConfig={"CloudWatchOutputEnabled": True}
            )

        install_ouput = wait_for_command(ssm, resp["Command"]["CommandId"], instance_id)
        logger.info(f"CloudWatch agent installation output: {install_ouput}")

        # --- Step 3: Configure CloudWatch agent
        logger.info(f"Configuring CloudWatch agent for {instance_id}")
        resp = ssm.send_command(
            InstanceIds=[instance_id],
            DocumentName=SSM_DOC_MANAGE_AGENT,
            Parameters={
                "action": ["configure"],
                "mode": ["ec2"],
                "optionalConfigurationSource": ["default"],
                "optionalRestart": ["yes"],
            },
            CloudWatchOutputConfig={"CloudWatchOutputEnabled": True}
        )
        configure_output = wait_for_command(ssm, resp["Command"]["CommandId"], instance_id)
        logger.info(f"CloudWatch agent configuration output: {configure_output}")
        return  True

    except Exception as exc:
        logger.error(f"Failed to install CloudWatch agent: {exc}")
        return False
