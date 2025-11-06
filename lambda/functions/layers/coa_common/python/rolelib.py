import boto3
from os import environ
from loglib import logger

# Retrieve environment variables with defaults
role_name: str = environ.get('role_name', 'default_role')
session_name: str = environ.get('session_name', 'default_session')

def assume_role(event: dict) -> dict:
    """
    Assumes an IAM role for cross-account access.

    Args:
        event (dict): Contains region and account information.

    Returns:
        dict: The response containing assumed role credentials.
    """
    try:
        sts = boto3.client("sts", region_name=event['region'])
        role_arn = f"arn:aws:iam::{event['account']}:role/{role_name}-{event['region']}"
        response = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName=session_name
        )
        logger.info(f"Successfully assumed role: {role_name} in account: {event['account']}")
        return response
    except Exception as e:
        logger.error(f"Failed to assume role: {role_name} in account: {event['account']} - Error: {e}")
        raise

def retrieve_session_credentials(event: dict, role_dict: dict) -> boto3.session:
    """
    Retrieves session credentials from an assumed role.

    Args:
        event (dict): Contains account information.
        role_dict (dict): The dictionary containing assumed role credentials.

    Returns:
        boto3.Session: A new boto3 session initialized with the assumed role's credentials.
    """
    try:
        credentials = role_dict.get('Credentials', {})
        if not credentials:
            raise ValueError("Credentials not found in the role_dict response.")

        session = boto3.Session(
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken']
        )
        logger.info(f"Retrieved session credentials for role: {role_dict.get('AssumedRoleUser')} in account: {event['account']}")
        return session
    except KeyError as ke:
        logger.error(f"KeyError: Missing expected key in role_dict - {ke}")
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve session credentials for role: {role_dict.get('AssumedRoleUser')} in account: {event['account']} - Error: {e}")
        raise
