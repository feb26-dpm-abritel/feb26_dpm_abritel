"""DAG VoC : extract → refine+load → dbt → marts → alertes/tickets.

Cadence : quotidienne. Tout tourne en local au sein du worker Airflow
(les tâches Python sont in-process via PythonOperator pour éviter de cloner
l'env et partager la même stack Postgres/chemins `VOC_DATA_DIR`).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

DBT_DIR = "/opt/airflow/dbt"
DBT_PROFILES_DIR = "/opt/airflow/dbt"

default_args = {
    "owner": "voc",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}


def _extract_callable(**_):
    """Scrape les 3 sources × 3 marques et écrit en bronze (parquet)."""
    from voc.ingestion.runner import run

    path = run()
    return path


def _refine_load_callable(**context):
    """Lit le bronze → quality filter + categorize → Postgres raw.raw_reviews."""
    from voc.warehouse.loader import load

    bronze_path = context["ti"].xcom_pull(task_ids="extract")
    n = load(bronze_path)
    return n


def _llm_classify_callable(**_):
    """Reclasse les avis 'non_classe' via Ollama (best-effort, no-fail)."""
    from voc.refinement.llm_classify import refine_unclassified

    try:
        return refine_unclassified()
    except Exception as exc:  # noqa: BLE001 — étape non-bloquante volontairement
        import logging

        logging.getLogger(__name__).warning("LLM classify failed, skipping: %s", exc)
        return {"candidates": 0, "updated": 0, "skipped": 0, "error": str(exc)}


def _alerts_callable(**_):
    from voc.activation.alerting import detect

    return detect()


def _tickets_callable(**_):
    from voc.activation.ticketing import generate

    return generate()


def _slack_callable(**context):
    """Notification Slack récap — agrège les retours des tâches en amont."""
    from voc.activation.slack import notify

    ti = context["ti"]
    ticket_stats = ti.xcom_pull(task_ids="generate_tickets") or {}
    n_alerts = ti.xcom_pull(task_ids="generate_alerts") or 0
    if not isinstance(ticket_stats, dict):
        # Compat ancien retour int → cast minimal
        ticket_stats = {"csv": int(ticket_stats), "notion_created": 0}
    return notify(ticket_stats, n_alerts=int(n_alerts or 0))


with DAG(
    dag_id="voc_pipeline",
    description="Voice of Customer — collecte, raffinement, modélisation dbt, activation",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["voc", "abritel", "mvp"],
) as dag:
    extract = PythonOperator(
        task_id="extract",
        python_callable=_extract_callable,
    )

    refine_and_load = PythonOperator(
        task_id="refine_and_load",
        python_callable=_refine_load_callable,
    )

    llm_classify = PythonOperator(
        task_id="llm_classify",
        python_callable=_llm_classify_callable,
    )

    dbt_seed = BashOperator(
        task_id="dbt_seed",
        bash_command=f"cd {DBT_DIR} && dbt seed --profiles-dir {DBT_PROFILES_DIR} --full-refresh",
    )

    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=f"cd {DBT_DIR} && dbt run --profiles-dir {DBT_PROFILES_DIR}",
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"cd {DBT_DIR} && dbt test --profiles-dir {DBT_PROFILES_DIR}",
    )

    generate_alerts = PythonOperator(
        task_id="generate_alerts",
        python_callable=_alerts_callable,
    )

    generate_tickets = PythonOperator(
        task_id="generate_tickets",
        python_callable=_tickets_callable,
    )

    notify_slack = PythonOperator(
        task_id="notify_slack",
        python_callable=_slack_callable,
        trigger_rule="all_done",  # envoie même si une tâche amont a échoué
    )

    extract >> refine_and_load >> llm_classify >> dbt_seed >> dbt_run >> dbt_test
    dbt_test >> [generate_alerts, generate_tickets]
    [generate_alerts, generate_tickets] >> notify_slack
