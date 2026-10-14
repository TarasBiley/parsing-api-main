import json
import re
from datetime import datetime
from time import sleep
from venv import logger

import pandas as pd
from billiard.exceptions import SoftTimeLimitExceeded
from bs4 import ResultSet, Tag, BeautifulSoup
from requests import Response, Session
from selenium import webdriver
from selenium.common import NoSuchElementException, StaleElementReferenceException, exceptions, \
    ElementNotInteractableException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec

from core.config import settings
from models.offers import Offer
from common import GetOfferCommon, CONDITIONS, PRE_PACKING, USA_STATES, FULL_CONDITION_NAME, \
    error_handler_to_logger


class GetOfferAeroBay(GetOfferCommon):
    """
    Получение квот с AeroBay
    """
    raw_offers = list()
    page_size = 100
    leadtime_limit = bool()
    page_limit = 10

    def __init__(self, part_numbers: list, session: Session):
        self.part_numbers = part_numbers
        self.html_page = None
        self.session = session

    def get_offers(self) -> list[Offer]:
        """
        Основная функция для получения квот
        :return: Список квот
        """
        self.raw_offers = []
        for part_number in self.part_numbers:
            offers = []
            self.leadtime_limit = False
            rows = self.page_size
            page = 1
            try_to_log_in = False
            tries = 0
            while rows % self.page_size == 0 and tries < self.page_limit:  # Если на странице есть записи или лимит попыток не исчерпан
                self.response = self._get_response(self.session, page, part_number)
                if self.response.status_code != 200:
                    break

                self.html_page = self._get_html_page()

                html_offers = self.html_page.find_all('div', {'class': 'parent_product_box_list'})

                if html_offers and not try_to_log_in:
                    is_auth = self._check_authorization(html_offers)
                    if not is_auth:
                        self._log_in(self.session)
                        continue
                    try_to_log_in = True

                for html_offer in html_offers:
                    try:
                        item = self._get_item(html_offer)
                        if '...' in item:  # Обработка длинных part_number
                            item = item.replace('...', '')
                            if item.replace('-', '') not in part_number.replace('-', ''):  # Исключение аналогов, предлагаемых AeroBay
                                continue
                        else:
                            if part_number.replace('-', '') != item.replace('-', ''):  # Исключение аналогов, предлагаемых AeroBay
                                continue
                        raw_offer = self._get_raw_offer(html_offer, part_number)
                        if raw_offer:
                            offers.append(raw_offer)
                    except ValueError as e:
                        error_handler_to_logger(e, 'AeroBay')

                page += 1
                rows = len(offers)
                tries += 1

            if self.leadtime_limit:
                new_raw_offers_with_leadtime = []
                for raw_offer in offers:
                    if raw_offer.int_leadtime_start != 999 or raw_offer.int_leadtime_end != 999:
                        new_raw_offers_with_leadtime.append(raw_offer)
                self.raw_offers.extend(new_raw_offers_with_leadtime)
            else:
                self.raw_offers.extend(offers)
        return self.raw_offers

    @staticmethod
    def _check_authorization(html_offers: ResultSet) -> bool:
        """
        Проверка авторизации на AeroBay
        :param html_offers: Полученная страница с AeroBay
        :return: Авторизован ли пользователь
        """
        try:
            return not bool(html_offers[0].find_all(
                'div',
                {
                    'class': 'div_log_in margin_auto_0',
                }
            )[0].find_all(
                'a'
            )[0].string)
        except IndexError:
            return True

    def _log_in(self, session: Session):
        """
        Авторизация на AeroBay. Сохраняет токен в настройках в параметре AEROBAY_SETTINGS.JSESSIONID
        :return: None
        """
        csrf = self.html_page.find_all(
            'input',
            {
                'type': 'hidden',
                'name': '_csrf'
            }
        )[0].attrs['value']
        session.post(
            'https://www.aero-bay.com/j_spring_security_check',
            data={
                'userName': settings.AEROBAY_SETTINGS.USER_NAME,
                'password': settings.AEROBAY_SETTINGS.PASSWORD,
                '_csrf': csrf
            },
            cookies={
                'JSESSIONID': session.cookies.get('JSESSIONID'),
            },
            headers={
                'content-type': 'application/x-www-form-urlencoded',
            }

        )
        jsession_id = session.cookies.get('JSESSIONID')
        settings.AEROBAY_SETTINGS.JSESSIONID = jsession_id

    def _get_response(self, session: Session, page: int, part_number: str) -> Response:
        """
        Отправка запроса на получение страницы с офферами
        :param page: Номер запрашиваемой страницы
        :return: Запрашиваемая страница
        """
        cookies = {
            'JSESSIONID': settings.AEROBAY_SETTINGS.JSESSIONID
        } if settings.AEROBAY_SETTINGS.JSESSIONID else None
        return session.get(
            'https://www.aero-bay.com/q',
            params={
                'searchType': 'PART_NUMBER',
                'item': part_number,
                'page': page,
                'itemsPerPage': self.page_size,
            },
            cookies=cookies
        )

    def _get_raw_offer(self, html_offer: Tag, part_number: str) -> Offer | None:
        """
        Получение данных с html страницы
        :param html_offer: позиция в html
        :return: Квота
        """
        offer_description = self._get_offer_description(html_offer)
        condition = self._get_condition(html_offer, part_number)
        quantity = self._get_quantity(html_offer, part_number)
        offer_country = self._get_offer_country(html_offer, part_number)
        price, price_unit = self._get_price(html_offer)
        if not price:
            return None

        int_leadtime_start, int_leadtime_end = self._get_lead_time(html_offer, part_number)

        update_on = self._get_update_on(html_offer)
        comment = self._get_comment(html_offer)
        raw_offer = Offer(
            inventory=part_number,
            offer_description=offer_description,
            condition=condition,
            quantity=quantity,
            offer_country=offer_country,
            price=price,
            price_unit=price_unit,
            int_leadtime_start=int_leadtime_start,
            int_leadtime_end=int_leadtime_end,
            company='AEROBAY',
            commit_date_unix=update_on,
            aviator_purchase='LM',
            to_buy=True,
            sale_type='SALE',
            comment=comment
        )

        return raw_offer

    def _get_item(self, html_offer: Tag) -> str:
        """
        Получение part_number записи на странице
        :param html_offer: позиция в html
        :return: part_number
        """
        return html_offer.find_all(
            'h5',
            {
                'class': 'uppercase black-text title_product_list_result',
            }
        )[0].find_all(
            'strong'
        )[0].string

    @staticmethod
    def _get_offer_description(html_offer: Tag) -> str:
        """
        Получение описания позиции
        :param html_offer: позиция в html
        :return: Описание позиции
        """
        return html_offer.find_all(
            'p',
            {
                'class': 'lit-bold black-text under_title_product_list_result display_all_text_infos',
            }
        )[0].string

    @staticmethod
    def _get_condition(html_offer: Tag, part_number: str) -> str:
        """
        Получение состояния в позиции
        :param html_offer: позиция в html
        :return: Состояние
        """
        condition = html_offer.find_all(
            'div',
            {
                'class': 'div_cc margin_auto_0',
            }
        )[0].find_all(
            'span'
        )[0].string

        if condition in CONDITIONS:
            return condition
        else:
            raise ValueError(f'Item: {part_number}, Invalid condition: {condition}')

    @staticmethod
    def _get_quantity(html_offer: Tag, part_number: str) -> int:
        """
        Получение количества предметов в позиции
        :param html_offer: позиция в html
        :return: Количество предметов в позиции
        """
        quantity = html_offer.find_all(
            'div',
            {
                'class': 'div_qty margin_auto_0',
            }
        )[0].find_all(
            'div',
            {
                'class': 'product_infos_inside_product_box_list pd10',
            }
        )[0].contents[1].string
        if quantity.isdigit():
            return int(quantity)
        elif quantity == 'On demand':
            return 1
        else:
            raise ValueError(f'Item: {part_number}, Invalid quantity: {quantity}')

    def _get_offer_country(self, html_offer: Tag, part_number: str) -> str | int:
        """
        Получение местонахождения позиции
        :param html_offer: позиция в html
        :param part_number: Парт-номер позиции
        :return: Местонахождение позиции
        """
        location = html_offer.find_all(
            'div',
            {
                'class': 'div_location margin_auto_0',
            }
        )[0].find_all(
            'span'
        )[0].string
        return location

    def _get_price(self, html_offer: Tag) -> tuple[int | None, str | int]:
        """
        Получение цены позиции
        :param html_offer: позиция в html
        :return: Цена позиции
        """
        try:
            row_price = html_offer.find_all(
                'span',
                {
                    'class': 'small-text bold price_product_list_result',
                }
            )[0].find_all(
                'span'
            )
            if row_price[0].string and 'ask price' in row_price[0].string.lower():
                price = None
                offer_price_unit = 'USD'
            else:
                price = row_price[0].find_all()
                offer_price_unit = price[0].string.lower()
                price = (float(price[1].string.strip().replace(' ', '')) +
                         float(price[2].string.strip().replace(' ', '')) * 0.01)
        except IndexError:
            price = None
            offer_price_unit = 'USD'

        return price, offer_price_unit

    def _get_lead_time(self, html_offer: Tag, part_number: str) -> tuple[int, int]:
        """
        Получение lead_time позиции
        :param html_offer: позиция в html
        :return: lead_time
        """
        lead_time = html_offer.find_all(
            'div',
            {
                'class': 'div_lead_time margin_auto_0',
            }
        )[0].find_all(
            'div',
            {
                'class': 'product_infos_inside_product_box_list pd10'
            }
        )[0].string
        row_lead_time = lead_time.replace('\n', '').replace('\t', '').strip().lower().split(' ')

        if 'between' in row_lead_time:
            row_lead_time.remove('between')
            row_lead_time.remove('and')
            if 'months' in row_lead_time:
                int_leadtime_start = int(row_lead_time[0]) * 30
                int_leadtime_end = int(row_lead_time[1]) * 30
            elif 'weeks' in row_lead_time:
                int_leadtime_start = int(row_lead_time[0]) * 7
                int_leadtime_end = int(row_lead_time[1]) * 7
            elif 'days' in row_lead_time:
                int_leadtime_start = int(row_lead_time[0])
                int_leadtime_end = int(row_lead_time[1])
            else:
                raise ValueError(f'Item: {part_number}, Invalid lead time: {lead_time}')
        elif 'n/a' in row_lead_time or 'tbd' in row_lead_time or 'tbc' in row_lead_time or 'tbc.' in row_lead_time:
            int_leadtime_start = 999
            int_leadtime_end = 999
        elif 'stock' in row_lead_time or 'stock,' in row_lead_time:
            int_leadtime_start = 0
            int_leadtime_end = 0
        elif 'days' in row_lead_time or 'day' in row_lead_time:
            int_leadtime_start = int(row_lead_time[0])
            int_leadtime_end = int(row_lead_time[0])
        elif len(row_lead_time) == 1:
            if row_lead_time[0].isdigit():
                int_leadtime_start = int(row_lead_time[0])
                int_leadtime_end = int(row_lead_time[0])
            else:
                int_leadtime_start = 999
                int_leadtime_end = 999
        else:
            raise ValueError(f'Item: {part_number}, Invalid lead time: {lead_time}')

        # Если есть хоть один оффер с валидными leadtime, то офферы с не валидным leadtime будут убраны
        if int_leadtime_start != 999 and int_leadtime_end != 999:
            self.leadtime_limit = True

        return int_leadtime_start, int_leadtime_end

    def _get_update_on(self, html_offer: Tag) -> datetime.timestamp:
        """
        Получение даты обновления позиции
        :param html_offer: позиция в html
        :return: Дата обновления
        """
        update_on = html_offer.find_all(
            'div',
            {
                'class': 'div_update_on margin_auto_0',
            }
        )[0].find_all(
            'span',
        )[0].string

        return datetime.strptime(update_on, '%d-%b-%Y').timestamp()

    def _get_comment(self, html_offer: Tag) -> str | None:
        """
        Получение комментария к позиции
        :param html_offer: позиция в html
        :return: Комментарий
        """
        card_url = html_offer.find_all(
            'a',
            {
                'class': 'global_link_redirection',
            }
        )[0].attrs['href']

        cookies = {
            'JSESSIONID': settings.AEROBAY_SETTINGS.JSESSIONID
        } if settings.AEROBAY_SETTINGS.JSESSIONID else None

        response = self.session.get(
            'https://www.aero-bay.com' + card_url,
            cookies=cookies
        )
        bs = BeautifulSoup(response.text, 'html.parser')
        comment = bs.find_all(
            'p',
            {
                'class': 'location under_title_font_style style_under_text',
            }
        )
        if comment:
            return comment[0].string or ''


