import json
import re
from abc import abstractmethod
from venv import logger

import redis
from bs4 import BeautifulSoup
from requests import Response, Session

from core.config import settings

CONDITIONS = [
    'NE',
    'NS',
    'FN',
    'OH',
    'RP',
    'IN',
    'SV',
    'MD',
    'AR',
    'RB',
    'I/T',
    'TE',
]

FULL_CONDITION_NAME = {
    'new': 'NE',
    'newsurplus': 'NS',
    'factorynew': 'FN',
    'overhauled': 'OH',
    'repaired': 'RP',
    'visually inspected': 'IN',
    'inspected': 'IN',
    'serviceable': 'SV',
    'modified': 'MD',
    'asremoved': 'AR',
    'rebuilt': 'RB',
    'functiontested': 'TE',
    'tested': 'TE',
}

PRE_PACKING = (
    'EA',
    'PACK',
    'KIT',
    'BOX',
    'SHT',
    'ROLL',
    'CAN',
    'PAIR',
    'QUAR',
    'M2',
    'SQFT',
    'M',
    'CM',
    'MM',
    'FEET',
    'YARD',
    'GAL',
    'M3',
    'L',
    'ML',
    'TU',
    'KG',
    'GR',
    'LB',
    'OZ',
    'IN',
    'PT',
    'UOM',
)

USA_STATES = (
    'AL', '(AL)',
    'AK', '(AK)',
    'AZ', '(AZ)',
    'AR', '(AR)',
    'CA', '(CA)',
    'CO', '(CO)',
    'CT', '(CT)',
    'DE', '(DE)',
    'FL', '(FL)',
    'GA', '(GA)',
    'HI', '(HI)',
    'ID', '(ID)',
    'IL', '(IL)',
    'IN', '(IN)',
    'IA', '(IA)',
    'KS', '(KS)',
    'KY', '(KY)',
    'LA', '(LA)',
    'ME', '(ME)',
    'MD', '(MD)',
    'MA', '(MA)',
    'MI', '(MI)',
    'MN', '(MN)',
    'MS', '(MS)',
    'MO', '(MO)',
    'MT', '(MT)',
    'NE', '(NE)',
    'NV', '(NV)',
    'NH', '(NH)',
    'NJ', '(NJ)',
    'NM', '(NM)',
    'NY', '(NY)',
    'NC', '(NC)',
    'ND', '(ND)',
    'OH', '(OH)',
    'OK', '(OK)',
    'OR', '(OR)',
    'PA', '(PA)',
    'RI', '(RI)',
    'SC', '(SC)',
    'SD', '(SD)',
    'TN', '(TN)',
    'TX', '(TX)',
    'UT', '(UT)',
    'VT', '(VT)',
    'VA', '(VA)',
    'WA', '(WA)',
    'WV', '(WV)',
    'WI', '(WI)',
    'WY', '(WY)',
)

class GetOfferAbstract:
    @abstractmethod
    def get_offers(self):
        ...

    @abstractmethod
    def _get_html_page(self) -> BeautifulSoup:
        ...


class GetOfferCommon(GetOfferAbstract):
    response: Response = None
    site: str = ''

    def get_offers(self):
        """
        Основная функция получения квот
        """
        pass

    def _get_html_page(self) -> BeautifulSoup:
        return BeautifulSoup(self.response.text, 'html.parser')

    def _save_country(self, param: str, country: str, item: str = None) -> None:
        """
        Сохранение в redis стран, найденных парсером
        :param param: Название параметра для сохранения
        :param country: Полученное название страны (до обработки)
        :param item: Парт-номер, по которому была найдена страна
        """
        with redis.Redis(host=settings.REDIS_SETTINGS.HOST, port=settings.REDIS_SETTINGS.PORT) as redis_session:
            countries = redis_session.get('COUNTRIES_v2')
            if countries:
                countries = json.loads(countries)
                if param not in countries:
                    countries[param] = {}
            else:
                countries = {param: {}}

            if country not in countries[param].keys():
                countries[param][country] = item
                redis_session.set(
                    'COUNTRIES_v2',
                    json.dumps(countries)
                )

    @staticmethod
    def extract_number(price_str: str) -> float | int | None:
        """
        Поиск и извлечение цены в строке
        :param price_str: Цена на сайте
        :return: Преобразованная цена
        """
        clean_str = re.sub(r'[^\d.]', '', price_str)
        if clean_str:
            return float(clean_str)

    def _check_global_tries_to_login(self) -> bool:
        """
        Проверка количества ошибок при авторизации на сайте
        """
        with redis.Redis(host=settings.REDIS_SETTINGS.HOST, port=settings.REDIS_SETTINGS.PORT) as redis_session:
            site_loging_data = redis_session.get('SITE_STOP_LOGING')
        if site_loging_data:
            site_loging = json.loads(site_loging_data)
            return self.site not in site_loging or not site_loging[self.site]
        else:
            return True

    def login_availability(func):
        def check(self, *args, **kwargs):
            if not self._check_global_tries_to_login():
                logger.error('[%s] Check %s authorization credentials. '
                             'Reset site_loging_tries for %s in redis' % (self.site, self.site, self.site))
                return self.raw_offers
            else:
                return func(self, *args, **kwargs)
        return check


def error_handler_to_logger(e: Exception, site: str) -> None:
    """
    Запись ошибок в лог
    :param e: ошибка
    :param site: Сайт, который парсился во время возникновения ошибки
    :return: None
    """
    trace = []
    tb = e.__traceback__
    while tb is not None:
        trace.append({
            'filename': tb.tb_frame.f_code.co_filename,
            'name': tb.tb_frame.f_code.co_name,
            'lineno': tb.tb_lineno
        })
        tb = tb.tb_next
    logger.error(f'[{site}][Error] ' + str({
        'type': type(e).__name__,
        'message': str(e),
        'trace': trace
    }))
