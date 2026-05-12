from app.settings.celery_app import celery
from app.apiClients.clientX import XClient
from db.service import save_rank_result, save_flag_result, save_profile_result
import logging

log = logging.getLogger(__name__)


@celery.task(bind=True, autoretry_for=(Exception,),
             retry_backoff=True, retry_jitter=True, retry_kwargs={"max_retries": 3})
def rank_task(self, prompt: str, character_list: list[str], universe_name: str,
              universe_id: int, parameter: str,
              arc: str | None = None, context: str | None = None) -> dict:
    client = XClient()
    result = client.rank(prompt, character_list, universe_name, arc, context)
    save_rank_result(result, universe_id, parameter)
    log.info("rank %s saved for universe %s", parameter, universe_id)
    return result


@celery.task(bind=True, autoretry_for=(Exception,),
             retry_backoff=True, retry_jitter=True, retry_kwargs={"max_retries": 3})
def flag_task(self, flag_name: str, character_list: list[str], universe_name: str,
              universe_id: int,
              arc: str | None = None, context: str | None = None) -> dict:
    client = XClient()
    result = client.flag(flag_name, character_list, universe_name, arc, context)
    save_flag_result(result, universe_id, flag_name)
    log.info("flag %s saved for universe %s", flag_name, universe_id)
    return result


@celery.task(bind=True, autoretry_for=(Exception,),
             retry_backoff=True, retry_jitter=True, retry_kwargs={"max_retries": 3})
def profile_task(self, character_list: list[str], universe_name: str,
                 universe_id: int,
                 arc: str | None = None, context: str | None = None) -> dict:
    client = XClient()
    result = client.profile(character_list, universe_name, arc, context)
    save_profile_result(result, universe_id)
    log.info("profile saved for universe %s", universe_id)
    return result
