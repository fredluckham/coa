from os import environ
from aws_lambda_powertools import Logger, Tracer

# Retrieve environment variables with fallbacks
app_name: str = environ.get('app')
log_level: str = environ.get('powertools_log_level', 'INFO')  # Default to 'INFO'
log_event: str = environ.get('powertools_log_event', 'false')  # Default to 'false'

# Initialize the logger with service name and log level
logger = Logger(
    service=app_name,
    level=log_level
)

# Initialize the tracer for distributed tracing
tracer = Tracer()

# Log configuration during initialization for visibility
logger.info(f"Logger initialized with service: {app_name}, level: {log_level}, log_event: {log_event}")