class GetOfferAvioSupport(GetOfferCommon):
    """
    Получение квот с https://aviosupport.com/
    """
    raw_offers = list()
    page_limit = 10

    def __init__(self, items: list[str], driver: webdriver):
        self.items = items
        # self.context = context
        self.driver = driver

    def get_offers(self) -> list[Offer]:
        """
        Основная функция для получения квот
        :return: Список квот
        """
        self._log_in()

        sleep(2)

        self.driver.get('https://aviosupport.com/search/newsearch.aspx')
        sleep(3)

        part_numbers_to_parse = self.items[:self.page_limit]
        iteration = 1
        offers = []
        while part_numbers_to_parse:
            self._part_number_search(part_numbers_to_parse)
            sleep(2)
            try:
                main_table = self.driver.find_element(By.XPATH, '/html/body/form/div[6]/div[1]/div[2]/table')
            except NoSuchElementException as e:
                logger.info(f'[{part_numbers_to_parse}] No data on aviosupport')
            else:
                try:
                    tables = main_table.find_elements(By.XPATH, '/html/body/form/div[6]/div[1]/div[2]/table/tbody/tr/td/table')
                    for index, table in enumerate(tables):

                        tag_index = 2 if index % 2 else 1

                        quantity, leadtime, price, offer_price_unit = self._get_availability(table, index)
                        if not quantity or not price:
                            continue

                        offer_info = {
                            'part_number': self._get_part_number(table, index),
                            'description': self._get_description(table, index),
                            'condition': None,
                            'quantity': quantity,
                            'leadtime': leadtime,
                            'price': price,
                            'pre_packing': self._get_pre_packing(table, index),
                            'certificate': None,
                        }
                        if leadtime is not None and leadtime:
                            int_leadtime_start = leadtime
                            int_leadtime_end = leadtime
                        else:
                            int_leadtime_start = 0
                            int_leadtime_end = 0

                        details = table.find_elements(
                            By.CSS_SELECTOR,
                            f'a#ContentMain_rptProducts_btnAdditionalDetails{tag_index}_{index}'
                        )
                        if details:
                            try:
                                self.driver.execute_script('arguments[0].click();', details[0])
                            except StaleElementReferenceException as e:
                                logger.info(str(e))
                            offer_info['condition'] = self._get_condition(table, index, tag_index)
                            offer_info['certificate'] = self._get_certificate(table, index, tag_index)

                        raw_offer = Offer(
                            inventory=offer_info['part_number'],
                            offer_description=offer_info['description'],
                            condition=offer_info['condition'],
                            quantity=quantity,
                            offer_country='TO BE ANNOUNCED',
                            price=price,
                            price_unit=offer_price_unit,
                            int_leadtime_start=int_leadtime_start,
                            int_leadtime_end=int_leadtime_end,
                            company='AVIOSUPPORT',
                            commit_date_unix=None,
                            aviator_purchase='LM',
                            to_buy=True,
                            sale_type='SALE',
                            certificate=str(offer_info['certificate']) if offer_info['certificate'] else None,
                        )

                        offers.append(raw_offer)
                except Exception as e:
                    error_handler_to_logger(e, 'AvioSupport')

            part_numbers_to_parse = self.items[
                                    self.page_limit * iteration:(self.page_limit * iteration) + self.page_limit
                                    ]
            iteration += 1
        return offers

    def _log_in(self, tries: int = 0):
        """
        Аутентификация на сайте
        :param tries: Количество попыток аутентификации
        :return: None
        """
        if tries >= 5:
            return None
        self.driver.get('https://aviosupport.com/MyAvio/signin.aspx')
        try:
            login = self.driver.find_element(By.CSS_SELECTOR, 'input#ContentMain_uiUserid')
            login.send_keys(settings.AVIOSUPPORT_SETTINGS.USER_NAME)
            password = self.driver.find_element(By.CSS_SELECTOR, 'input#ContentMain_uiSignInPassword')
            password.send_keys(settings.AVIOSUPPORT_SETTINGS.PASSWORD)
            login_button = self.driver.find_element(By.CSS_SELECTOR, 'input#ContentMain_BtnSignIn')
            self.driver.execute_script('arguments[0].click();', login_button)
        except NoSuchElementException as e:
            sleep(1)
            self._log_in(tries + 1)


    def _part_number_search(self, part_numbers_to_parse: list[str], tries: int = 0) -> None:
        """
        Поиск списка парт номеров
        :param part_numbers_to_parse: Список парт номеров
        :param tries: Номер попытки поиска
        :return: None
        """
        if tries >= 10:
            return None
        try:
            search_area = self.driver.find_element(By.CSS_SELECTOR, 'textarea#ContentMain_uiPNSearch')
            search_area.clear()
            search_area.send_keys('\n'.join(part_numbers_to_parse))

            search_button = self.driver.find_element(By.CSS_SELECTOR, 'input#ContentMain_btnPNSearch')
            self.driver.execute_script('arguments[0].click();', search_button)

        except NoSuchElementException as e:
            sleep(1)
            return self._part_number_search(part_numbers_to_parse, tries + 1)
        except ElementNotInteractableException as e:
            sleep(1)
            return self._part_number_search(part_numbers_to_parse, tries + 1)
        except StaleElementReferenceException as e:
            sleep(1)
            return self._part_number_search(part_numbers_to_parse, tries + 1)

    def _get_part_number(self, table, index) -> str:
        """
        Получение парт номера
        :param table: Таблица, в которой происходит поиск
        :param index: Порядковый номер записи
        :return: str
        """
        return table.find_element(By.CSS_SELECTOR, f'span#ContentMain_rptProducts_lblPNum_{index}').text

    def _get_description(self, table, index) -> str:
        """
        Получение писания квоты
        :param table: Таблица, в которой происходит поиск
        :param index: Порядковый номер записи
        :return: str
        """
        return table.find_element(
            By.CSS_SELECTOR,
            f'span#ContentMain_rptProducts_lblDescription_{index}'
        ).text

    def _get_condition(self, table, index, tag_index: int) -> str | None:
        """
        Получение состояния квоты
        :param table: Таблица, в которой происходит поиск
        :param index: Порядковый номер записи
        :param tag_index: Чётность записи
        :return:
        """
        detail = table.find_element(
            By.CSS_SELECTOR,
            f'span#ContentMain_rptProducts_UpdateLabel{tag_index}_{index}'
        ).text
        detail = detail.split('\n')
        if 'Condition' in detail[2]:
            return detail[2].strip().split(' ')[-1]

    def _get_certificate(self, table, index, tag_index: int) -> str:
        """
        Получение сертификата
        :param table: Таблица, в которой происходит поиск
        :param index: Порядковый номер записи
        :param tag_index: Чётность записи
        :return:
        """
        certificate = table.find_element(
            By.CSS_SELECTOR,
            f'span#ContentMain_rptProducts_UpdateLabel{tag_index+2}_{index}'
        ).text
        return certificate.replace('\n', ' ')

    def _get_availability(self, table, index) -> tuple[int | None, int | None, float | None, str | None]:
        """
        Получение данных доступности квоты
        :param table: Таблица, в которой происходит поиск
        :param index: Порядковый номер записи
        :return: Количество, leadtime, цены, валюта
        """
        quantity = None
        leadtime = 0
        price = None
        offer_price_unit = 'USD'
        availability = table.find_element(
            By.CSS_SELECTOR, f'span#ContentMain_rptProducts_lblAvailability_{index}'
        )
        availability = availability.text
        for row in availability.split('\n'):
            if 'Stock' in row:
                if 'In Stock' in row:
                    quantity = float(row.split(':')[-1].strip())
            elif 'Leadtime' in row:
                try:
                    leadtime = int(re.findall(r'\d+', row)[0])
                except Exception as e:
                    error_handler_to_logger(e, 'AvioSupport')
                    leadtime = 0
            elif 'Price' in row:
                price = row.replace(',', '').split(':')[-1].strip()
                offer_price_unit = price[0]
                price = float(row.replace(',', '').split(':')[-1].strip()[1:])
        return quantity, leadtime, price, offer_price_unit

    def _get_pre_packing(self, table, index) -> str | None:
        """
        Получение данных количества единиц инвентаря, соответствующих данной квоте
        :param table: Таблица, в которой происходит поиск
        :param index: Порядковый номер записи
        """
        pre_packing = table.find_elements(By.CSS_SELECTOR, f'span#ContentMain_rptProducts_lblPriceUM_{index}')
        if pre_packing:
            pre_packing = pre_packing[0].text.replace('/', '').upper()
            if pre_packing in PRE_PACKING:
                return pre_packing


