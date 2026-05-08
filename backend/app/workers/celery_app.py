import uuid
from pathlib import Path

from celery import Celery

from app.config import settings

celery_app = Celery(
    "idss",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.workers.celery_app.run_genomics_pipeline": {"queue": "slow"},
        "app.workers.celery_app.run_ml_train": {"queue": "slow"},
        "app.workers.celery_app.run_phenotypic_ingest": {"queue": "fast"},
        "app.workers.celery_app.run_alert_score": {"queue": "fast"},
        "app.workers.celery_app.run_forecast": {"queue": "fast"},
        "app.workers.celery_app.run_ncbi_fetch": {"queue": "fast"},
    },
)


def _runner():
    from app.services.tool_runner import ToolRunner
    return ToolRunner()


def _jm():
    from app.services.job_manager import JobManager
    return JobManager


@celery_app.task(bind=True, name="app.workers.celery_app.run_genomics_pipeline")
def run_genomics_pipeline(self, job_id: str, pipeline_meta: dict, file_paths: list[str]):
    """
    Chains 6 genomics tools: fetch_local → qc → snp → amr → phylo → report → db_store.
    Updates job step progress in Redis at each stage.
    """
    from app.services.job_manager import JobManager
    from app.services.tool_runner import ToolRunner

    runner = ToolRunner()
    jm = JobManager
    job_dir = Path(settings.job_tmp_dir) / job_id

    jm.set_status(job_id, "running")

    # ── Step 1: Catalog uploaded files ──────────────────────────────────────
    jm.set_step(job_id, "fetch_local", "running")
    result_fetch = runner.run_tool(
        "fetch_local_sequences",
        {"directory": str(job_dir / "uploads"), "extensions": [".fasta", ".fa", ".fna", ".fastq", ".fq"]},
        job_dir,
    )
    if result_fetch.status == "error":
        jm.set_step(job_id, "fetch_local", "failed", result_fetch.stderr)
        jm.set_status(job_id, "failed", result_fetch.stderr)
        return
    jm.set_step(job_id, "fetch_local", "done")

    sequences_index = result_fetch.data

    # ── Step 2: QC ────────────────────────────────────────────────────────────
    jm.set_step(job_id, "qc", "running")
    result_qc = runner.run_tool(
        "qc_sequences",
        {"sequences_index": sequences_index, "output_file": ".tmp/qc_report.json"},
        job_dir,
    )
    if result_qc.status == "error":
        jm.set_step(job_id, "qc", "failed", result_qc.stderr)
        jm.set_status(job_id, "failed", result_qc.stderr)
        return
    jm.set_step(job_id, "qc", "done")

    # ── Step 3: SNP detection (requires reference) ───────────────────────────
    snp_result_data: dict = {}
    ref_accession = pipeline_meta.get("reference_accession")

    jm.set_step(job_id, "snp", "running")
    if ref_accession:
        # Fetch reference first
        ref_fetch = runner.run_tool(
            "fetch_ncbi_sequences",
            {
                "accessions": [ref_accession],
                "output_dir": ".tmp/reference",
                "ncbi_email": settings.ncbi_email,
                "ncbi_api_key": settings.ncbi_api_key,
            },
            job_dir,
        )
        if ref_fetch.status == "ok" and ref_fetch.data.get("files"):
            ref_file = ref_fetch.data["files"][0]["path"]
            snp_input = {
                "query_files": [f["path"] for f in sequences_index.get("files", [])],
                "reference_file": ref_file,
                "identity_threshold": pipeline_meta.get("identity_threshold", 0.80),
                "output_file": ".tmp/snp_results.json",
            }
            result_snp = runner.run_tool("snp_detection", snp_input, job_dir)
            if result_snp.status != "error":
                snp_result_data = result_snp.data
    jm.set_step(job_id, "snp", "done")

    # ── Step 4: AMR detection ─────────────────────────────────────────────────
    jm.set_step(job_id, "amr", "running")
    result_amr = runner.run_tool(
        "amr_detection",
        {
            "sequences_index": sequences_index,
            "identity_threshold": pipeline_meta.get("identity_threshold", 0.80),
            "ncbi_email": settings.ncbi_email,
            "ncbi_api_key": settings.ncbi_api_key,
            "db_cache_path": ".tmp/amr_db.fasta",
            "output_file": ".tmp/amr_results.json",
        },
        job_dir,
    )
    if result_amr.status == "error":
        jm.set_step(job_id, "amr", "failed", result_amr.stderr)
        jm.set_status(job_id, "failed", result_amr.stderr)
        return
    jm.set_step(job_id, "amr", "done")

    # ── Step 5: Phylogenetics (≥3 sequences required) ─────────────────────────
    phylo_result_data: dict = {}
    jm.set_step(job_id, "phylo", "running")
    file_list = sequences_index.get("files", [])
    if len(file_list) >= 3:
        result_phylo = runner.run_tool(
            "phylogenetics",
            {
                "sequences_index": sequences_index,
                "method": pipeline_meta.get("tree_method", "nj"),
                "kmer_size": pipeline_meta.get("kmer_size", 21),
                "output_dir": ".tmp/phylo",
            },
            job_dir,
        )
        if result_phylo.status == "ok":
            phylo_result_data = result_phylo.data
    jm.set_step(job_id, "phylo", "done")

    # ── Step 6: Generate Word report ─────────────────────────────────────────
    jm.set_step(job_id, "report", "running")
    runner.run_tool(
        "generate_genomics_report",
        {
            "qc_report_file": ".tmp/qc_report.json",
            "amr_results_file": ".tmp/amr_results.json",
            "snp_results_file": ".tmp/snp_results.json" if snp_result_data else None,
            "phylo_dir": ".tmp/phylo" if phylo_result_data else None,
            "output_file": ".tmp/genomics_report.docx",
            "study_name": pipeline_meta.get("study_name", ""),
            "researcher": pipeline_meta.get("researcher", ""),
        },
        job_dir,
    )
    jm.set_step(job_id, "report", "done")

    # ── Step 7: Store in database ─────────────────────────────────────────────
    jm.set_step(job_id, "db_store", "running")
    run_id = str(uuid.uuid4())
    result_store = runner.run_tool(
        "db_store_run",
        {
            "run_id": run_id,
            "researcher": pipeline_meta.get("researcher"),
            "study_name": pipeline_meta.get("study_name"),
            "pathogen": pipeline_meta.get("pathogen"),
            "source_type": pipeline_meta.get("source_type", "unknown"),
            "country": pipeline_meta.get("country"),
            "region": pipeline_meta.get("region"),
            "facility": pipeline_meta.get("facility"),
            "notes": pipeline_meta.get("notes"),
            "qc_report_file": ".tmp/qc_report.json",
            "amr_results_file": ".tmp/amr_results.json",
            "snp_results_file": ".tmp/snp_results.json" if snp_result_data else None,
            "phylo_dir": ".tmp/phylo" if phylo_result_data else None,
            "db_path": str(settings.db_path),
        },
        job_dir,
    )
    if result_store.status == "error":
        jm.set_step(job_id, "db_store", "failed", result_store.stderr)
        jm.set_status(job_id, "failed", result_store.stderr)
        return
    jm.set_step(job_id, "db_store", "done")

    jm.set_run_id(job_id, run_id)
    jm.set_result(job_id, {
        "run_id": run_id,
        "qc": result_qc.data,
        "amr": result_amr.data,
        "snp": snp_result_data,
        "phylo": phylo_result_data,
    })
    jm.set_status(job_id, "done")


