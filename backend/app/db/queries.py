"""
Read-only query functions mirroring db_query.py logic.
All functions return list[dict] or dict for easy Pydantic serialization.
"""
from typing import Any, Optional

from app.db.connection import db_cursor


def list_runs(page: int = 1, page_size: int = 20, pathogen: Optional[str] = None, region: Optional[str] = None) -> dict[str, Any]:
    offset = (page - 1) * page_size
    filters, params = [], []

    if pathogen:
        filters.append("pr.pathogen = ?")
        params.append(pathogen)
    if region:
        filters.append("pr.region = ?")
        params.append(region)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    with db_cursor() as cur:
        count_row = cur.execute(f"SELECT COUNT(*) FROM pipeline_runs pr {where}", params).fetchone()
        total = count_row[0] if count_row else 0

        rows = cur.execute(
            f"""
            SELECT pr.run_id, pr.researcher, pr.study_name, pr.pathogen,
                   pr.region, pr.source_type, pr.created_at,
                   COUNT(DISTINCT s.sample_id) AS sample_count,
                   ar.alert_level, ar.alert_score
            FROM pipeline_runs pr
            LEFT JOIN samples s ON s.run_id = pr.run_id
            LEFT JOIN alert_records ar ON ar.run_id = pr.run_id
            {where}
            GROUP BY pr.run_id
            ORDER BY pr.created_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()

    items = [dict(r) for r in rows]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, -(-total // page_size)),
    }


def get_run_detail(run_id: str) -> Optional[dict[str, Any]]:
    with db_cursor() as cur:
        run = cur.execute("SELECT * FROM pipeline_runs WHERE run_id = ?", (run_id,)).fetchone()
        if not run:
            return None

        samples = cur.execute("SELECT * FROM samples WHERE run_id = ?", (run_id,)).fetchall()
        qc = cur.execute(
            "SELECT q.* FROM qc_results q JOIN samples s ON s.sample_id = q.sample_id WHERE s.run_id = ?",
            (run_id,),
        ).fetchall()
        amr_hits = cur.execute(
            """
            SELECT ah.*, s.sample_id as sid
            FROM amr_hits ah
            JOIN amr_results ar ON ar.result_id = ah.result_id
            JOIN samples s ON s.sample_id = ar.sample_id
            WHERE s.run_id = ?
            """,
            (run_id,),
        ).fetchall()
        alert = cur.execute("SELECT * FROM alert_records WHERE run_id = ?", (run_id,)).fetchone()

    return {
        **dict(run),
        "samples": [dict(s) for s in samples],
        "qc_results": [dict(q) for q in qc],
        "amr_hits": [dict(h) for h in amr_hits],
        "alert": dict(alert) if alert else None,
    }


def get_amr_trend(gene: Optional[str] = None, region: Optional[str] = None, days: int = 365) -> list[dict]:
    filters = ["pr.created_at >= date('now', ? || ' days')"]
    params: list[Any] = [f"-{days}"]

    if gene:
        filters.append("ah.gene = ?")
        params.append(gene)
    if region:
        filters.append("pr.region = ?")
        params.append(region)

    where = "WHERE " + " AND ".join(filters)

    with db_cursor() as cur:
        rows = cur.execute(
            f"""
            SELECT date(pr.created_at) AS date, ah.gene, pr.region, COUNT(*) AS count
            FROM amr_hits ah
            JOIN amr_results ar ON ar.result_id = ah.result_id
            JOIN samples s ON s.sample_id = ar.sample_id
            JOIN pipeline_runs pr ON pr.run_id = s.run_id
            {where}
            GROUP BY date(pr.created_at), ah.gene, pr.region
            ORDER BY date ASC
            """,
            params,
        ).fetchall()

    return [dict(r) for r in rows]


def get_resistance_rates(antibiotic: Optional[str] = None, region: Optional[str] = None, pathogen: Optional[str] = None) -> list[dict]:
    filters: list[str] = []
    params: list[Any] = []

    if antibiotic:
        filters.append("ast.antibiotic = ?")
        params.append(antibiotic)
    if region:
        filters.append("ps.region = ?")
        params.append(region)
    if pathogen:
        filters.append("ps.pathogen_name = ?")
        params.append(pathogen)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    with db_cursor() as cur:
        rows = cur.execute(
            f"""
            SELECT ast.antibiotic,
                   COALESCE(ps.region, 'Unknown') AS region,
                   ROUND(100.0 * SUM(CASE WHEN ast.interpretation = 'R' THEN 1 ELSE 0 END) / COUNT(*), 1) AS resistance_pct,
                   COUNT(*) AS total_samples
            FROM ast_records ast
            JOIN phenotypic_samples ps ON ps.sample_id = ast.sample_id
            {where}
            GROUP BY ast.antibiotic, ps.region
            HAVING total_samples >= 5
            ORDER BY resistance_pct DESC
            """,
            params,
        ).fetchall()

    return [dict(r) for r in rows]


def get_outbreak_signals(days: int = 90, min_samples: int = 3) -> list[dict]:
    with db_cursor() as cur:
        rows = cur.execute(
            """
            SELECT ah.gene, pr.region, pr.pathogen,
                   COUNT(DISTINCT s.sample_id) AS sample_count,
                   MIN(date(pr.created_at)) AS first_seen,
                   MAX(date(pr.created_at)) AS last_seen
            FROM amr_hits ah
            JOIN amr_results ar ON ar.result_id = ah.result_id
            JOIN samples s ON s.sample_id = ar.sample_id
            JOIN pipeline_runs pr ON pr.run_id = s.run_id
            WHERE pr.created_at >= date('now', ? || ' days')
            GROUP BY ah.gene, pr.region, pr.pathogen
            HAVING sample_count >= ?
            ORDER BY sample_count DESC
            """,
            (f"-{days}", min_samples),
        ).fetchall()

    return [dict(r) for r in rows]


def get_mdr_trend(region: Optional[str] = None, pathogen: Optional[str] = None, days: int = 365) -> list[dict]:
    filters = ["ps.collection_date >= date('now', ? || ' days')"]
    params: list[Any] = [f"-{days}"]

    if region:
        filters.append("ps.region = ?")
        params.append(region)
    if pathogen:
        filters.append("ps.pathogen_name = ?")
        params.append(pathogen)

    where = "WHERE " + " AND ".join(filters)

    with db_cursor() as cur:
        rows = cur.execute(
            f"""
            SELECT date(ps.collection_date) AS date,
                   mc.mdr_class,
                   COUNT(*) AS count
            FROM mdr_classifications mc
            JOIN phenotypic_samples ps ON ps.sample_id = mc.sample_id
            {where}
            GROUP BY date(ps.collection_date), mc.mdr_class
            ORDER BY date ASC
            """,
            params,
        ).fetchall()

    return [dict(r) for r in rows]


def list_alerts(
    level: Optional[str] = None,
    region: Optional[str] = None,
    days: int = 90,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    offset = (page - 1) * page_size
    filters = ["ar.created_at >= date('now', ? || ' days')"]
    params: list[Any] = [f"-{days}"]

    if level:
        filters.append("ar.alert_level = ?")
        params.append(level)
    if region:
        filters.append("pr.region = ?")
        params.append(region)

    where = "WHERE " + " AND ".join(filters)

    with db_cursor() as cur:
        total = cur.execute(
            f"""
            SELECT COUNT(*) FROM alert_records ar
            JOIN pipeline_runs pr ON pr.run_id = ar.run_id
            {where}
            """,
            params,
        ).fetchone()[0]

        rows = cur.execute(
            f"""
            SELECT ar.*, pr.pathogen, pr.region, pr.researcher
            FROM alert_records ar
            JOIN pipeline_runs pr ON pr.run_id = ar.run_id
            {where}
            ORDER BY ar.created_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()

    return {
        "items": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, -(-total // page_size)),
    }


def list_ml_models() -> list[dict]:
    with db_cursor() as cur:
        rows = cur.execute(
            "SELECT * FROM ml_models ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]