class GetOfferEcsat(GetOfferCommon):
    """
    Получение квот с https://aviosupport.com/
    """
    raw_offers = list()

    def __init__(self, items: list[str], driver: webdriver):
        self.items = items
        self.driver = driver

    def get_offers(self) -> list[Offer]:
        """
        Основная функция для получения квот
        :return: Список квот
        """
        self._log_in()
        offers = []

        for part_number in self.items:
            try:
                self.driver.get(f'https://www.e-csat.com/search?term={part_number}')
            except exceptions.WebDriverException as e:
                error_handler_to_logger(e, 'e-csat')
                continue

            sleep(1)

            rows = self.driver.find_elements(By.CSS_SELECTOR, 'tr.items__row')
            for row in rows:

                inventory = self._get_inventory(row)
                if inventory.upper() != part_number:
                    continue

                quantity = self._get_quantity(row)
                if quantity is None:
                    continue

                price, price_unit = self._get_price(row)
                if price is None:
                    continue

                row_offer = Offer(
                    inventory=inventory,
                    offer_description='',
                    condition='NE',
                    quantity=quantity,
                    offer_country='EUROPEAN UNION',
                    price=price,
                    price_unit=price_unit,
                    int_leadtime_start=0,
                    int_leadtime_end=0,
                    company='CZECH AIRLINES TECHNICS',
                    commit_date_unix=None,
                    aviator_purchase='LM',
                    to_buy=True,
                    sale_type='SALE',
                )
                offers.append(row_offer)

        return offers

    def _get_inventory(self, row) -> str:
        """
        Поиск парт номера
        :param row: Строка для поиска данных
        :return: Парт номер
        """
        return row.find_element(By.CSS_SELECTOR, 'td.items__number').text

    def _get_quantity(self, row) -> int | None:
        """
        Получение количества доступных объектов для квоты
        :param row: Строка для поиска данных
        :return: Количество объектов
        """
        in_stock = row.find_element(By.CSS_SELECTOR, 'td.items__stock').text
        if in_stock.lower() == 'price on request':
            return None
        in_stock = in_stock.split()
        for item in in_stock:
            if item.isdigit():
                return int(item)

    def _get_price(self, row) -> tuple[float | None, str | None]:
        """
        Получение цены и валюты
        :param row: Строка для поиска данных
        :return: Цена и валюта
        """
        item_price = row.find_element(By.CSS_SELECTOR, 'td.items__price').text
        price = self.extract_number(item_price)

        if price and len(item_price) >= 2:
            item_price = item_price.split()
            price_unit = item_price[-1].upper()
        else:
            if not price:
                price = None
            price_unit = 'USD'

        return price, price_unit

    @staticmethod
    def extract_number(text: str) -> float | int | None:
        """
        Поиск и извлечение цены в строке
        :param text: Цена на сайте
        :return: Преобразованная цена
        """
        match = re.search(r'\$?\s?(\d{1,3}(?:[ ,]\d{3})*(?:\.\d+)?)', text)
        if match:
            number_str = match.group(1).replace(",", "").replace(' ', '')
            return float(number_str) if "." in number_str else int(number_str)
        return None

    def _log_in(self):
        """
        Аутентификация на сайте
        :return: None
        """
        self.driver.get('https://www.e-csat.com/')
        try:
            login_tab = self.driver.find_element(By.CSS_SELECTOR, 'label.form__input-label[for="login"]')
            self.driver.execute_script('arguments[0].click();', login_tab)
            login = self.driver.find_element(By.CSS_SELECTOR, 'input#login')
            login.send_keys(settings.ECSAT_SETTINGS.USER_NAME)

            password_tab = self.driver.find_element(By.CSS_SELECTOR, 'label.form__input-label[for="password"]')
            self.driver.execute_script('arguments[0].click();', password_tab)
            password = self.driver.find_element(By.CSS_SELECTOR, 'input#password')
            password.send_keys(settings.ECSAT_SETTINGS.PASSWORD)

            login_button = self.driver.find_element(By.CSS_SELECTOR, 'input[value="Enter"]')
            self.driver.execute_script('arguments[0].click();', login_button)
            sleep(1)
        except NoSuchElementException:
            pass


