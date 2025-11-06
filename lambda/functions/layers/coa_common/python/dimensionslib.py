from taglib import retrieve_identifier_data
from loglib import logger
from typing import Tuple


def update_identifier(event: dict, item: object) -> Tuple[object, str]:
    """
    Updates the item's dimensions with the identifier value from the event.

    Args:
        event (dict): Event data containing resource and identifier information.
        item (Any): An object that contains dimensions to be updated.

    Returns:
        Any: Updated item with modified dimensions.
    """
    logger.info(f"Updating identifier for item: {item}")
    
    try:
        identifier: str | None = retrieve_identifier_data(event)
        logger.info(f"Retrieved identifier: {identifier}")

        if hasattr(item, 'dimensions') and isinstance(item.dimensions, list):
            for dimension in item.dimensions:
                if dimension.get("Name") == identifier:
                    logger.info(f"Updating dimension '{identifier}' with value: {event['resource_id']}")
                    dimension["Value"] = event['resource_id']
        else:
            raise AttributeError("The 'dimensions' attribute is missing or not a list.")

        return item, identifier
    except KeyError as e:
        logger.error(f"KeyError in update_identifier: Missing key {e} in event.")
        raise
    except AttributeError as e:
        logger.error(f"AttributeError in update_identifier: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in update_identifier: {e}")
        raise


def update_dimensions(event: dict, item: object, meta_data: dict) -> object:
    """
    Updates the item's dimensions with metadata values.

    Args:
        event (dict): Event data containing resource and identifier information.
        item (Any): An object that contains dimensions to be updated.
        meta_data (dict): Metadata mapping dimension names to their values.

    Returns:
        Any: Updated item with modified dimensions.
    """
    logger.info(f"Updating dimensions for item with metadata: {meta_data}")
    
    try:
        # Update identifier first
        item, identifier = update_identifier(event, item)

        # Update dimensions with metadata
        if hasattr(item, 'dimensions') and isinstance(item.dimensions, list):
            for dimension in item.dimensions:
                dimension_name = dimension.get("Name")
                if dimension_name in meta_data:
                    logger.info(f"Updating dimension '{dimension_name}' with value: {meta_data[dimension_name]}")
                    dimension["Value"] = meta_data[dimension_name]
                elif dimension_name != identifier:
                    logger.info(f"Dimension not found in meta data tags. Removing dimension: {dimension}")
                    item.dimensions.remove(dimension)
        else:
            raise AttributeError("The 'dimensions' attribute is missing or not a list.")

        return item
    except KeyError as e:
        logger.error(f"KeyError in update_dimensions: Missing key {e} in metadata.")
        raise
    except AttributeError as e:
        logger.error(f"AttributeError in update_dimensions: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in update_dimensions: {e}")
        raise
