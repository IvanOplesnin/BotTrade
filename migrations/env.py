import asyncio
import os
from logging.config import fileConfig

import yaml
from sqlalchemy import pool

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

server_address = os.getenv("ADDRESS")
config_file = os.getenv("CONFIG_FILE")
if not config_file:
    config_file = r"C:\Users\aples\PycharmProjects\BotTrade\test_config.yaml"
with open(config_file, "r") as f:
    sqlalchemy_url = yaml.load(f, Loader=yaml.FullLoader)["db-pgsql"]['address']
    sqlalchemy_url = sqlalchemy_url.replace("db", server_address).replace("5432", "5437")
    config.set_main_option("sqlalchemy.url", sqlalchemy_url)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
from database.pgsql.models import Base

target_metadata = Base.metadata


# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online():
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
