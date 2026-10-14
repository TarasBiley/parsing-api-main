import json
from http.client import RemoteDisconnected
from time import sleep

import redis
import telebot
from telebot import types
from telebot.types import InlineKeyboardMarkup

from core.config import settings

bot = telebot.TeleBot(settings.TELEGRAM_TOKEN)


class LoginException(Exception):
    """
    Exception raised when login on site fails.
    """
    def __init__(self, site: str) -> None:
        self.site = site
        self.redis_update()

    def __str__(self):
        return '[%s] Login failed on site %s' % (self.site, self.site)

    def redis_update(self) -> None:
        with redis.Redis(host=settings.REDIS_SETTINGS.HOST, port=settings.REDIS_SETTINGS.PORT) as redis_session:
            data = redis_session.get('SITE_LOGING_TRIES')

            if data:
                site_loging_tries = json.loads(data)
                if self.site in site_loging_tries:
                    site_loging_tries[self.site] += 1
                    if site_loging_tries[self.site] <= 5:
                        self.telegram_msg(f'Ошибка авторизации №{site_loging_tries[self.site]}')
                    else:
                        login_status_data = redis_session.get('SITE_STOP_LOGING')
                        if login_status_data:
                            login_status = json.loads(login_status_data)
                            login_status[self.site] = True

                        else:
                            login_status = {self.site: True}
                        redis_session.set(
                            'SITE_STOP_LOGING',
                            json.dumps(login_status)
                        )
                        self.telegram_msg(
                            f'Превышено максимальное количество попыток авторизации.\n'
                            f'Для возобновления необходимо сбросить счётчик\n' + settings.TAGGED_TELEGRAM_ACCS
                        )
                else:
                    site_loging_tries[self.site] = 1
            else:
                site_loging_tries = {self.site: 1}
                self.telegram_msg(f'Ошибка авторизации №{site_loging_tries[self.site]}')
            redis_session.set(
                'SITE_LOGING_TRIES',
                json.dumps(site_loging_tries),
                ex=3600
            )

    def telegram_msg(self, msg: str, tries: int = 0) -> None:
        try:
            bot.send_message(
                settings.CHAT_ID,
                self.site + ' ' + msg
            )
        except RemoteDisconnected as e:
            if tries < 5:
                sleep(1)
                self.telegram_msg(msg, tries + 1)
            else:
                raise e

