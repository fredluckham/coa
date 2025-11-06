from os import environ
from loglib import logger

# Retrieve environment variables with defaults
app_name: str = environ.get('app', 'default_app')
company_tag: str = environ.get('company_tag', 'default_company')
support_tag: str = environ.get('support_tag', 'default_support')
monitor_tag: str = environ.get('monitor_tag', 'default_monitor')
dimensions_tag: str = environ.get('dimensions_tag', 'dimensions')
identifier_tag: str = environ.get('identifier_tag', 'identifier')
cloudwatch_tag: str = environ.get('cloudwatch_tag', 'cloudwatch')
ec2_linux_disk_tag: str = environ.get('ec2_linux_disk_tag', 'linux_disk')
ec2_windows_disk_tag: str = environ.get('ec2_windows_disk_tag', 'windows_disk')


def retrieve_service_and_metrics(event: dict) -> tuple:
    """
    Retrieves the service name and a list of metrics from the event tags.

    Args:
        event (dict): The event containing tags.

    Returns:
        tuple:
            - service_name: The name of the service if found, otherwise None.
            - metric_list: A list of metrics if found, otherwise None.
    """
    try:
        service_name = None
        metric_list: list = []

        for tag, value in event.get('tags', {}).items():
            if f"{company_tag}:{monitor_tag}" in tag and value != "False":
                split_string = tag.split(':')
                if len(split_string) >= 4 and split_string[2] not in {dimensions_tag, identifier_tag, cloudwatch_tag}:
                    service_name = split_string[2]
                    metric_list.append(split_string[3])

        if service_name and metric_list:
            logger.info(f"Successfully retrieved service name: {service_name}")
            logger.info(f"Successfully retrieved metric list: {metric_list}")
            return service_name, metric_list
        else:
            logger.warning("Unable to retrieve service name or metric list from tags.")
            return None, None
    except Exception as e:
        logger.error(f"Error in retrieve_service_and_metrics: {e}")
        return None, None


def retrieve_metadata(event: dict) -> dict:
    """
    Retrieves metadata from the event tags based on the dimensions tag.

    Args:
        event (dict): The event containing tags.

    Returns:
        dict: A dictionary of metadata.
    """
    try:
        metadata: dict = {}

        for tag, value in event.get('tags', {}).items():
            if f"{company_tag}:{monitor_tag}:{dimensions_tag}" in tag:
                split_string = tag.split(':')
                if len(split_string) >= 4:
                    metadata[split_string[3]] = value

        if metadata:
            logger.info(f"Successfully retrieved metadata: {metadata}")
        else:
            logger.warning("No metadata found.")
        return metadata
    except Exception as e:
        logger.error(f"Error in retrieve_metadata: {e}")
        return {}


def retrieve_volume_data(event: dict) -> list:
    """
    Retrieves EC2 disk metadata from the event tags.

    Args:
        event (dict): The event containing tags.

    Returns:
        list: A list of dictionaries containing EC2 disk configurations.
    """
    try:
        volume_data: list = []

        for tag, value in event.get('tags', {}).items():
            if f"{company_tag}:{monitor_tag}:EC2:{ec2_linux_disk_tag}" in tag:
                volume_data.extend(parse_linux_disk_data(value))
            elif f"{company_tag}:{monitor_tag}:EC2:{ec2_windows_disk_tag}" in tag:
                volume_data.extend(parse_windows_disk_data(value))

        if volume_data:
            logger.info(f"Successfully retrieved EC2 disk metric data: {volume_data}")
        else:
            logger.warning("No EC2 disk metric data found.")
        return volume_data
    except Exception as e:
        logger.error(f"Error in retrieve_volume_data: {e}")
        return []


def parse_linux_disk_data(value: str) -> list:
    """
    Parses EC2 Linux disk data from a string value.

    Args:
        value (str): The tag value containing disk configurations.

    Returns:
        list: A list of dictionaries for each disk configuration.
    """
    disk_data: list = []
    try:
        for unit in value.split(';'):
            parts = unit.split(',')
            if len(parts) >= 3:
                disk_data.append({'device': parts[0], 'fstype': parts[1], 'path': parts[2]})
    except ValueError as e:
        logger.error(f"Error parsing disk data: {e}")
    return disk_data


def parse_windows_disk_data(value: str) -> list:
    """
    Parses EC2 Windows disk data from a string value.

    Args:
        value (str): The tag value containing disk configurations.

    Returns:
        list: A list of dictionaries for each disk configuration.
    """
    disk_data: list = []
    try:
        for unit in value.split(';'):
            parts = unit.split(',')
            if len(parts) >= 2:
                disk_data.append({'objectname': parts[0], 'instance': parts[1]})
    except ValueError as e:
        logger.error(f"Error parsing disk data: {e}")
    return disk_data


def retrieve_identifier_data(event: dict) -> str | None:
    """
    Retrieves the identifier data from the event tags.

    Args:
        event (dict): The event containing tags.

    Returns:
        str or None: The identifier tag value if found, otherwise None.
    """
    try:
        for tag, value in event.get('tags', {}).items():
            if f"{company_tag}:{monitor_tag}:{identifier_tag}" in tag:
                logger.info(f"Successfully retrieved identifier tag: {value}")
                return value
        logger.warning("Identifier tag not found.")
        return None
    except Exception as e:
        logger.error(f"Error in retrieve_identifier_data: {e}")
        return None
