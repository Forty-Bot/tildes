# Copyright (c) 2018 Tildes contributors <code@tildes.net>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Script for doing the initial setup of database tables."""
# pylint: disable=unused-wildcard-import,wildcard-import,wrong-import-order

import os
import subprocess
from typing import Optional

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Connectable, Engine

from tildes.database_models import *  # noqa
from tildes.lib.database import get_session_from_config
from tildes.models import DatabaseModel
from tildes.models.group import Group, GroupSubscription
from tildes.models.log import Log
from tildes.models.user import User


def initialize_db(config_path: str, alembic_config_path: Optional[str] = None) -> None:
    """Load the app config and create the database tables.

    This function will probably only complete successfully when run as user postgres,
    since the run_sql_scripts_in_dir method runs psql through that user to be able to
    create functions using untrusted languages (PL/Python specifically).
    """
    db_session = get_session_from_config(config_path)
    engine = db_session.bind

    create_tables(engine)

    run_sql_scripts_in_dir("sql/init/", engine)

    # if an Alembic config file wasn't specified, assume it's alembic.ini in the same
    # directory
    if not alembic_config_path:
        path = os.path.split(config_path)[0]
        alembic_config_path = os.path.join(path, "alembic.ini")

    # mark current Alembic revision in db so migrations start from this point
    alembic_cfg = Config(alembic_config_path)
    command.stamp(alembic_cfg, "head")


def create_tables(connectable: Connectable) -> None:
    """Create the database tables."""
    # tables to skip (due to inheritance or other need to create manually)
    excluded_tables = Log.INHERITED_TABLES + ["log"]

    tables = [
        table
        for table in DatabaseModel.metadata.tables.values()
        if table.name not in excluded_tables
    ]
    DatabaseModel.metadata.create_all(connectable, tables=tables)

    # create log table (and inherited ones) last
    DatabaseModel.metadata.create_all(connectable, tables=[Log.__table__])


def run_sql_scripts_in_dir(path: str, engine: Engine) -> None:
    """Run all sql scripts in a directory, as the database superuser."""
    for root, _, files in os.walk(path):
        sql_files = [filename for filename in files if filename.endswith(".sql")]
        for sql_file in sql_files:
            subprocess.call(
                [
                    "psql",
                    "-U",
                    "postgres",
                    "-f",
                    os.path.join(root, sql_file),
                    engine.url.database,
                ]
            )


def insert_dev_data(config_path: str) -> None:
    """Load the app config and insert some "starter" data for a dev version."""
    session = get_session_from_config(config_path)

    user = User("TestUser", "password")
    group = Group("testing", "An automatically created group to use for testing")
    subscription = GroupSubscription(user, group)
    motte_group = Group(
        "themotte", "Themotte group, automatically created for the dev environment"
    )
    motte_subscription = GroupSubscription(user, motte_group)
    session.add_all([user, group, subscription, motte_group, motte_subscription])

    session.commit()
