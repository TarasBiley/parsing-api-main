import random
from datetime import datetime
from time import sleep

import requests
from billiard.exceptions import SoftTimeLimitExceeded
from fastapi.logger import logger
from selenium import webdriver
from selenium.common import SessionNotCreatedException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from models.offers import Offer
from parsers.common import GetOfferCommon, error_handler_to_logger
from parsers.html_parser import GetOfferAeroBay, GetOfferAvioSupport, GetOfferEcsat, GetOfferDasi, GetOfferProponent, \
    GetOfferSatair, GetOfferWencor, GetOfferAviall, GetOfferBDSI

class Scraping:
    selenium_classes  = [
        {'class': GetOfferAvioSupport, 'name': 'AvioSupport'},
        {'class': GetOfferEcsat, 'name': 'e-csat'},
        {'class': GetOfferDasi, 'name': 'DASI'},
        {'class': GetOfferProponent, 'name': 'Proponent'},
        {'class': GetOfferWencor, 'name': 'Wencor'},
        {'class': GetOfferAviall, 'name': 'Aviall'},
        {'class': GetOfferBDSI, 'name': 'BDSI'},
    ]
    session_classes = [
        {'class': GetOfferAeroBay, 'name': 'AeroBay'},
        {'class': GetOfferSatair, 'name': 'SatairMarket'},
    ]

    def __init__(self, part_numbers: list, context: dict):
        self.part_numbers = part_numbers
        self.context = context

    def scraping(self) -> list[Offer]:
        """
        Основная функция по запуску поиска квот
        :return: Общий список квот
        """
        offers = []

        for session_class in self.session_classes:
            received_offers = self.site_session_scraping(session_class['class'], session_class['name'])
            offers.extend(received_offers)
        if self.selenium_classes:
            offers.extend(self.full_selenium_scraping())
        return offers

    def full_selenium_scraping(self, tries: int = 0, old_selenium_offers=None) -> list[Offer]:
        """
        Запуск поиска квот через selenium для разных сайтов
        :param tries: Количество попыток старта вебдрайвера
        :param old_selenium_offers: Список квот с предыдущей попытки
        :return: Список квот
        """
        if old_selenium_offers is None:
            old_selenium_offers = []
        if tries >= 5:
            return old_selenium_offers
        selenium_offers = []
        try:
            with webdriver.Chrome(options=self.driver_options()) as driver:
                driver.implicitly_wait(3)

                for selenium_class in self.selenium_classes:
                    received_offers = self.site_selenium_scraping(driver, selenium_class['class'], selenium_class['name'])
                    selenium_offers.extend(received_offers)

                try:
                    driver.close()
                except Exception as e:
                    error_handler_to_logger(e, 'DRIVER_CLOSE')
            return selenium_offers
        except SessionNotCreatedException as e:
            if tries >= 4:
                logger.error(f'SessionNotCreatedException: tries {tries}')
                raise e
            sleep(1)
            return self.full_selenium_scraping(tries=tries + 1, old_selenium_offers=selenium_offers)
        except WebDriverException as e:
            if tries >= 4:
                logger.error(f'WebDriverException: tries {tries}')
                raise e
            sleep(1)
            return self.full_selenium_scraping(tries=tries + 1, old_selenium_offers=selenium_offers)

    def site_selenium_scraping(self, driver: webdriver, scraper_class: GetOfferCommon(), name: str) -> list[Offer]:
        """
        Поиск квот через selenium для определённого сайта
        :param driver: Драйвер для работы парсера
        :param scraper_class: Класс парсера
        :param name: Наименование сайта
        :return: Список квот
        """
        start_time = datetime.now()
        try:
            received_offers = scraper_class(self.part_numbers, driver, self.context).get_offers()
        except SoftTimeLimitExceeded as e:
            raise e
        except Exception as e:
            error_handler_to_logger(e, name)
            received_offers = []

        self.time_logger(name, start_time, len(received_offers))

        return received_offers

    def site_session_scraping(self, scraper_class: GetOfferCommon(), name: str) -> list[Offer]:
        """
        Поиск квот через requests
        :param scraper_class: Класс парсера
        :param name: Наименование сайта
        :return: Список квот
        """
        start_time = datetime.now()
        with requests.Session() as session:
            try:
                received_offers = scraper_class(self.part_numbers, session, self.context).get_offers()
            except Exception as e:
                error_handler_to_logger(e, name)
                received_offers = []
            self.time_logger(name, start_time, len(received_offers))
        return received_offers

    @staticmethod
    def time_logger(site: str, start_time: datetime, count_offers: int) -> None:
        """
        Логирования времени, затраченного на парсинг
        :param site: Сайт, который парсился
        :param start_time: Время начала парсинга
        :param count_offers: Количество найденных квот на сайте
        :return: None
        """
        logger.info(
            '[%s] Time to parse: %s, get %s offers' % (site, datetime.now() - start_time, count_offers)
        )

    @staticmethod
    def driver_options() -> Options:
        """
        Настройки драйвера
        """
        options = Options()
        options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--no-zygote')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-popup-blocking')
        options.add_argument('--blink-settings=imagesEnabled=false')
        options.add_argument('--window-size=1600,1080')
        user_agents = [
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.106 Safari/537.36 OPR/38.0.2220.41',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.59',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/42.0.2311.135 Safari/537.36 Edge/12.246',
        ]
        random_user_agent = random.choice(user_agents)
        options.add_argument(f"--user-agent={random_user_agent}")
        return options
