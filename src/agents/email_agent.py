import os
from typing import Dict

import boto3
from agents import Agent, function_tool

from src.config.settings import (
    DEFAULT_AWS_REGION,
    EMAIL_MODEL,
    RECIPIENT,
    SENDER,
)


@function_tool
def send_email(subject: str, html_body: str) -> Dict[str, str]:
    """Send an email with the given subject and HTML body via SES."""
    region_name = os.environ.get("AWS_DEFAULT_REGION", DEFAULT_AWS_REGION)
    try:
        client = boto3.client("ses", region_name=region_name)
        response = client.send_email(
            Source=SENDER,
            Destination={"ToAddresses": [RECIPIENT]},
            Message={
                "Subject": {"Data": subject},
                "Body": {"Html": {"Data": html_body}},
            },
        )
        print("Email response", response.get("MessageId"))
        return {"status": "success"}
    except Exception as exc:
        print("Email error", str(exc))
        return {"status": "error", "message": str(exc)}


INSTRUCTIONS = """You are able to send a nicely formatted HTML email based on a detailed report.
You will be provided with a detailed report. You should use your tool to send one email, providing the
report converted into clean, well presented HTML with an appropriate subject line.
You can edit the text for clarity and presentation purposes, 
but do not remove any information, sections or citations present in the original text."""

email_agent = Agent(
    name="Email agent",
    instructions=INSTRUCTIONS,
    tools=[send_email],
    model=EMAIL_MODEL,
)
