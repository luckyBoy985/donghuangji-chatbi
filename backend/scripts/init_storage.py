from __future__ import annotations

import boto3
from botocore.exceptions import ClientError

from backend.app.core.config import settings


def main() -> None:
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name="us-east-1",
    )
    try:
        client.head_bucket(Bucket=settings.s3_bucket)
    except ClientError:
        client.create_bucket(Bucket=settings.s3_bucket)
    print(f"bucket ready: {settings.s3_bucket}")


if __name__ == "__main__":
    main()
