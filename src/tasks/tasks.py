import json
from datetime import datetime
from time import sleep

import requests
import telebot
from billiard.exceptions import SoftTimeLimitExceeded
from fastapi.logger import logger

from celery_config import celery_app
from core.config import settings
from models.offers import Offer
from parsers.common import GetOfferCommon
from parsers.exceptions import LoginException
from parsers.scraping_process import Scraping

bot = telebot.TeleBot(settings.TELEGRAM_TOKEN)


@celery_app.task(soft_time_limit=1800)
def get_offers_task(part_numbers: list, context: dict, host: str):
    logger.info(f'Get part_numbers={part_numbers}')
    offers = []
    try:
        offers = Scraping(part_numbers, context).scraping()
        send_offers_to_aviator(offers)

    except SoftTimeLimitExceeded:
        msg = f'Time limit exceeded. part_numbers = {part_numbers}'
        logger.error(msg)
        bot.send_message(
            settings.CHAT_ID,
            msg
        )
        if offers:
            send_offers_to_aviator(offers)


def send_offers_to_aviator(offers: list[Offer]):
    start_time = datetime.now()

    try_to_auth = GetOfferCommon()
    try_to_auth.site = 'Aviator'
    if not try_to_auth._check_global_tries_to_login():
        logger.info('[Aviator][ERROR] Time to send info: %s' % (datetime.now() - start_time))
        return

    with requests.Session() as session:
        url = settings.MAIN_SERVER

        try_to_auth = False
        for offer in offers:
            response = upload_offer(session, url, offer)
            if response.status_code == 401 and not try_to_auth:
                try_to_auth = True
                if auth_aviator(session, url) == 200:
                    response = upload_offer(session, url, offer)
                else:
                    raise LoginException('Aviator')
            if response.status_code != 201:
                logger.error(f'[ERROR] Error to save offer: status_code = {response.status_code}\n'
                             f'offer: {offer.model_dump()}')

    logger.info('[Aviator] Time to send info: %s' % (datetime.now() - start_time))


def upload_offer(session: requests.Session(), url: str, offer: Offer, retry: int = 0):
    if retry >= 7:
        raise ConnectionError

    try:
        response = session.post(
            f'{url}/api/manager/offer/',
            data=offer.model_dump_json(),
            headers={
                'content-type': 'application/json',
                'authorization': f'JWT {settings.AVIATOR_SETTINGS.AUTHORISATION_TOKEN}'
            }
        )
    except ConnectionError:
        sleep(2 ^ retry)
        return upload_offer(session, url, offer, retry + 1)

    return response


def auth_aviator(session: requests.Session(), url: str):
    auth_response = session.post(
        f'{url}/api/token/',
        data=json.dumps({
            'username': settings.AVIATOR_SETTINGS.USER_NAME,
            'password': settings.AVIATOR_SETTINGS.PASSWORD,
            'code': settings.AVIATOR_SETTINGS.CODE,
        }),
        headers={
            'content-type': 'application/json',
        }
    )
    if auth_response.status_code == 200:
        settings.AVIATOR_SETTINGS.AUTHORISATION_TOKEN = auth_response.json()['access']
    return auth_response.status_code
