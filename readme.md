# COA – Cloud Observability Alarms (COA)

**COA** is a modular, event-driven monitoring framework designed to automatically generate and manage CloudWatch alarms across AWS services using tags, custom configurations, and centralized orchestration.

## Overview

This solution provides:

- Intelligent alarm creation based on tagged AWS resources
- Custom thresholds via a prepopulated DynamoDB config table
- Event-driven processing using EventBridge and Step Functions
- Structured observability with AWS Lambda Powertools for logging, metrics, and tracing

The goal is zero-touch alarm coverage for EC2 and beyond, all managed declaratively via tagging.

## Architecture

```
Resource Tag Change or EC2 Termination
              │
              ▼
       EventBridge Rule
              │
              ▼
        Step Function (or Lambda)
              │
              ▼
    DynamoDB (config) + CloudWatch Alarms
```

### Key Components:
- **EventBridge**: Triggers workflows based on tag changes or instance termination
- **Step Functions**: Manages complex orchestration logic
- **Lambdas**:
  - `create_alarm`: Builds and deploys CloudWatch alarms
  - `seed_dynamodb`: Prepopulates alarm configs for common AWS metrics
- **DynamoDB Tables**:
  - `AlarmTable`: Stores alarm configs
  - `ClientTable`: Reserved for client-specific metadata

## Deployment

This project uses **AWS SAM** and can be deployed via GitHub Actions.

### Requirements:
- AWS CLI + credentials (OIDC or assumed role)
- SAM CLI installed
- GitHub Actions configured with:
  ```yaml
  - uses: aws-actions/configure-aws-credentials
    with:
      role-to-assume: arn:aws:iam::<account-id>:role/coa-github-actions-role
  ```

### Manual CLI Deploy:

```bash
sam build --use-container
sam deploy --guided
```

## Local Testing

You can invoke the functions locally using SAM CLI:

```bash
sam local invoke CreateAlarmFunction --event events/sample-event.json
```

Or test event ingestion:

```bash
aws events put-events --entries file://events/test-termination.json
```

## Configuration

All runtime config is passed via environment variables and the `template.yaml` stack parameters:

- `AlarmTable` and `ClientTable`
- Tag identifiers: `<COMPANY>`, `Supported`, `Monitored`, etc.
- Metric tags: `disk_used_percent`, `StatusCheckFailed`, etc.

Update seed data in `functions/seed_dynamodb/app.py` to define new service alarms.

## Security

- Least privilege IAM roles per Lambda
- EventBus policy can be scoped to specific accounts if needed
- DynamoDB and Lambda access controlled via environment and SAM permissions

## Supported Alarms (by default)

- EC2:
  - CPUUtilization
  - StatusCheckFailed
  - Disk usage (Linux/Windows)
- RDS, ELB, and others can be added easily via the config layer.

## Logging & Tracing

- Lambda Powertools enabled:
  - Structured JSON logs
  - Cold start tracking
  - AWS X-Ray tracing
- Logs can be viewed in CloudWatch under each function’s log group

## Usage

To trigger alarm creation, tag your AWS resources using the following format:

### Required Tag
- **Key**: `<COMPANY>:Monitored`
- **Value**: `true` (case-insensitive)

This signals the system to include the resource in the monitoring workflow.

### Optional Tags (For More Control)
- **<COMPANY>:Company** – Used to categorize resources by client or business unit
- **<COMPANY>:Supported** – Boolean flag indicating ownership or SLA requirement
- **<COMPANY>:Dimension** – Used to map to specific CloudWatch metric dimensions
- **<COMPANY>:Identifier** – Resource-specific identifier (like InstanceId)

When a tagged resource is created or updated:
1. An **EventBridge rule** captures the tag change.
2. The event is forwarded to a **Step Function** or **Lambda function**.
3. The service reads the **alarm config from DynamoDB** and creates CloudWatch alarms dynamically.

### Example (EC2 Console Tagging)
| Key               | Value      |
|------------------|------------|
| <COMPANY>:Monitored | true       |
| <COMPANY>:Company   | <COMPANY>     |
| <COMPANY>:Supported | true       |

Ensure that your environment includes a seed configuration for the matching resource type (e.g., EC2, RDS) to successfully apply alarm thresholds.
