import json
import os
import boto3
import urllib3

http = urllib3.PoolManager()

def send_response(event, context, status, reason):
    response_body = {
        "Status": status,
        "Reason": reason,
        "PhysicalResourceId": context.log_stream_name,
        "StackId": event["StackId"],
        "RequestId": event["RequestId"],
        "LogicalResourceId": event["LogicalResourceId"],
        "Data": {}
    }

    encoded = json.dumps(response_body).encode("utf-8")
    try:
        http.request("PUT", event["ResponseURL"], body=encoded, headers={"Content-Type": ""})
    except Exception as e:
        print("Failed to send CloudFormation response:", e)

def lambda_handler(event, context):
    try:
        if event["RequestType"] == "Delete":
            send_response(event, context, "SUCCESS", "Delete request ignored.")
            return

        table_name = os.environ["alarm_table"]
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(table_name)

        seed_items = [

            # EC2 CPU
            {
                "service": "EC2",
                "metric_name": "CPUUtilization",
                "datapoints_to_alarm": 15,
                "evaluation_periods": 15,
                "period": 60,
                "statistic": "Average",
                "treat_missing_data": "breaching",
                "actions_enabled": True,
                "alarm_description": "Triggered when CPU exceeds thresholds or becomes unreachable",
                "comparison_operator": "GreaterThanThreshold",
                "dimensions": [{"Name": "InstanceId", "Value": "InstanceId"}],
                "namespace": "AWS/EC2",
                "thresholds": [
                    {"criticality": "Critical", "threshold": 95, "priority": "P1"},
                    {"criticality": "High", "threshold": 90, "priority": "P2"},
                    {"criticality": "Low", "threshold": 80, "priority": "P3"}
                ]
            },

            # EC2 StatusCheckFailed (P1 only)
            {
                "service": "EC2",
                "metric_name": "StatusCheckFailed_Instance",
                "datapoints_to_alarm": 1,
                "evaluation_periods": 1,
                "period": 60,
                "statistic": "Maximum",
                "treat_missing_data": "breaching",
                "actions_enabled": True,
                "alarm_description": "Instance status check has failed.",
                "comparison_operator": "GreaterThanThreshold",
                "dimensions": [{"Name": "InstanceId", "Value": "InstanceId"}],
                "namespace": "AWS/EC2",
                "thresholds": [
                    {"criticality": "Critical", "threshold": 1, "priority": "P1"}
                ]
            },

            # EC2 Linux Memory Utilization
            {
                "service": "EC2",
                "metric_name": "mem_used_percent",
                "datapoints_to_alarm": 15,
                "evaluation_periods": 15,
                "period": 60,
                "statistic": "Average",
                "treat_missing_data": "breaching",
                "actions_enabled": True,
                "alarm_description": "Linux memory usage exceeds thresholds",
                "comparison_operator": "GreaterThanThreshold",
                "dimensions": [
                    {"Name": "InstanceId", "Value": "InstanceId"},
                    {"Name": "InstanceType", "Value": "InstanceType"},
                    {"Name": "ImageId", "Value": "ImageId"},
                    {"Name": "AutoScalingGroup", "Value": "AutoScalingGroup"}
                ],
                "namespace": "CWAgent",
                "thresholds": [
                    {"criticality": "Critical", "threshold": 95, "priority": "P1"},
                    {"criticality": "High", "threshold": 90, "priority": "P2"},
                    {"criticality": "Low", "threshold": 80, "priority": "P3"}
                ]
            },

            # EC2 Windows Memory Utilization
            {
                "service": "EC2",
                "metric_name": "Memory % Committed Bytes In Use",
                "datapoints_to_alarm": 15,
                "evaluation_periods": 15,
                "period": 60,
                "statistic": "Average",
                "treat_missing_data": "breaching",
                "actions_enabled": True,
                "alarm_description": "Windows memory usage exceeds thresholds",
                "comparison_operator": "GreaterThanThreshold",
                "dimensions": [
                    {"Name": "InstanceId", "Value": "InstanceId"},
                    {"Name": "InstanceType", "Value": "InstanceType"},
                    {"Name": "ImageId", "Value": "ImageId"},
                    {"Name": "AutoScalingGroup", "Value": "AutoScalingGroup"}
                ],
                "namespace": "CWAgent",
                "thresholds": [
                    {"criticality": "Critical", "threshold": 95, "priority": "P1"},
                    {"criticality": "High", "threshold": 90, "priority": "P2"},
                    {"criticality": "Low", "threshold": 80, "priority": "P3"}
                ]
            },

            # EC2 Linux Disk Usage
            {
                "service": "EC2",
                "metric_name": "disk_used_percent",
                "datapoints_to_alarm": 15,
                "evaluation_periods": 15,
                "period": 60,
                "statistic": "Average",
                "treat_missing_data": "breaching",
                "actions_enabled": True,
                "alarm_description": "Linux disk usage exceeds thresholds",
                "comparison_operator": "GreaterThanThreshold",
                "dimensions": [
                    {"Name": "InstanceId", "Value": "InstanceId"},
                    {"Name": "InstanceType", "Value": "InstanceType"},
                    {"Name": "ImageId", "Value": "ImageId"},
                    {"Name": "AutoScalingGroup", "Value": "AutoScalingGroup"}
                ],
                "namespace": "CWAgent",
                "thresholds": [
                    {"criticality": "Critical", "threshold": 95, "priority": "P1"},
                    {"criticality": "High", "threshold": 90, "priority": "P2"},
                    {"criticality": "Low", "threshold": 80, "priority": "P3"}
                ]
            },

            # EC2 Windows Disk Usage
            {
                "service": "EC2",
                "metric_name": "LogicalDisk % Free Space",
                "datapoints_to_alarm": 15,
                "evaluation_periods": 15,
                "period": 60,
                "statistic": "Average",
                "treat_missing_data": "breaching",
                "actions_enabled": True,
                "alarm_description": "Windows disk free space falls below thresholds",
                "comparison_operator": "LessThanThreshold",
                "dimensions": [
                    {"Name": "InstanceId", "Value": "InstanceId"},
                    {"Name": "InstanceType", "Value": "InstanceType"},
                    {"Name": "ImageId", "Value": "ImageId"},
                    {"Name": "AutoScalingGroup", "Value": "AutoScalingGroup"}
                ],
                "namespace": "CWAgent",
                "thresholds": [
                    {"criticality": "Critical", "threshold": 5, "priority": "P1"},   # 5% free
                    {"criticality": "High", "threshold": 10, "priority": "P2"},     # 10% free
                    {"criticality": "Low", "threshold": 20, "priority": "P3"}       # 20% free
                ]
            },

            # RDS Free Storage
            {
                "service": "RDS",
                "metric_name": "FreeStorageSpace",
                "datapoints_to_alarm": 15,
                "evaluation_periods": 15,
                "period": 60,
                "statistic": "Minimum",
                "treat_missing_data": "breaching",
                "actions_enabled": True,
                "alarm_description": "Free storage falling below thresholds",
                "comparison_operator": "LessThanThreshold",
                "dimensions": [{"Name": "DBInstanceIdentifier", "Value": "DBInstanceIdentifier"}],
                "namespace": "AWS/RDS",
                "thresholds": [
                    {"criticality": "Critical", "threshold": 5000000000, "priority": "P1"},
                    {"criticality": "High", "threshold": 10000000000, "priority": "P2"},
                    {"criticality": "Low", "threshold": 20000000000, "priority": "P3"}
                ]
            },

            # ELB Unhealthy Hosts
            {
                "service": "ELB",
                "metric_name": "UnHealthyHostCount",
                "datapoints_to_alarm": 3,
                "evaluation_periods": 3,
                "period": 60,
                "statistic": "Average",
                "treat_missing_data": "notBreaching",
                "actions_enabled": True,
                "alarm_description": "One or more ELB hosts reported as unhealthy",
                "comparison_operator": "GreaterThanThreshold",
                "dimensions": [{"Name": "LoadBalancerName", "Value": "LoadBalancerName"}],
                "namespace": "AWS/ELB",
                "thresholds": [
                    {"criticality": "Critical", "threshold": 3, "priority": "P1"},
                    {"criticality": "High", "threshold": 2, "priority": "P2"},
                    {"criticality": "Low", "threshold": 1, "priority": "P3"}
                ]
            },

            # Lambda Errors
            {
                "service": "Lambda",
                "metric_name": "Errors",
                "datapoints_to_alarm": 2,
                "evaluation_periods": 2,
                "period": 60,
                "statistic": "Sum",
                "treat_missing_data": "notBreaching",
                "actions_enabled": True,
                "alarm_description": "Lambda function errors exceed thresholds",
                "comparison_operator": "GreaterThanThreshold",
                "dimensions": [{"Name": "FunctionName", "Value": "FunctionName"}],
                "namespace": "AWS/Lambda",
                "thresholds": [
                    {"criticality": "Critical", "threshold": 5, "priority": "P1"},
                    {"criticality": "High", "threshold": 3, "priority": "P2"},
                    {"criticality": "Low", "threshold": 1, "priority": "P3"}
                ]
            },

            # EBS Burst Balance
            {
                "service": "EBS",
                "metric_name": "BurstBalance",
                "datapoints_to_alarm": 3,
                "evaluation_periods": 3,
                "period": 60,
                "statistic": "Average",
                "treat_missing_data": "notBreaching",
                "actions_enabled": True,
                "alarm_description": "EBS burst balance running low",
                "comparison_operator": "LessThanThreshold",
                "dimensions": [{"Name": "VolumeId", "Value": "VolumeId"}],
                "namespace": "AWS/EBS",
                "thresholds": [
                    {"criticality": "Critical", "threshold": 10, "priority": "P1"},
                    {"criticality": "High", "threshold": 15, "priority": "P2"},
                    {"criticality": "Low", "threshold": 20, "priority": "P3"}
                ]
            },

            # DynamoDB Consumed Read Capacity
            {
                "service": "DynamoDB",
                "metric_name": "ConsumedReadCapacityUnits",
                "datapoints_to_alarm": 15,
                "evaluation_periods": 15,
                "period": 60,
                "statistic": "Sum",
                "treat_missing_data": "notBreaching",
                "actions_enabled": True,
                "alarm_description": "Read capacity usage approaching provisioned limit",
                "comparison_operator": "GreaterThanThreshold",
                "dimensions": [{"Name": "TableName", "Value": "TableName"}],
                "namespace": "AWS/DynamoDB",
                "thresholds": [
                    {"criticality": "Critical", "threshold": 90, "priority": "P1"},
                    {"criticality": "High", "threshold": 80, "priority": "P2"},
                    {"criticality": "Low", "threshold": 70, "priority": "P3"}
                ]
            },

            # DynamoDB Consumed Write Capacity
            {
                "service": "DynamoDB",
                "metric_name": "ConsumedWriteCapacityUnits",
                "datapoints_to_alarm": 15,
                "evaluation_periods": 15,
                "period": 60,
                "statistic": "Sum",
                "treat_missing_data": "notBreaching",
                "actions_enabled": True,
                "alarm_description": "Write capacity usage approaching provisioned limit",
                "comparison_operator": "GreaterThanThreshold",
                "dimensions": [{"Name": "TableName", "Value": "TableName"}],
                "namespace": "AWS/DynamoDB",
                "thresholds": [
                    {"criticality": "Critical", "threshold": 90, "priority": "P1"},
                    {"criticality": "High", "threshold": 80, "priority": "P2"},
                    {"criticality": "Low", "threshold": 70, "priority": "P3"}
                ]
            },

            # DynamoDB System Errors
            {
                "service": "DynamoDB",
                "metric_name": "SystemErrors",
                "datapoints_to_alarm": 3,
                "evaluation_periods": 3,
                "period": 60,
                "statistic": "Sum",
                "treat_missing_data": "notBreaching",
                "actions_enabled": True,
                "alarm_description": "DynamoDB system errors detected",
                "comparison_operator": "GreaterThanThreshold",
                "dimensions": [{"Name": "TableName", "Value": "TableName"}],
                "namespace": "AWS/DynamoDB",
                "thresholds": [
                    {"criticality": "Critical", "threshold": 5, "priority": "P1"},
                    {"criticality": "High", "threshold": 3, "priority": "P2"},
                    {"criticality": "Low", "threshold": 1, "priority": "P3"}
                ]
            },

            # ---------------------------
            # S3
            # ---------------------------

            # S3 4xx Errors
            {
                "service": "S3",
                "metric_name": "4xxErrors",
                "datapoints_to_alarm": 15,
                "evaluation_periods": 15,
                "period": 60,
                "statistic": "Sum",
                "treat_missing_data": "notBreaching",
                "actions_enabled": True,
                "alarm_description": "S3 client errors (4xx) exceeding thresholds",
                "comparison_operator": "GreaterThanThreshold",
                "dimensions": [{"Name": "BucketName", "Value": "BucketName"}],
                "namespace": "AWS/S3",
                "thresholds": [
                    {"criticality": "Critical", "threshold": 1000, "priority": "P1"},
                    {"criticality": "High", "threshold": 500, "priority": "P2"},
                    {"criticality": "Low", "threshold": 100, "priority": "P3"}
                ]
            },

            # S3 5xx Errors
            {
                "service": "S3",
                "metric_name": "5xxErrors",
                "datapoints_to_alarm": 15,
                "evaluation_periods": 15,
                "period": 60,
                "statistic": "Sum",
                "treat_missing_data": "notBreaching",
                "actions_enabled": True,
                "alarm_description": "S3 server errors (5xx) exceeding thresholds",
                "comparison_operator": "GreaterThanThreshold",
                "dimensions": [{"Name": "BucketName", "Value": "BucketName"}],
                "namespace": "AWS/S3",
                "thresholds": [
                    {"criticality": "Critical", "threshold": 100, "priority": "P1"},
                    {"criticality": "High", "threshold": 50, "priority": "P2"},
                    {"criticality": "Low", "threshold": 10, "priority": "P3"}
                ]
            },

            # S3 First Byte Latency
            {
                "service": "S3",
                "metric_name": "FirstByteLatency",
                "datapoints_to_alarm": 15,
                "evaluation_periods": 15,
                "period": 60,
                "statistic": "Average",
                "treat_missing_data": "notBreaching",
                "actions_enabled": True,
                "alarm_description": "S3 latency exceeds thresholds",
                "comparison_operator": "GreaterThanThreshold",
                "dimensions": [{"Name": "BucketName", "Value": "BucketName"}],
                "namespace": "AWS/S3",
                "thresholds": [
                    {"criticality": "Critical", "threshold": 1000, "priority": "P1"},  # ms
                    {"criticality": "High", "threshold": 500, "priority": "P2"},
                    {"criticality": "Low", "threshold": 200, "priority": "P3"}
                ]
            },

            # ---------------------------
            # ECS
            # ---------------------------

            # ECS CPU Utilization
            {
                "service": "ECS",
                "metric_name": "CPUUtilization",
                "datapoints_to_alarm": 15,
                "evaluation_periods": 15,
                "period": 60,
                "statistic": "Average",
                "treat_missing_data": "breaching",
                "actions_enabled": True,
                "alarm_description": "ECS CPU usage exceeds thresholds",
                "comparison_operator": "GreaterThanThreshold",
                "dimensions": [{"Name": "ClusterName", "Value": "ClusterName"}],
                "namespace": "AWS/ECS",
                "thresholds": [
                    {"criticality": "Critical", "threshold": 95, "priority": "P1"},
                    {"criticality": "High", "threshold": 90, "priority": "P2"},
                    {"criticality": "Low", "threshold": 80, "priority": "P3"}
                ]
            },

            # ECS Memory Utilization
            {
                "service": "ECS",
                "metric_name": "MemoryUtilization",
                "datapoints_to_alarm": 15,
                "evaluation_periods": 15,
                "period": 60,
                "statistic": "Average",
                "treat_missing_data": "breaching",
                "actions_enabled": True,
                "alarm_description": "ECS memory usage exceeds thresholds",
                "comparison_operator": "GreaterThanThreshold",
                "dimensions": [{"Name": "ClusterName", "Value": "ClusterName"}],
                "namespace": "AWS/ECS",
                "thresholds": [
                    {"criticality": "Critical", "threshold": 95, "priority": "P1"},
                    {"criticality": "High", "threshold": 90, "priority": "P2"},
                    {"criticality": "Low", "threshold": 80, "priority": "P3"}
                ]
            },

            # ---------------------------
            # API Gateway
            # ---------------------------

            # API Gateway 5XX Errors
            {
                "service": "APIGateway",
                "metric_name": "5XXError",
                "datapoints_to_alarm": 3,
                "evaluation_periods": 3,
                "period": 60,
                "statistic": "Sum",
                "treat_missing_data": "notBreaching",
                "actions_enabled": True,
                "alarm_description": "API Gateway 5xx errors detected",
                "comparison_operator": "GreaterThanThreshold",
                "dimensions": [{"Name": "ApiName", "Value": "ApiName"}],
                "namespace": "AWS/ApiGateway",
                "thresholds": [
                    {"criticality": "Critical", "threshold": 100, "priority": "P1"},
                    {"criticality": "High", "threshold": 50, "priority": "P2"},
                    {"criticality": "Low", "threshold": 10, "priority": "P3"}
                ]
            },

            # API Gateway 4XX Errors
            {
                "service": "APIGateway",
                "metric_name": "4XXError",
                "datapoints_to_alarm": 15,
                "evaluation_periods": 15,
                "period": 60,
                "statistic": "Sum",
                "treat_missing_data": "notBreaching",
                "actions_enabled": True,
                "alarm_description": "API Gateway 4xx errors detected",
                "comparison_operator": "GreaterThanThreshold",
                "dimensions": [{"Name": "ApiName", "Value": "ApiName"}],
                "namespace": "AWS/ApiGateway",
                "thresholds": [
                    {"criticality": "Critical", "threshold": 1000, "priority": "P1"},
                    {"criticality": "High", "threshold": 500, "priority": "P2"},
                    {"criticality": "Low", "threshold": 100, "priority": "P3"}
                ]
            },

            # API Gateway Latency
            {
                "service": "APIGateway",
                "metric_name": "Latency",
                "datapoints_to_alarm": 15,
                "evaluation_periods": 15,
                "period": 60,
                "statistic": "Average",
                "treat_missing_data": "notBreaching",
                "actions_enabled": True,
                "alarm_description": "API Gateway latency exceeds thresholds",
                "comparison_operator": "GreaterThanThreshold",
                "dimensions": [{"Name": "ApiName", "Value": "ApiName"}],
                "namespace": "AWS/ApiGateway",
                "thresholds": [
                    {"criticality": "Critical", "threshold": 2000, "priority": "P1"},  # ms
                    {"criticality": "High", "threshold": 1500, "priority": "P2"},
                    {"criticality": "Low", "threshold": 1000, "priority": "P3"}
                ]
            },

            # ---------------------------
            # CloudFront
            # ---------------------------

            # CloudFront 5xx Error Rate
            {
                "service": "CloudFront",
                "metric_name": "5xxErrorRate",
                "datapoints_to_alarm": 3,
                "evaluation_periods": 3,
                "period": 60,
                "statistic": "Average",
                "treat_missing_data": "notBreaching",
                "actions_enabled": True,
                "alarm_description": "CloudFront 5xx error rate exceeds thresholds",
                "comparison_operator": "GreaterThanThreshold",
                "dimensions": [{"Name": "DistributionId", "Value": "DistributionId"}],
                "namespace": "AWS/CloudFront",
                "thresholds": [
                    {"criticality": "Critical", "threshold": 5, "priority": "P1"},   # %
                    {"criticality": "High", "threshold": 3, "priority": "P2"},
                    {"criticality": "Low", "threshold": 1, "priority": "P3"}
                ]
            },

            # CloudFront Total Error Rate
            {
                "service": "CloudFront",
                "metric_name": "TotalErrorRate",
                "datapoints_to_alarm": 3,
                "evaluation_periods": 3,
                "period": 60,
                "statistic": "Average",
                "treat_missing_data": "notBreaching",
                "actions_enabled": True,
                "alarm_description": "CloudFront total error rate exceeds thresholds",
                "comparison_operator": "GreaterThanThreshold",
                "dimensions": [{"Name": "DistributionId", "Value": "DistributionId"}],
                "namespace": "AWS/CloudFront",
                "thresholds": [
                    {"criticality": "Critical", "threshold": 10, "priority": "P1"},  # %
                    {"criticality": "High", "threshold": 5, "priority": "P2"},
                    {"criticality": "Low", "threshold": 2, "priority": "P3"}
                ]
            },

            # ---------------------------
            # RDS (more depth)
            # ---------------------------

            # RDS CPU Utilization
            {
                "service": "RDS",
                "metric_name": "CPUUtilization",
                "datapoints_to_alarm": 15,
                "evaluation_periods": 15,
                "period": 60,
                "statistic": "Average",
                "treat_missing_data": "breaching",
                "actions_enabled": True,
                "alarm_description": "RDS CPU usage exceeds thresholds",
                "comparison_operator": "GreaterThanThreshold",
                "dimensions": [{"Name": "DBInstanceIdentifier", "Value": "DBInstanceIdentifier"}],
                "namespace": "AWS/RDS",
                "thresholds": [
                    {"criticality": "Critical", "threshold": 95, "priority": "P1"},
                    {"criticality": "High", "threshold": 90, "priority": "P2"},
                    {"criticality": "Low", "threshold": 80, "priority": "P3"}
                ]
            },

            # RDS Database Connections
            {
                "service": "RDS",
                "metric_name": "DatabaseConnections",
                "datapoints_to_alarm": 15,
                "evaluation_periods": 15,
                "period": 60,
                "statistic": "Average",
                "treat_missing_data": "breaching",
                "actions_enabled": True,
                "alarm_description": "RDS connections approaching limit",
                "comparison_operator": "GreaterThanThreshold",
                "dimensions": [{"Name": "DBInstanceIdentifier", "Value": "DBInstanceIdentifier"}],
                "namespace": "AWS/RDS",
                "thresholds": [
                    {"criticality": "Critical", "threshold": 1000, "priority": "P1"},
                    {"criticality": "High", "threshold": 750, "priority": "P2"},
                    {"criticality": "Low", "threshold": 500, "priority": "P3"}
                ]
            },

            # RDS Freeable Memory
            {
                "service": "RDS",
                "metric_name": "FreeableMemory",
                "datapoints_to_alarm": 15,
                "evaluation_periods": 15,
                "period": 60,
                "statistic": "Minimum",
                "treat_missing_data": "breaching",
                "actions_enabled": True,
                "alarm_description": "RDS freeable memory falling below thresholds",
                "comparison_operator": "LessThanThreshold",
                "dimensions": [{"Name": "DBInstanceIdentifier", "Value": "DBInstanceIdentifier"}],
                "namespace": "AWS/RDS",
                "thresholds": [
                    {"criticality": "Critical", "threshold": 200000000, "priority": "P1"},  # ~200MB
                    {"criticality": "High", "threshold": 500000000, "priority": "P2"},    # ~500MB
                    {"criticality": "Low", "threshold": 1000000000, "priority": "P3"}     # ~1GB
                ]
            }
        ]


        with table.batch_writer() as batch:
            for item in seed_items:
                batch.put_item(Item=item)

        send_response(event, context, "SUCCESS", "AlarmTable seeded with full metrics.")

    except Exception as e:
        print("Seeding error:", e)
        send_response(event, context, "FAILED", str(e))
        raise