@celery_app.task(bind=True, name="app.workers.celery_app.run_phenotypic_ingest")
def run_phenotypic_ingest(self, job_id: str, file_path: str, meta: dict):
    from app.services.job_manager import JobManager
    from app.services.tool_runner import ToolRunner

    runner = ToolRunner()
    jm = JobManager
    job_dir = Path(settings.job_tmp_dir) / job_id

    jm.set_status(job_id, "running")
    jm.set_step(job_id, "ingest", "running")

    result = runner.run_tool(
        "phenotypic_analysis",
        {
            "input_file": file_path,
            "output_file": ".tmp/phenotypic_results.json",
            "db_path": str(settings.db_path),
            **meta,
        },
        job_dir,
    )

    if result.status == "error":
        jm.set_step(job_id, "ingest", "failed", result.stderr)
        jm.set_status(job_id, "failed", result.stderr)
        return

    jm.set_step(job_id, "ingest", "done")
    jm.set_result(job_id, result.data)
    jm.set_status(job_id, "done")


@celery_app.task(bind=True, name="app.workers.celery_app.run_alert_score")
def run_alert_score(self, job_id: str, run_id: str):
    from app.services.job_manager import JobManager
    from app.services.tool_runner import ToolRunner

    runner = ToolRunner()
    jm = JobManager
    job_dir = Path(settings.job_tmp_dir) / job_id

    jm.set_status(job_id, "running")
    jm.set_step(job_id, "alert_score", "running")

    result = runner.run_tool(
        "alert_score",
        {"run_id": run_id, "db_path": str(settings.db_path), "output_file": ".tmp/alert_result.json"},
        job_dir,
    )

    if result.status == "error":
        jm.set_step(job_id, "alert_score", "failed", result.stderr)
        jm.set_status(job_id, "failed", result.stderr)
        return

    jm.set_step(job_id, "alert_score", "done")
    jm.set_result(job_id, result.data)
    jm.set_status(job_id, "done")