class GetOfferDasi(GetOfferCommon):
    """
    Получение квот с https://store.dasi.com/
    """
    raw_offers = list()

    def __init__(self, items: list[str], driver: webdriver):
        self.items = items
        # self.context = context
        self.driver = driver

    def get_offers(self, tries: int = 0) -> list[Offer]:
        """
        Основная функция для получения квот
        :param tries: Количество попыток выполнения функции
        :return: Список квот
        """
        if tries >= 5:
            logger.error('[DASI][Error] Too many tries to login')
            return []
        # self._full_log_in()
        self._add_cookies()
        offers = []

        try:
            self.driver.get('https://store.dasi.com/search.aspx')
        except exceptions.WebDriverException as e:
            logger.error('[DASI][ERROR] ' + str(e))
            return []

        sleep(2)

        search_area = self.driver.find_element(By.CSS_SELECTOR, 'textarea.searchtext')

        search_area.clear()
        search_area.send_keys('\n'.join(self.items))

        exact_match = self.driver.find_element(
            By.CSS_SELECTOR,
            'input#ctl00_ctl00_cph1_cph1_ctrlSearch_cbNotExactMatch'
        )
        self.driver.execute_script('arguments[0].click();', exact_match)

        search_button = self.driver.find_element(
            By.CSS_SELECTOR,
            'input.searchbutton#ctl00_ctl00_cph1_cph1_ctrlSearch_btnMultiSearch'
        )
        self.driver.execute_script('arguments[0].click();', search_button)

        sleep(3)

        if self.driver.find_elements(By.CSS_SELECTOR, 'div[style="width: 100%; height: auto; display: none;"]'):
            expand_buttons = self.driver.find_elements(By.CSS_SELECTOR, 'div.expand')
            for expand_button in expand_buttons:
                self.driver.execute_script('arguments[0].click();', expand_button)

        raw_items = self.driver.find_elements(
            By.XPATH,
            '/html/body/form/div[3]/div[3]/div[3]/div/div/div/div/div[2]/div[6]/table/tbody/tr/td/div'
        )

        for raw_item in raw_items:
            inventory = self._get_inventory(raw_item)
            if inventory not in self.items:
                continue
            try:
                item_info = raw_item.find_elements(By.CSS_SELECTOR, 'tr.cart-item-row')
                for item in item_info:
                    row_info = item.find_elements(By.TAG_NAME, 'td')

                    if 'Log in\nto view' == row_info[8].text:
                        logger.warning('[DASI] Need new cookie')

                    condition = self._get_condition(row_info)
                    description = self._get_description(row_info)
                    offer_country = self._get_offer_country(row_info, inventory)
                    leadtime = self._get_leadtime(row_info, inventory)
                    quantity = self._get_quantity(row_info)
                    price, price_unit = self._get_price(row_info)
                    if price is None:
                        continue
                    row_offer = Offer(
                        inventory=inventory,
                        offer_description=description,
                        condition=condition,
                        quantity=quantity,
                        offer_country=offer_country,
                        price=price,
                        price_unit=price_unit,
                        int_leadtime_start=leadtime,
                        int_leadtime_end=leadtime,
                        company='DASI',
                        commit_date_unix=None,
                        aviator_purchase='LM',
                        to_buy=True,
                        sale_type='SALE',
                    )
                    offers.append(row_offer)
            except Exception as e:
                logger.error(f'[DASI][ERROR] Item: {inventory}; Error: ' + str(e))
                error_handler_to_logger(e, 'DASI')

        return offers

    def _get_inventory(self, raw_item) -> str:
        """
        Получение парт номера квоты
        :param raw_item: Элемент, в которой происходит поиск
        :return: str
        """
        return raw_item.find_element(By.CSS_SELECTOR, 'div.product_list_title').text.split()[0]

    def _get_quantity(self, raw_item) -> str:
        """
        Получение количества доступных объектов для квоты
        :param raw_item: Строка для поиска данных
        :return: Количество объектов
        """
        return raw_item[7].text

    def _get_condition(self, raw_item) -> str:
        """
        Получение состояния квоты
        :param raw_item: Строка для поиска данных
        :return: Состояние объекта квоты
        """
        return raw_item[0].text

    def _get_description(self, raw_item) -> str:
        """
        Получение описания квоты
        :param raw_item: Строка для поиска данных
        :return: Описание квоты
        """
        return raw_item[1].text

    def _get_offer_country(self, raw_item, part_number: str):
        """
        Получение страны нахождения квоты
        :param raw_item: Строка для поиска данных
        :return: Страна
        """
        raw_country = raw_item[2].text.upper()
        return raw_country

    def _get_leadtime(self, raw_item, inventory: str = '') -> int | None:
        """
        Получение leadtime по квоте
        :param raw_item: Строка для поиска данных
        :param inventory: Парт номер квоты
        :return: leadtime
        """
        row_lead_time = raw_item[3].text.lower()
        try:
            if 'day' in row_lead_time:
                row_lead_time = row_lead_time.replace('day', '').strip()
                return int(row_lead_time)
            else:
                raise ValueError(f'Item: {inventory}, Invalid lead time: {row_lead_time}')
        except Exception as e:
            logger.error(f'[DASI][ERROR] Invalid lead time: {str(e)}')

    def _get_price(self, raw_item) -> tuple[float | None, str | None]:
        """
        Получение цены и валюты по квоте
        :param raw_item: Строка для поиска данных
        :return: Цена и валюта
        """
        item_price = raw_item[8].text

        if 'RFQ' in item_price:
            price = None
            price_unit = 'USD'
        else:
            item_price = item_price.replace(',', '')

            price = self.extract_number(item_price)

            if price:
                price_unit = item_price[0]
            else:
                if not price:
                    price = None
                price_unit = 'USD'

        return price, price_unit

    def _add_cookies(self):
        """
        Использование ранее полученных куки для получения доступа к сайту
        :return: None
        """
        self.driver.get(f'https://store.dasi.com')
        sleep(1)

        cookies = pd.read_csv('media/cookies.csv', delimiter=';')
        dasi_cookies = cookies.loc[cookies['site'] == 'DASI']

        value1 = dasi_cookies.value1.values[0]
        value2 = dasi_cookies.value2.values[0]
        value3 = dasi_cookies.value3.values[0]
        value4 = dasi_cookies.value4.values[0]

        if value1 and value2 and value3 and value4:
            cookies = {
                '.ASPXANONYMOUS': value1,
                'ASP.NET_SessionId': value2,
                'DASI.CustomerSessionGUIDCookie': value3,
                'NOPCOMMERCE.AUTH': value4,
            }
            for key, value in cookies.items():
                self.driver.add_cookie({'name': key, 'value': value})
        else:
            logger.warning('[DASI] Need new cookie (now don\'t have any cookies)')


