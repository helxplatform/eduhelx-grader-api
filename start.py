import os
import glob
import uvicorn
import asyncio
from dotenv import load_dotenv
from alembic.config import Config
from alembic import command
from app.services import LmsSyncService
from app.database import SessionLocal

def main(host, port, reload, workers):
    # Mapping table for special case filename transformations
    special_cases = {
        "postgres-password": "POSTGRES_PASSWORD"
    }

    # Paths where ConfigMap and Secret are mounted
    config_path = "/etc/grader-config"
    secret_path = "/etc/grader-secret"

    # Path where .env file will be created
    env_path = "/app/.env"

    # Check if running in Kubernetes
    if os.path.isdir(config_path) or os.path.isdir(secret_path):
        # Get list of all files in ConfigMap and Secret
        config_files = glob.glob(os.path.join(config_path, "*"))
        secret_files = glob.glob(os.path.join(secret_path, "*"))

        # Combine ConfigMap and Secret into a single .env file
        with open(env_path, "w") as env_file:
            for filepath in config_files + secret_files:
                filename = os.path.basename(filepath)
                key = special_cases.get(filename, filename)
                with open(filepath, "r") as file:
                    env_file.write(f"{key}={file.read().strip()}\n")

    # If .env file exists, turn it into env variables
    if os.path.exists(env_path):
        load_dotenv(env_path)

    # Run Alembic migrations
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")


    # Run setup wizard, if required.
    try:
        with SessionLocal() as session:
            lms_sync_service = LmsSyncService(session)
            asyncio.run(lms_sync_service.downsync())
    except ValueError as e:
        print(str(e))

    # Start the application
    uvicorn_args = ["uvicorn", "app.main:app", "--host", host, "--port", port]
    if reload: uvicorn_args.append("--reload")
    if workers: uvicorn_args.append("--workers")
    if reload: workers = None
    portInt = int(port)
    # subprocess.run(uvicorn_args)
    uvicorn.run("app.main:app", host=host, port=portInt, reload=reload, workers=workers)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-H", "--host", default="0.0.0.0", help="The host to bind to.")
    parser.add_argument("-p", "--port", default="8000", help="The port to bind to.")
    parser.add_argument_group('Production vs. Development', 'One of these options must be chosen. --reload is most useful when developing; never use it in production. Use --workers in production.')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-r", "--reload", action="store_true", help="Enable auto-reload.")
    group.add_argument("-w", "--workers", help="Workers help")
    args = parser.parse_args()
    
    host = args.host
    port = args.port
    reload = args.reload
    workers = args.workers
    main(host, port, reload, workers)
