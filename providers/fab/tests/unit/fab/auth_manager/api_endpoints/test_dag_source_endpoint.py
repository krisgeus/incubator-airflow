# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
from __future__ import annotations

import ast
import os

import pytest

from airflow.models import DagBag
from airflow.providers.fab.www.security import permissions
from unit.fab.auth_manager.api_endpoints.api_connexion_utils import create_user, delete_user

from tests_common.test_utils.db import (
    clear_db_dag_code,
    clear_db_dags,
    clear_db_serialized_dags,
    parse_and_sync_to_db,
)
from tests_common.test_utils.version_compat import AIRFLOW_V_3_0_PLUS

pytestmark = [
    pytest.mark.db_test,
    pytest.mark.skipif(not AIRFLOW_V_3_0_PLUS, reason="Test requires Airflow 3.0+"),
]


EXAMPLE_DAG_ID = "example_bash_operator"
TEST_DAG_ID = "latest_only"
NOT_READABLE_DAG_ID = "latest_only_with_trigger"
TEST_MULTIPLE_DAGS_ID = "asset_produces_1"


@pytest.fixture(scope="module")
def configured_app(minimal_app_for_auth_api):
    app = minimal_app_for_auth_api
    create_user(
        app,
        username="test",
        role_name="Test",
        permissions=[(permissions.ACTION_CAN_READ, permissions.RESOURCE_DAG_CODE)],
    )
    app.appbuilder.sm.sync_perm_for_dag(
        TEST_DAG_ID,
        access_control={"Test": [permissions.ACTION_CAN_READ]},
    )
    app.appbuilder.sm.sync_perm_for_dag(
        EXAMPLE_DAG_ID,
        access_control={"Test": [permissions.ACTION_CAN_READ]},
    )
    app.appbuilder.sm.sync_perm_for_dag(
        TEST_MULTIPLE_DAGS_ID,
        access_control={"Test": [permissions.ACTION_CAN_READ]},
    )

    yield app

    delete_user(app, username="test")


class TestGetSource:
    @pytest.fixture(autouse=True)
    def setup_attrs(self, configured_app) -> None:
        self.app = configured_app
        self.client = self.app.test_client()  # type:ignore
        self.clear_db()

    def teardown_method(self) -> None:
        self.clear_db()

    @staticmethod
    def clear_db():
        clear_db_dags()
        clear_db_serialized_dags()
        clear_db_dag_code()

    @staticmethod
    def _get_dag_file_docstring(fileloc: str) -> str | None:
        with open(fileloc) as f:
            file_contents = f.read()
        module = ast.parse(file_contents)
        docstring = ast.get_docstring(module)
        return docstring

    def test_should_respond_403_not_readable(self, url_safe_serializer):
        parse_and_sync_to_db(os.devnull, include_examples=True)
        dagbag = DagBag(read_dags_from_db=True)
        dag = dagbag.get_dag(NOT_READABLE_DAG_ID)

        response = self.client.get(
            f"/api/v1/dagSources/{dag.dag_id}",
            headers={"Accept": "text/plain"},
            environ_overrides={"REMOTE_USER": "test"},
        )
        read_dag = self.client.get(
            f"/api/v1/dags/{NOT_READABLE_DAG_ID}",
            environ_overrides={"REMOTE_USER": "test"},
        )
        assert response.status_code == 403
        assert read_dag.status_code == 403

    def test_should_respond_403_some_dags_not_readable_in_the_file(self, url_safe_serializer):
        parse_and_sync_to_db(os.devnull, include_examples=True)
        dagbag = DagBag(read_dags_from_db=True)
        dag = dagbag.get_dag(TEST_MULTIPLE_DAGS_ID)

        response = self.client.get(
            f"/api/v1/dagSources/{dag.dag_id}",
            headers={"Accept": "text/plain"},
            environ_overrides={"REMOTE_USER": "test"},
        )

        read_dag = self.client.get(
            f"/api/v1/dags/{TEST_MULTIPLE_DAGS_ID}",
            environ_overrides={"REMOTE_USER": "test"},
        )
        assert response.status_code == 403
        assert read_dag.status_code == 200