class GetOfferProponent(GetOfferCommon):
    """
    Получение квот с https://procart.proponent.com/
    """
    raw_offers = list()

    def __init__(self, items: list[str], driver: webdriver):
        self.items = items
        self.driver = driver

    def get_offers(self, retries: int = 0, full_login: bool = False) -> list[Offer]:
        """
        Основная функция для получения квот
        :param retries: Количество попыток выполнения функции
        :param full_login: Необходимость полного логина
        :return: Список квот
        """
        if retries >= 5:
            logger.error('[Proponent][Error] Too many tries to login')
            return []

        self._set_cookies(full_login=full_login)
        offers = []

        try:
            self.driver.get('https://procart.proponent.com')
            sleep(1)
            names = self.driver.find_elements(By.CSS_SELECTOR, 'strong#lbluserName')
            if not names or names[0].text != 'Sam Adamson':
                return self.get_offers(retries + 1, True)
        except exceptions.WebDriverException as e:
            logger.error('[Proponent][ERROR] ' + str(e))
            return self.get_offers(retries + 1)

        search_area = self.driver.find_element(By.CSS_SELECTOR, 'textarea#MainContent_txtBulkPart')
        search_area.send_keys('\n'.join(self.items))

        search_button = self.driver.find_element(By.CSS_SELECTOR, 'input#MainContent_btnBulkSearch')
        self.driver.execute_script('arguments[0].click();', search_button)
        sleep(1)

        page = self._get_page()

        number_of_page = page.text.strip()
        if number_of_page.isdigit():
            number_of_page = int(number_of_page)
        else:
            number_of_page = 1

        for i in range(number_of_page):
            rows = self.driver.find_elements(By.CSS_SELECTOR, 'tr.rowMainGrid.MainGrid_ParentRow')
            for row in rows:
                inventory = self._get_inventory(row)
                if inventory.upper() not in self.items:
                    continue
                id_num = row.get_attribute('id')

                quantity = self._get_quantity(row)
                if quantity is None:
                    continue

                description = self._get_description(row)
                certs = self._get_certs(row)
                pre_packing = self._get_pre_packing(row)

                price, price_unit = self._get_price(row)
                if not price:
                    continue
                selects = self.driver.find_elements(By.CSS_SELECTOR, f'select#ddlWarehouse_jQGridDemo_{id_num}_t')
                if selects:
                    select = Select(selects[0])
                    options = select.options
                    if options:
                        for option in options:
                            select.select_by_visible_text(option.text)
                            qty = self.driver.find_elements(
                                By.CSS_SELECTOR,
                                f'td[aria-describedby="jQGridDemo_{id_num}_t_WhsQty"]'
                            )
                            if qty:
                                qty = qty[0].text
                            else:
                                continue
                            warehouse = self._get_warehouse(select.all_selected_options[0], inventory)

                            row_offer = Offer(
                                inventory=inventory,
                                offer_description=description,
                                condition='NE',
                                quantity=qty,
                                offer_country=warehouse,
                                price=price,
                                price_unit=price_unit,
                                int_leadtime_start=0,
                                int_leadtime_end=0,
                                company='PROPONENT',
                                commit_date_unix=None,
                                aviator_purchase='LM',
                                to_buy=True,
                                sale_type='SALE',
                                certificate=certs,
                                pre_packing=pre_packing,
                            )
                            offers.append(row_offer)
                    else:
                        row_warehouse = self.driver.find_elements(
                            By.CSS_SELECTOR,
                            f'span#lblWarehouseName_jQGridDemo_{id_num}_t'
                        )
                        if row_warehouse:
                            warehouse = self._get_warehouse(row_warehouse[0], inventory)
                            row_offer = Offer(
                                inventory=inventory,
                                offer_description=description,
                                condition='NE',
                                quantity=quantity,
                                offer_country=warehouse,
                                price=price,
                                price_unit=price_unit,
                                int_leadtime_start=0,
                                int_leadtime_end=0,
                                company='PROPONENT',
                                commit_date_unix=None,
                                aviator_purchase='LM',
                                to_buy=True,
                                sale_type='SALE',
                                certificate=certs,
                                pre_packing=pre_packing,
                            )
                            offers.append(row_offer)

            next_page = self.driver.find_element(By.CSS_SELECTOR, 'td#next_jQGridDemoPager')
            self.driver.execute_script('arguments[0].click();', next_page)
            sleep(2)

        return offers

    def _get_page(self, tries: int = 0):
        """
        Поиск номера страницы
        :param tries: количество попыток
        :return: None
        """
        if tries >= 5:
            raise exceptions.WebDriverException('Can\'t find number of pages')
        try:
            page = self.driver.find_element(By.CSS_SELECTOR, 'span#sp_1_jQGridDemoPager')
        except NoSuchElementException:
            sleep(1)
            return self._get_page(tries + 1)
        return page

    def _get_inventory(self, row) -> str:
        """
        Получение парт номера квоты
        :param row: Элемент, в которой происходит поиск
        :return: str
        """
        part_number = row.find_element(
            By.CSS_SELECTOR,
            'td.customer-part[aria-describedby="jQGridDemo_Cust_part_copy"]'
        )
        if part_number:
            return part_number.text
        return ''

    def _get_quantity(self, row) -> int | None:
        """
        Получение количества доступных объектов для квоты
        :param row: Строка для поиска данных
        :return: Количество объектов
        """
        quantity = row.find_element(By.CSS_SELECTOR, 'td[aria-describedby="jQGridDemo_QtyAvailable"]').text
        if quantity.isdigit():
            return int(quantity)

    def _get_description(self, row) -> str:
        """
        Получение описания квоты
        :param row: Строка для поиска данных
        :return: Описание квоты
        """
        description = row.find_element(By.CSS_SELECTOR, 'td[aria-describedby="jQGridDemo_Item_description1"]').text
        if description:
            description = description.replace('\n', '')
        return description or ''

    def _get_certs(self, row) -> str:
        """
        Получение сертификатов квоты
        :param row: Строка для поиска данных
        :return: Сертификаты квоты
        """
        certs = row.find_elements(By.CSS_SELECTOR, 'td[aria-describedby="jQGridDemo_CertNotes"]')
        if certs:
            return certs[0].text.replace('\n', '')
        return ''

    def _get_pre_packing(self, row) -> str:
        """
        Получение единицы измерения квоты
        :param row: Строка для поиска данных
        :return: Единица измерения квоты
        """
        pre_packing = row.find_elements(By.CSS_SELECTOR, 'td[aria-describedby="jQGridDemo_Um"]')
        if pre_packing and pre_packing[0].text in PRE_PACKING:
            return pre_packing[0].text
        return 'EA'

    def _get_price(self, row) -> tuple[float | None, str | None]:
        """
        Получение цены и валюты по квоте
        :param row: Строка для поиска данных
        :return: Цена и валюта
        """
        item_price = row.find_element(By.CSS_SELECTOR, 'td[aria-describedby="jQGridDemo_Price"]').text
        price = self.extract_number(item_price)

        if price and len(item_price) >= 2:
            price_unit = item_price[0]
        else:
            if not price:
                price = None
            price_unit = 'USD'

        return price, price_unit

    def _get_warehouse(self, row, part_number) -> str:
        """
        Получение склада нахождения квоты
        :param row: Строка для поиска данных
        :param part_number: Парт номер для логирования
        :return: Id страны
        """
        raw_country = row.text.replace('Warehouse: ', '').strip().upper()

        country = raw_country.split()[-1]
        return country

    def _set_cookies(self, tries: int = 0, full_login: bool = False):
        """
        Использование ранее полученных куки для получения доступа к сайту
        :param tries: Количество попыток получения/установки куки
        :param full_login: Необходимость обновления куки
        :return: None
        """
        if tries >= 5:
            raise Exception('Too many tries to login')
        self.driver.get(f'https://procart.proponent.com/')
        sleep(1)
        cookies = pd.read_csv('media/cookies.csv', delimiter=';')
        proponent_cookies = cookies.loc[cookies['site'] == 'Proponent']
        csrf_token = proponent_cookies.value1.values[0]
        net_sessionid = proponent_cookies.value2.values[0]

        if csrf_token and net_sessionid and not full_login:
            cookies = {
                'csrf_token': csrf_token,
                'ASP.NET_SessionId': net_sessionid,
            }
            for key, value in cookies.items():
                self.driver.add_cookie({'name': key, 'value': value})
        else:
            self._log_in()
            self._set_cookies(tries + 1)

    def _log_in(self):
        """
        Аутентификация на сайте
        :return: None
        """
        self.driver.get('https://procart.proponent.com/Login.aspx')
        sleep(1)
        login = self.driver.find_element(By.CSS_SELECTOR, 'input#MainContent_txtUserName')
        login.send_keys(settings.PROPONENT_SETTINGS.USER_NAME)

        password = self.driver.find_element(By.CSS_SELECTOR, 'input#MainContent_txtPassword')
        password.send_keys(settings.PROPONENT_SETTINGS.PASSWORD)

        login_button = self.driver.find_element(By.CSS_SELECTOR, 'input#MainContent_btnLogin')
        self.driver.execute_script('arguments[0].click();', login_button)
        sleep(1)
        csrf_token = self.driver.get_cookie('csrf_token')
        session_id = self.driver.get_cookie('ASP.NET_SessionId')
        cookies = pd.read_csv('media/cookies.csv', delimiter=';')
        cookies.loc[cookies['site'] == 'Proponent', 'value1'] = csrf_token['value']
        cookies.loc[cookies['site'] == 'Proponent', 'value2'] = session_id['value']
        cookies.to_csv('media/cookies.csv', index=False, sep=';')


class GetOfferSatair(GetOfferCommon):
    """
    Получение квот с https://www.satair.com
    """
    raw_offers = list()

    def __init__(self, items: list[str], session: Session):
        self.items = items
        self.session = session

    def get_offers(self, retries: int = 0) -> list[Offer]:
        """
        Основная функция для получения квот
        :param retries: Количество попыток выполнения функции
        :return: Список квот
        """
        if retries >= 5:
            logger.error('[Satair][Error] Too many tries to login')
            return []

        self._log_in()

        offers = []

        for item in self.items:
            raw_main_info = self.session.get(
                'https://www.satair.com/api/offersearch',
                params={'urlParams': f'q={item}&currentPage=0&pageSize=100&fields=FULL'}
            )
            main_info = json.loads(raw_main_info.content)

            products = []
            request_for_info = {'productPriceRequests': []}
            if 'Data' not in main_info:
                logger.error(f'[Satair] No "Data" in response: {str(main_info)}, retry: {retries+1}')
                return self.get_offers(retries + 1)
            for offer in main_info['Data']['Products']:
                if offer['ManufacturerAid'] == item:
                    request_for_info['productPriceRequests'].append(
                        {
                            'OfferId': offer['Id'],
                            'Quantity': 1,
                         }
                    )
                    products.append(offer)
            if not request_for_info['productPriceRequests']:
                continue

            offers_additional_info = self.session.post(
                'https://www.satair.com/api/product/additionalinfo/',
                json=request_for_info
            )
            if offers_additional_info.status_code != 200:
                continue
            offers_additional_info = json.loads(offers_additional_info.content)

            for number, offer_add_info in enumerate(offers_additional_info['Data']):
                if offer_add_info['Availabilities'] and offer_add_info['Availabilities'][0]['InStock']:
                    state = products[number]['State'].replace(' ', '').lower()
                    if state in FULL_CONDITION_NAME:
                        condition = FULL_CONDITION_NAME[state]
                    else:
                        continue

                    if offer_add_info['RemainingOfferQuantity'] == 0:
                        plants = self.session.get(
                            f'https://www.satair.com/api/product/plants/{offer_add_info["Id"]}',
                        )
                        plants = json.loads(plants.content)
                        if 'Data' not in plants:
                            logger.error(f'[Satair] No "Data" in response: {str(plants)}, retry: {retries + 1}')
                            return self.get_offers(retries + 1)
                        for plant in plants['Data']['Plants']:
                            offer_country = self._get_country(plant['Warehouse'])
                            row_offer = Offer(
                                inventory=item,
                                offer_description=products[number]['Name'],
                                condition=condition,
                                quantity=plant['Quantity'],
                                offer_country=offer_country,
                                price=offer_add_info['BasePrice']['Value'],
                                price_unit=offer_add_info['BasePrice']['CurrencyIso'],
                                int_leadtime_start=0,
                                int_leadtime_end=0,
                                certificate=products[number]['Certificate'],
                                company='SATAIR',
                                commit_date_unix=None,
                                aviator_purchase='LM',
                                to_buy=True,
                                sale_type='SALE',
                            )
                            offers.append(row_offer)



                    else:
                        offer_country = self._get_country(offer_add_info['Warehouse']['Name'])
                        row_offer = Offer(
                            inventory=item,
                            offer_description=products[number]['Name'],
                            condition=condition,
                            quantity=offer_add_info['RemainingOfferQuantity'],
                            offer_country=offer_country,
                            price=offer_add_info['BasePrice']['Value'],
                            price_unit=offer_add_info['BasePrice']['CurrencyIso'],
                            int_leadtime_start=0,
                            int_leadtime_end=0,
                            certificate=products[number]['Certificate'],
                            company='SATAIR',
                            commit_date_unix=None,
                            aviator_purchase='LM',
                            to_buy=True,
                            sale_type='SALE',
                        )
                        offers.append(row_offer)

        return offers

    def _get_country(self, text: str):
        """
        Получение страны нахождения квоты
        :param text: Строка для поиска данных
        :return: Id страны
        """
        match = re.search(r'\(([^)]+)\)', text)
        if match:
            return match.group(1)
        match = text.split(',')
        if match:
            match = match[-1].strip().upper()
            return match
        return 'TO BE ANNOUNCED'

    def _log_in(self):
        """
        Аутентификация на сайте
        :return: None
        """
        data = {
            'userId': settings.SATAIR_SETTINGS.USER_NAME,
            'password': settings.SATAIR_SETTINGS.PASSWORD,
            'rememberMe': False,
        }
        self.session.post('https://www.satair.com/api/login', data)


