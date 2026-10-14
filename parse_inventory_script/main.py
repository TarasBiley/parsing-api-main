import csv
import os
import random
from datetime import datetime

import openpyxl
import requests
import pandas as pd
from fastapi.logger import logger
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from common import error_handler_to_logger, GetOfferCommon
from models.offers import Offer
from html_parser import (GetOfferAvioSupport, GetOfferEcsat, GetOfferDasi, GetOfferProponent, GetOfferWencor,
                         GetOfferAviall, GetOfferBDSI, GetOfferAeroBay, GetOfferSatair)

class Scraping:
    classes = {
        'AeroBay': GetOfferAeroBay,
        'SatairMarket': GetOfferSatair,
        'AvioSupport': GetOfferAvioSupport,
        'e-csat': GetOfferEcsat,
        'DASI': GetOfferDasi,
        'Proponent': GetOfferProponent,
        'Wencor': GetOfferWencor,
        'Aviall': GetOfferAviall,
        'BDSI': GetOfferBDSI,
    }
    session_cl = [
        'AeroBay',
        'SatairMarket',
    ]
    selenium_cl = [
        'AvioSupport',
        'e-csat',
        'DASI',
        'Proponent',
        'Wencor',
        'Aviall',
        'BDSI',
    ]

    def __init__(self, driver: webdriver, part_numbers: list):
        self.driver = driver
        self.part_numbers = part_numbers

    def scraping(self, site) -> list[Offer]:
        """
        Основная функция по запуску поиска квот
        :return: Общий список квот
        """
        offers = []
        if site in self.session_cl:
            received_offers = self.site_session_scraping(self.classes[site], site)
            offers.extend(received_offers)
        elif site in self.selenium_cl:
            offers.extend(self.full_selenium_scraping(self.classes[site], site))
        return offers

    def full_selenium_scraping(self,
                               scraper_class: GetOfferCommon(),
                               name: str,
                               tries: int = 0,
                               old_selenium_offers=None) -> list[Offer]:
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
        received_offers = self.site_selenium_scraping(driver, scraper_class, name)
        selenium_offers.extend(received_offers)

        return selenium_offers

    def site_selenium_scraping(self, driver: webdriver, scraper_class: GetOfferCommon(), name: str) -> list[Offer]:
        """
        Поиск квот через selenium для определённого сайта
        :param driver: Драйвер для работы парсера
        :param scraper_class: Класс парсера
        :param name: Наименование сайта
        :return: Список квот
        """
        start_time = datetime.now()
        received_offers = scraper_class(self.part_numbers, driver).get_offers()

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
                received_offers = scraper_class(self.part_numbers, session).get_offers()
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
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.59',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/42.0.2311.135 Safari/537.36 Edge/12.246',
    ]
    random_user_agent = random.choice(user_agents)
    options.add_argument(f"--user-agent={random_user_agent}")
    return options


SITES = [
    'AvioSupport',
    'Proponent',
    'AeroBay',
    'DASI',
    'BDSI',
    'Aviall',
    'e-csat',
    'Wencor',
    'SatairMarket',
]

def parse_func(excel_file: str, sheet_name: str):
    if not os.path.exists('media/progress.csv'):
        if not os.path.isdir('media'):
            os.mkdir('media')
        with open('media/progress.csv', 'w', newline='') as csvfile:
            csvwriter = csv.writer(csvfile, delimiter=';', quotechar='|')
            csvwriter.writerow(['line', 'site'])
            for site in SITES:
                csvwriter.writerow(['0', site])
    if not os.path.exists('media/items.csv'):
        with open('media/items.csv', 'w', newline='') as csvfile:
            csvwriter = csv.writer(csvfile, delimiter=';', quotechar='|')
            csvwriter.writerow(['inventory'])
    if not os.path.exists('media/cookies.csv'):
        with open('media/cookies.csv', 'w', newline='') as csvfile:
            csvwriter = csv.writer(csvfile, delimiter=';', quotechar='|')
            csvwriter.writerow(['site', 'value1', 'value2', 'value3', 'value4'])
            for site in SITES:
                csvwriter.writerow([site, 'q', 'q', 'q', 'q'])

    progress = pd.read_csv('media/progress.csv', delimiter=';')

    service = Service('/home/leonid/work/erp-parser/chromedriver')

    site_10 = ['BDSI', 'Aviall', 'SatairMarket']
    site_1000 = ['AvioSupport', ]

    with (webdriver.Chrome(options=driver_options(), service=service) as driver):
        driver.implicitly_wait(3)
        for row in progress.itertuples():
            row_number = row.line
            df = pd.read_excel(excel_file, sheet_name, header=0, skiprows=row_number)
            types = [
                'CONSUMABLES',
                'Missing pn',
                'UNKNOWN',
            ]
            part_numbers = []
            rows = 0
            for line in df.values:
                rows += 1
                if line[4] in types:
                    part_numbers.append(line[0])

                if ((len(part_numbers) > 30 and row.site in site_10)
                    or (len(part_numbers) > 100 and row.site not in site_1000)
                    or len(part_numbers) > 1000):
                    offers = Scraping(driver, part_numbers).scraping(row.site)
                    new_lines = {}
                    for offer in offers:
                        for param, value in offer.model_dump().items():
                            if param in new_lines.keys():
                                new_lines[param].append(value)
                            else:
                                new_lines[param] = [value]

                    new_line = pd.DataFrame(new_lines)
                    df = pd.read_csv('media/items.csv', delimiter=';', low_memory=False)
                    d = pd.concat([df, new_line], ignore_index=True, )
                    d.to_csv('media/items.csv', sep=';', index=False, na_rep='')
                    progress.loc[progress['site'] == row.site, 'line'] += rows
                    progress.to_csv('media/progress.csv', index=False, sep=';')
                    rows = 0
                    part_numbers = []
            else:
                if part_numbers:
                    offers = Scraping(driver, part_numbers).scraping(row.site)
                    new_lines = {}
                    for offer in offers:
                        for param, value in offer.model_dump().items():
                            if param in new_lines.keys():
                                new_lines[param].append(value)
                            else:
                                new_lines[param] = [value]
                    new_line = pd.DataFrame(new_lines)
                    df = pd.read_csv('media/items.csv', delimiter=';', low_memory=False)
                    d = pd.concat([df, new_line], ignore_index=True, )
                    d.to_csv('media/items.csv', sep=';', index=False, na_rep='')
                    progress.loc[progress['site'] == row.site, 'line'] += rows
                    progress.to_csv('media/progress.csv', index=False, sep=';')
                    rows = 0
                    part_numbers = []


def csv_to_excel():
    """
    Перевод csv файла в xlsx
    :return:
    """
    dataframe = pd.read_csv('media/items.csv', delimiter=';', low_memory=False)

    filename = 'media/items.xlsx'

    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        dataframe.to_excel(writer, sheet_name='results', index=False, header=dataframe.columns)
        worksheet = writer.sheets['results']
        for idx, val in enumerate(dataframe.columns):
            col_letter = openpyxl.utils.get_column_letter(idx + 1)
            worksheet.column_dimensions[col_letter].width = max(len(val), 15)


if __name__ == '__main__':
    parse_func('Inventory_Report_May_2024.xlsx', 'Sheet1')
    csv_to_excel()
