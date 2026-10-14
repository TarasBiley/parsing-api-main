import json
from functools import lru_cache

from fastapi import Depends
from redis.asyncio import Redis

from db.redis import get_redis
from models.offers import Offer
from parsers.html_parser import GetOfferAeroBay


class OfferService:
    """
    Сервис для получения данных с сайтов
    """
    async def get_data(self, items: list[str]) -> list[Offer]:
        offers = list()
        for item in items:
            offers += GetOfferAeroBay(item).get_offers()
        return offers


class DASICookiesService:
    """
    Сохранения куки для dasi
    """
    def __init__(self, redis: Redis):
        self._redis = redis

    async def set_data(self, cookies: dict[str: str]) -> tuple[str, int]:
        try:
            await self._redis.set(name='DASI_COOKIES', value=json.dumps(cookies))
            return 'Cookies updated', 201
        except Exception as e:
            return str(e), 400


class ResetLoginTriesService:
    """
    Сброс неудачных попыток авторизации на сайтах
    """
    def __init__(self, redis: Redis):
        self._redis = redis

    async def reset_data(self, sites: dict[str: list[str]]) -> tuple[str, int]:

        raw_data_tries = await self._redis.get(name='SITE_LOGING_TRIES')
        raw_data_stop = await self._redis.get(name='SITE_STOP_LOGING')
        if raw_data_tries:
            loging_tries = json.loads(raw_data_tries)
        else:
            loging_tries = {}
        if raw_data_stop:
            stop_loging = json.loads(raw_data_stop)
        else:
            stop_loging = {}

        not_find = []
        updated = []
        for site in sites['sites']:

            if site in loging_tries:
                loging_tries[site] = 0
                tries_updated = True
            else:
                tries_updated = False

            if site in stop_loging:
                stop_loging[site] = False
                stop_loging_updated = True
            else:
                stop_loging_updated = False

            if tries_updated or stop_loging_updated:
                updated.append(site)
            else:
                not_find.append(site)

        try:
            await self._redis.set(name='SITE_LOGING_TRIES', value=json.dumps(loging_tries))
            await self._redis.set(name='SITE_STOP_LOGING', value=json.dumps(stop_loging))
        except Exception as e:
            return str(e), 400

        if not_find and updated:
            return str({'updated': updated, 'not_find': not_find}), 200
        elif not_find and not updated:
            return str({'updated': updated, 'not_find': not_find}), 404
        elif not not_find and updated:
            return str({'updated': updated, 'not_find': not_find}), 200
        else:
            return '', 404


@lru_cache()
def get_order_service(
) -> OfferService:
    return OfferService()


@lru_cache()
def set_dasi_cookies(
    redis: Redis = Depends(get_redis)
) -> DASICookiesService:
    return DASICookiesService(redis)


@lru_cache()
def reset_login_tries_service(
    redis: Redis = Depends(get_redis)
) -> ResetLoginTriesService:
    return ResetLoginTriesService(redis)