class GetOfferWencor(GetOfferCommon):
    """
    Получение квот с https://fly.wencor.com/
    """
    raw_offers = list()

    def __init__(self, items: list[str], driver: webdriver):
        self.items = items
        self.driver = driver

    def get_offers(self, retries: int = 0, full_login: bool = False) -> list[Offer]:
        """
        Основная функция для получения квот
        :param retries: Количество попыток выполнения функции
        :param full_login: Необходимость полного логина
        :return: Список квот
        """
        if retries >= 5:
            logger.error('[Wencor][Error] Too many tries to login')
            return []

        self._set_cookies(full_login=full_login)
        offers = []

        try:
            self.driver.get('https://fly.wencor.com/search')
            sleep(1)
            if self.driver.title == 'Home - WencorFly':
                return self.get_offers(retries + 1, True)
        except exceptions.WebDriverException as e:
            logger.error('[Wencor][ERROR] ' + str(e))
            return self.get_offers(retries + 1)

        search_area = self.driver.find_element(By.CSS_SELECTOR, 'textarea#itemnumberinputbox')
        search_area.send_keys('\n'.join(self.items))

        search_button = self.driver.find_element(By.CSS_SELECTOR, 'button#addToQuickEntry')
        self.driver.execute_script('arguments[0].click();', search_button)
        sleep(5)

        first_tables = self.driver.find_elements(By.CSS_SELECTOR, 'div.information.info-no-image')
        part_numbers_to_search = []
        for table in first_tables:
            if table.text:
                item = table.text.split('\n')[0]
            else:
                item = None
            if item in self.items:
                in_stock = table.find_elements(By.CSS_SELECTOR, 'div.stock-quantity')
                if in_stock and 'In Stock' in in_stock[0].text:
                    part_numbers_to_search.append(item)
        for part_number_to_search in part_numbers_to_search:
            self.driver.get(f'https://fly.wencor.com/products/-/o/category/all/ecom-search/{part_number_to_search}')
            sleep(3)
            item_page = self.driver.find_elements(By.CSS_SELECTOR, 'a.product-name')
            if item_page:
                self.driver.execute_script('arguments[0].click();', item_page[0])
                sleep(2)

                quantity = self._get_quantity(self.driver)
                if quantity is None:
                    continue

                description = self._get_description(self.driver)
                price, price_unit = self._get_price(self.driver)
                if price is None or price_unit is None:
                    continue

                offer_country = self._get_country(self.driver)
                specifications = self.driver.find_elements(By.CSS_SELECTOR, 'div.specification-content')
                if specifications:
                    specification = specifications[0].find_elements(By.TAG_NAME, 'tr')
                    leadtime = self._get_leadtime(specification[8])
                    certificate = self._get_certificate(specification[9])
                else:
                    leadtime = 0
                    certificate = None

                row_offer = Offer(
                    inventory=part_number_to_search,
                    offer_description=description,
                    condition='NE',
                    quantity=quantity,
                    offer_country=offer_country,
                    price=price,
                    price_unit=price_unit,
                    int_leadtime_start=leadtime,
                    int_leadtime_end=leadtime,
                    certificate=certificate,
                    company='WENCOR',
                    commit_date_unix=None,
                    aviator_purchase='LM',
                    to_buy=True,
                    sale_type='SALE',
                )

                offers.append(row_offer)

        return offers

    def _get_leadtime(self, row) -> int:
        """
        Получение leadtime по квоте
        :param row: Строка для поиска данных
        :return: leadtime
        """
        leadtime = row.find_element(By.CSS_SELECTOR, 'td.value').text.lower()
        if 'days' in leadtime:
            match = re.search(r'(\d[\d\s]*\d)(?:[.,](\d+))?', leadtime)
            if match:
                days = match.group(1)
                if days and days[0].isdigit():
                    return int(days[0])

        return 0

    def _get_certificate(self, row) -> str:
        """
        Получение сертификата квоты
        :param row: Строка для поиска данных
        :return: Сертификат
        """
        return row.find_element(By.CSS_SELECTOR, 'td.value').text.strip()

    def _get_country(self, row) -> str | None:
        """
        Получение страны нахождения квоты
        :param row: Строка для поиска данных
        :return: Id страны
        """
        raw_country = row.find_element(By.CSS_SELECTOR, 'div.availability-delivery').text
        match = re.search(r'\(([^)]+)\)', raw_country)
        if match:
            match = match.group(1).strip().upper()
            return match
        return 'TO BE ANNOUNCED'

    def _get_quantity(self, row) -> int | None:
        """
        Получение количества доступных объектов для квоты
        :param row: Строка для поиска данных
        :return: Количество объектов
        """
        raw_quantities = row.find_elements(By.CSS_SELECTOR, 'div.stock-quantity')
        if raw_quantities:
            raw_quantity = raw_quantities[0].text
            if raw_quantity:
                raw_quantity_list = raw_quantity.split(': ')
                if len(raw_quantity_list) >= 2:
                    quantity = raw_quantity_list[1].strip().replace(',', '')
                    if quantity.isdigit():
                        return int(quantity)
        return None

    def _get_description(self, row) -> str:
        """
        Получение описания квоты
        :param row: Строка для поиска данных
        :return: Описание квоты
        """
        description = row.find_element(By.CSS_SELECTOR, 'div.product-description').text
        return description or ''

    def _get_price(self, row) -> tuple[float | None, str | None]:
        """
        Получение цены и валюты по квоте
        :param row: Строка для поиска данных
        :return: Цена и валюта
        """
        raw_price = row.find_element(By.CSS_SELECTOR, 'span.display-price')
        if raw_price:
            item_price = raw_price.find_element(By.CSS_SELECTOR, 'h2.price.new.price-large').text

            price = self.extract_number(item_price)

            if price and len(item_price) >= 2:
                price_unit = item_price[0]
            else:
                if not price:
                    price = None
                price_unit = 'USD'

            return price, price_unit
        return None, None

    def _set_cookies(self, tries: int = 0, full_login: bool = False):
        """
        Использование ранее полученных куки для получения доступа к сайту
        :param tries: Количество попыток получения/установки куки
        :param full_login: Необходимость обновления куки
        :return: None
        """
        if tries >= 5:
            raise Exception('[Wencor] Too many tries to login')
        if not full_login:
            self.driver.get('https://fly.wencor.com/log-in')
            sleep(1)

        cookies = pd.read_csv('media/cookies.csv', delimiter=';')
        wencor_cookies = cookies.loc[cookies['site'] == 'Wencor']

        id_cookie = wencor_cookies.value1.values[0]
        jsessionid_cookie = wencor_cookies.value2.values[0]

        if id_cookie and jsessionid_cookie and not full_login and id_cookie != 'q' and jsessionid_cookie != 'q':
            cookies = {
                'ID': id_cookie,
                'JSESSIONID': jsessionid_cookie,
            }
            for key, value in cookies.items():
                self.driver.add_cookie({'name': key, 'value': value})
        else:
            self._log_in()
            self._set_cookies(tries + 1)

    def _log_in(self):
        """
        Аутентификация на сайте
        :return: None
        """
        self.driver.get('https://fly.wencor.com/log-in')
        login_table = self.driver.find_element(
            By.CSS_SELECTOR,
            'div.rhy.widget__rhythmloginmultiinstancesportlet_WAR_'
            'rhythmloginmultiinstancesportlet_INSTANCE_Al8rQt3TrPh8_'
        )
        login = login_table.find_element(
            By.CSS_SELECTOR,
            'input#_rhythmloginmultiinstancesportlet_WAR_'
            'rhythmloginmultiinstancesportlet_INSTANCE_Al8rQt3TrPh8_username'
        )
        login.send_keys(settings.WENCOR_SETTINGS.USER_NAME)

        password = login_table.find_element(
            By.CSS_SELECTOR,
            'input#_rhythmloginmultiinstancesportlet_WAR_'
            'rhythmloginmultiinstancesportlet_INSTANCE_Al8rQt3TrPh8_password'
        )
        password.send_keys(settings.WENCOR_SETTINGS.PASSWORD)

        login_button = login_table.find_element(
            By.CSS_SELECTOR,
            'button.btn.btn-primary.login-btn'
        )
        sleep(1)
        self.driver.execute_script('arguments[0].click();', login_button)
        sleep(3)
        id_cookie = self.driver.get_cookie('ID')
        jsessionid_cookie = self.driver.get_cookie('JSESSIONID')

        cookies = pd.read_csv('media/cookies.csv', delimiter=';')
        cookies.loc[cookies['site'] == 'Wencor', 'value1'] = id_cookie['value']
        cookies.loc[cookies['site'] == 'Wencor', 'value2'] = jsessionid_cookie['value']
        cookies.to_csv('media/cookies.csv', index=False, sep=';')