@celery_app.task(bind=True, name="app.workers.celery_app.run_ml_train")
def run_ml_train(self, job_id: str, train_params: dict):
    from app.services.job_manager import JobManager
    from app.services.tool_runner import ToolRunner

    runner = ToolRunner()
    jm = JobManager
    job_dir = Path(settings.job_tmp_dir) / job_id

    jm.set_status(job_id, "running")
    jm.set_step(job_id, "ml_train", "running")

    result = runner.run_tool(
        "ml_train",
        {**train_params, "db_path": str(settings.db_path), "output_dir": ".tmp/models"},
        job_dir,
        timeout=7200,
    )

    if result.status == "error":
        jm.set_step(job_id, "ml_train", "failed", result.stderr)
        jm.set_status(job_id, "failed", result.stderr)
        return

    jm.set_step(job_id, "ml_train", "done")
    jm.set_result(job_id, result.data)
    jm.set_status(job_id, "done")


@celery_app.task(bind=True, name="app.workers.celery_app.run_ncbi_fetch")
def run_ncbi_fetch(self, job_id: str, fetch_params: dict):
    from app.services.job_manager import JobManager
    from app.services.tool_runner import ToolRunner

    runner = ToolRunner()
    jm = JobManager
    job_dir = Path(settings.job_tmp_dir) / job_id

    jm.set_status(job_id, "running")
    jm.set_step(job_id, "ncbi_fetch", "running")

    result = runner.run_tool(
        "fetch_ncbi_sequences",
        {
            **fetch_params,
            "ncbi_email": settings.ncbi_email,
            "ncbi_api_key": settings.ncbi_api_key,
            "output_dir": ".tmp/ncbi_sequences",
        },
        job_dir,
        timeout=600,
    )

    if result.status == "error":
        jm.set_step(job_id, "ncbi_fetch", "failed", result.stderr)
        jm.set_status(job_id, "failed", result.stderr)
        return

    jm.set_step(job_id, "ncbi_fetch", "done")
    jm.set_result(job_id, result.data)
    jm.set_status(job_id, "done")


@celery_app.task(bind=True, name="app.workers.celery_app.run_forecast")
def run_forecast(self, job_id: str, forecast_params: dict):
    from app.services.job_manager import JobManager
    from app.services.tool_runner import ToolRunner

    runner = ToolRunner()
    jm = JobManager
    job_dir = Path(settings.job_tmp_dir) / job_id

    jm.set_status(job_id, "running")
    jm.set_step(job_id, "forecast", "running")

    result = runner.run_tool(
        "forecast_trends",
        {**forecast_params, "db_path": str(settings.db_path), "output_file": ".tmp/forecast_result.json"},
        job_dir,
    )

    if result.status in ("error", "insufficient_data"):
        jm.set_step(job_id, "forecast", "failed", result.stderr)
        jm.set_status(job_id, "failed", result.stderr)
        return

    jm.set_step(job_id, "forecast", "done")
    jm.set_result(job_id, result.data)
    jm.set_status(job_id, "done")