class GetOfferAviall(GetOfferCommon):
    """
    Получение квот с https://shop.boeing.com/ (бывший Aviall)
    """
    raw_offers = list()
    logger_time = list()
    start_time = datetime

    def __init__(self, items: list[str], driver: webdriver):
        self.items = items
        self.driver = driver

    def get_offers(self, retries: int = 0, full_login: bool = False) -> list[Offer]:
        """
        Основная функция для получения квот
        :param retries: Количество попыток выполнения функции
        :param full_login: Необходимость полного логина
        :return: Список квот
        """
        try:
            if retries >= 5:
                logger.error('[Aviall][Error] Too many tries to login')
                return []

            self.start_time = datetime.now()
            self.logger_time = []
            try:
                self._log_in()
            except exceptions.WebDriverException as e:
                pass

            offers = []
            sleep(1)
            self.start_time = datetime.now()
            search_string = '+'.join(self.items).replace(' ', '')
            page = 0
            while page < 10:
                self.driver.get(f'https://shop.boeing.com/aviation-supply/search?q={search_string}&page={page}#')
                sleep(1)
                self._add_logtime(f'driver.get offer')

                tables = self.driver.find_elements(By.CSS_SELECTOR, 'a[name="invertoryReadyToShip"]')
                self._add_logtime(f'get tables')
                if not tables:
                    break

                hrefs = []
                for table in tables:
                    self.start_time = datetime.now()

                    element = table.find_element(By.XPATH, '..') # Переход к родительскому элементу
                    element = element.find_element(By.XPATH, '..')
                    if 'productLineItem' not in element.get_attribute('class'):
                        element = element.find_element(By.XPATH, '..')
                    href = element.find_elements(By.CSS_SELECTOR, 'a.productMainLink')
                    self._add_logtime(f'get href')
                    if href and href[0].text in self.items:
                        try:
                            found_href = href[0].get_attribute('href')
                        except exceptions.WebDriverException as e:
                            logger.error('[Aviall][Error] Href not found')
                            continue
                        hrefs.append(found_href)
                        self._add_logtime(f'found_href {found_href}')

                for href in hrefs:
                    self.start_time = datetime.now()
                    self.driver.get(href)
                    self._add_logtime(f'{href} driver.get')

                    item = self._get_item(self.driver)
                    if item not in self.items:
                        continue

                    self._add_logtime(f'{href} get part_number')

                    description = self._get_description(self.driver)
                    self._add_logtime(f'{href} get description')
                    price, price_unit = self._get_price(self.driver)
                    self._add_logtime(f'{href} get price')
                    if price is None or price_unit is None:
                        continue

                    pre_packing = self._get_pre_packing(self.driver)
                    self._add_logtime(f'{href} get pre_packing')

                    condition = self._get_condition(self.driver)
                    self._add_logtime(f'{href} get condition')
                    if condition is None:
                        condition = 'NE'

                    offer_country_quantity = self._get_country_quantity(self.driver, item)
                    self._add_logtime(f'{href} get offer_country | quantity')
                    if offer_country_quantity is None:
                        continue

                    for offer_country, quantity in offer_country_quantity.items():
                        row_offer = Offer(
                            inventory=item,
                            offer_description=description,
                            condition=condition,
                            quantity=quantity,
                            offer_country=offer_country,
                            price=price,
                            price_unit=price_unit,
                            int_leadtime_start=0,
                            int_leadtime_end=0,
                            certificate=None,
                            company='AVIALL',
                            commit_date_unix=None,
                            aviator_purchase='LM',
                            to_buy=True,
                            sale_type='SALE',
                            pre_packing=pre_packing
                        )

                        offers.append(row_offer)
                page += 1

            logger.info('\n'.join(self.logger_time))
        except SoftTimeLimitExceeded as e:
            logger.info('\n'.join(self.logger_time))
            raise e
        return offers

    def _get_item(self, row) -> str | None:
        """
        Получение парт номера квоты
        :param row: Строка для поиска данных
        :return: Парт номера
        """
        row_item = row.find_elements(
            By.CSS_SELECTOR,
            'div[style="margin-right: 15px;display: inline-block;"]'
        )
        if row_item:
            item = row_item[0].find_elements(
                By.TAG_NAME,
                'strong'
            )
            if item:
                return item[0].text.strip().upper().split('=')[0]

    def _get_country_quantity(self, raw_item, part_number: str) -> dict | None:
        """
        Получение страны нахождения квоты
        :param raw_item: Строка для поиска данных
        :param part_number: Парт-номер квоты
        :return: Словарь со странами и количеством доступных для заказа
        """
        countries = {}
        countries_backorder = []
        availability = raw_item.find_elements(By.CSS_SELECTOR, 'a[name="invertoryReadyToShip"]')
        if availability:
            raw_item.execute_script('arguments[0].click();', availability[0])
            locations = raw_item.find_elements(By.CSS_SELECTOR, 'table.aviall-stock-data')
            if locations:
                locations_rows = locations[0].find_elements(By.TAG_NAME, 'tr')
                for loc in locations_rows:
                    l = loc.find_elements(By.TAG_NAME, 'td')
                    if len(l) >= 2:
                        raw_offer_location = l[0].text
                        country = self._get_country(raw_offer_location, part_number)
                        raw_quantity = l[1].text
                        quantity = self.extract_number(raw_quantity)
                        if quantity is not None:
                            if country not in countries:
                                countries[country] = int(quantity)
                            else:
                                countries[country] += int(quantity)
                        else:
                            countries_backorder.append(country)
        if countries:
            return countries
        else:
            if countries_backorder:
                return {i: 1 for i in countries_backorder}
            else:
                return None

    def _get_country(self, raw_country: str, part_number: str):
        """
        Получение страны нахождения квоты
        :param raw_country: Строка с названием страны
        :return: Страна
        """
        raw_country = raw_country.upper()
        return raw_country

    def _get_condition(self, row) -> str | None:
        """
        Получение состояния квоты
        :param row: Строка для поиска данных
        :return: Состояние объекта квоты
        """
        raw_condition = row.find_elements(
            By.XPATH,
            '/html/body/div[10]/div[3]/div[8]/div[3]/div[1]/div[1]/div/table/tbody/tr[3]/td[2]/div/div[2]'
        )
        if raw_condition:
            condition = raw_condition[0].text.split('&')[0].lower().replace(' ', '')
            if condition and condition in FULL_CONDITION_NAME:
                return FULL_CONDITION_NAME[condition]
            logger.error('[Aviall][ERROR] Not find condition: ' + condition)
        return None

    def _get_quantity(self, row) -> int | None:
        """
        Получение количества доступных объектов для квоты
        :param row: Строка для поиска данных
        :return: Количество объектов
        """
        raw_quantity = row.find_elements(
            By.XPATH,
            '/html/body/div[10]/div[3]/div[8]/div[3]/div[1]/table/tbody/tr[2]/td[2]/table/tbody/tr/td/div[2]/div/'
            'form/div[2]/div[2]/div[1]'
        )
        if raw_quantity:
            quantity = raw_quantity[0].text.strip().replace(',', '')
            if quantity and quantity.isdigit():
                return int(quantity)
        return None

    def _get_description(self, row) -> str:
        """
        Получение описания квоты
        :param row: Строка для поиска данных
        :return: Описание квоты
        """
        description = row.find_elements(
            By.XPATH,
            '/html/body/div[10]/div[3]/div[8]/div[3]/div[1]/table/tbody/tr[1]/td/div/table/tbody/tr/td[1]/h1'
        )
        if description:
            return description[0].text or ''
        return ''

    def _get_price(self, row) -> tuple[float | None, str | None]:
        """
        Получение цены и валюты по квоте
        :param row: Строка для поиска данных
        :return: Цена и валюта
        """
        raw_price = row.find_elements(
            By.CSS_SELECTOR,
            'span#prodNetPrice'
        )
        if raw_price:
            raw_price = raw_price[0]
            item_price = raw_price.text

            price = self.extract_number(item_price)

            if price and len(item_price) >= 2:
                price_unit = item_price[0]
            else:
                if not price:
                    price = None
                price_unit = 'USD'

            return price, price_unit
        return None, None

    def _get_pre_packing(self, row) -> str | None:
        """
        Получение цены и валюты по квоте
        :param row: Строка для поиска данных
        :return: Цена и валюта
        """
        pre_packing = row.find_elements(
            By.XPATH,
            '/html/body/div[10]/div[3]/div[8]/div[3]/div[1]/table/tbody/tr[1]/td/div/table/tbody/tr/td[2]/div/div'
        )
        if pre_packing:
            pre_packing = pre_packing[0].text.upper()
            if 'KIT' in pre_packing:
                return 'KIT'
        return 'EA'

    def _log_in(self):
        """
        Аутентификация на сайте
        :return: None
        """
        self.driver.get('https://shop.boeing.com/aviation-supply/login')

        self._add_logtime('_log_in driver.get')

        sleep(2)
        login = self.driver.find_element(
            By.CSS_SELECTOR,
            'input#j_username'
        )

        login.send_keys(settings.AVIALL_SETTINGS.USER_NAME)

        self._add_logtime('_log_in find login')

        validate_button = self.driver.find_element(
            By.CSS_SELECTOR,
            'div#validateUsername'
        )
        self.driver.execute_script('arguments[0].click();', validate_button)
        self._add_logtime('_log_in validate_button')

        password = self.driver.find_element(
            By.CSS_SELECTOR,
            'input#loginpassword'
        )
        password.send_keys(settings.AVIALL_SETTINGS.PASSWORD)
        self._add_logtime('_log_in password')

        login_button = self.driver.find_element(
            By.CSS_SELECTOR,
            'button#submitbtn'
        )
        self.driver.execute_script('arguments[0].click();', login_button)
        self._add_logtime('_log_in login_button')
        sleep(1)

    def _add_logtime(self, msg: str):
        self.logger_time.append('%s time=%s' % (msg, datetime.now() - self.start_time))
        self.start_time = datetime.now()


class GetOfferBDSI(GetOfferCommon):
    """
    Получение квот с https://www.boeingdistribution.com/
    """
    raw_offers = list()
    logger_time = list()
    start_time = datetime

    def __init__(self, items: list[str], driver: webdriver):
        self.items = items
        self.driver = driver
        self.logger_time = []

    def get_offers(self, retries: int = 0, full_login: bool = False) -> list[Offer]:
        """
        Основная функция для получения квот
        :param retries: Количество попыток выполнения функции
        :param full_login: Необходимость полного логина
        :return: Список квот
        """
        try:
            if retries >= 5:
                logger.error('[BDSI][Error] Too many tries to login')
                return []

            self._set_cookies(full_login=full_login)
            account_name = self.driver.find_elements(By.CSS_SELECTOR, 'span.txt-upr')
            if not account_name:
                return self.get_offers(retries + 1, True)

            self.start_time = datetime.now()
            offers = []
            search_area = self.driver.find_element(By.CSS_SELECTOR, 'textarea#searchInput')
            search_area.clear()
            sleep(1)
            search_area.send_keys('\n'.join(self.items))
            self._add_logtime('search_area')

            search_button = self.driver.find_element(By.CSS_SELECTOR, 'button#boxSearch')
            self.driver.execute_script('arguments[0].click();', search_button)
            sleep(2)
            self._add_logtime('search_button')

            tabs = self.driver.find_elements(By.CSS_SELECTOR, 'tr.datar')
            self._add_logtime('find tabs')

            for tab in tabs:
                self.start_time = datetime.now()
                item = self._get_item(tab)
                if item is None:
                    continue

                quantity = self._get_quantity(tab)
                self._add_logtime('find quantity')
                if quantity is None:
                    continue

                price, price_unit = self._get_price(self.driver)
                self._add_logtime('find price')
                if price is None or price_unit is None:
                    continue

                description = self._get_description(tab)
                self._add_logtime('find description')

                row_offer = Offer(
                    inventory=item,
                    offer_description=description,
                    condition='NE',
                    quantity=quantity,
                    offer_country='UNITED STATES',
                    price=price,
                    price_unit=price_unit,
                    int_leadtime_start=0,
                    int_leadtime_end=0,
                    certificate=None,
                    company='BOEING DISTRIBUTION SERVICES',
                    commit_date_unix=None,
                    aviator_purchase='LM',
                    to_buy=True,
                    sale_type='SALE',
                )

                offers.append(row_offer)

            logger.info('\n'.join(self.logger_time))
        except SoftTimeLimitExceeded as e:
            self.logger_time.append('timelimit exceeded')
            logger.info('\n'.join(self.logger_time))
            raise e
        return offers

    def _get_quantity(self, row) -> int | None:
        """
        Получение количества доступных объектов для квоты
        :param row: Строка для поиска данных
        :return: Количество объектов
        """
        raw_quantity = row.find_elements(
            By.CSS_SELECTOR,
            'td[data-val="availQuantity"]'
        )
        if raw_quantity:
            quantity = raw_quantity[0].text.strip().replace(',', '')
            if quantity and quantity.isdigit():
                return int(quantity)
        return None

    def _get_description(self, row) -> str:
        """
        Получение описания квоты
        :param row: Строка для поиска данных
        :return: Описание квоты
        """
        description = row.find_element(
            By.CSS_SELECTOR,
            'td[data-val="description"]'
        ).text
        return description or ''

    def _get_item(self, row) -> str | None:
        """
        Получение парт номера квоты
        :param row: Строка для поиска данных
        :return: Парт номера
        """
        item = None
        tries = 0
        while item is None and tries < 5:
            try:
                item = row.get_attribute('primenumber')
                tries += 1
            except StaleElementReferenceException as e:
                if tries == 4:
                    return None
                item = None
                tries += 1
                sleep(1)
        if item in self.items:
            return item

    def _get_price(self, row) -> tuple[float | None, str | None]:
        """
        Получение цены и валюты по квоте
        :param row: Строка для поиска данных
        :return: Цена и валюта
        """
        raw_price = row.find_elements(
            By.CSS_SELECTOR,
            'td[data-val="unitPrice"]'
        )
        if raw_price:
            raw_price = raw_price[0]
            item_price = raw_price.text

            price = self.extract_number(item_price)

            if price and len(item_price) >= 2:
                price_unit = item_price[0]
            else:
                if not price:
                    price = None
                price_unit = 'USD'

            return price, price_unit
        return None, None

    def _set_cookies(self, tries: int = 0, full_login: bool = False):
        """
        Использование ранее полученных куки для получения доступа к сайту
        :param tries: Количество попыток получения/установки куки
        :param full_login: Необходимость обновления куки
        :return: None
        """
        if tries >= 5:
            raise Exception('[BDSI] Too many tries to login')

        self.start_time = datetime.now()
        self.driver.get('https://www.boeingdistribution.com/')
        self._add_logtime(f'_set_cookies {tries} driver.get')
        sleep(1)

        cookies = pd.read_csv('media/cookies.csv', delimiter=';')
        bdsi_cookies = cookies.loc[cookies['site'] == 'BDSI']

        jsessionid_cookie = bdsi_cookies.value1.values[0]
        self._add_logtime(f'_set_cookies {tries} redis')

        if jsessionid_cookie and jsessionid_cookie != 'q' and not full_login:
            cookies = {
                'JSESSIONID': jsessionid_cookie,
            }
            for key, value in cookies.items():
                self.driver.add_cookie({'name': key, 'value': value})
            self._add_logtime(f'_set_cookies {tries} add_cookie')
            self.driver.refresh()
            self._add_logtime(f'_set_cookies {tries} driver.refresh')
        else:
            self._log_in()
            self._set_cookies(tries + 1)

    def _log_in(self):
        """
        Аутентификация на сайте
        :return: None
        """
        self.start_time = datetime.now()
        login_tab = self.driver.find_element(
            By.CSS_SELECTOR,
            'span.login-or-register'
        )
        self.driver.execute_script('arguments[0].click();', login_tab)

        self._add_logtime(f'_log_in login_tab')

        login = self.driver.find_element(
            By.CSS_SELECTOR,
            'input#user-name'
        )
        login.send_keys(settings.BDSI_SETTINGS.USER_NAME)
        sleep(0.5)
        self._add_logtime(f'_log_in login')

        continue_login = self.driver.find_element(
            By.CSS_SELECTOR,
            'button#check-user-login'
        )
        self.driver.execute_script('arguments[0].click();', continue_login)
        self._add_logtime(f'_log_in continue_login')
        password = WebDriverWait(self.driver, 30).until(ec.visibility_of_element_located((By.CSS_SELECTOR,
            'input#c-password')))
        password.send_keys(settings.BDSI_SETTINGS.PASSWORD)
        sleep(0.5)
        self._add_logtime(f'_log_in password')
        login_in_popup = self.driver.find_element(
            By.CSS_SELECTOR,
            'button#logInPopup'
        )
        self.driver.execute_script('arguments[0].click();', login_in_popup)
        sleep(2)
        self._add_logtime(f'_log_in login_in_popup')

        activate_session = self.driver.find_elements(By.CSS_SELECTOR, 'button#activateSession')
        if activate_session:
            self.driver.execute_script('arguments[0].click();', activate_session[0])
            self._add_logtime(f'_log_in activate_session')

        jsessionid_cookie = self.driver.get_cookie('JSESSIONID')

        cookies = pd.read_csv('media/cookies.csv', delimiter=';')
        cookies.loc[cookies['site'] == 'BDSI', 'value1'] = jsessionid_cookie['value']
        cookies.to_csv('media/cookies.csv', index=False, sep=';')
        self._add_logtime(f'_log_in redis set jsessionid_cookie')

    def _add_logtime(self, msg: str):
        self.logger_time.append('%s time=%s' % (msg, datetime.now() - self.start_time))
        self.start_time = datetime.now()
