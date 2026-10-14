import csv
import datetime
import logging
import os
import random
from time import sleep

import openpyxl
import pandas as pd
from bs4 import BeautifulSoup

from curl_cffi import requests
from selenium import webdriver
from selenium.common import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

LOCAL_CHROMEDRIVER = True
PATH_TO_LOCAL_CHROMEDRIVER = 'chromedriver'

NOT_PARSE = [
    'Air Dusters',
    'Cloths & Wipes',
    'Cotton Swabs',
    'De-Ice Fluid',
    'Deodorizers',
    'Detailing Clay',
    'Dry-Wash',
    'Emergency & Safety',
    'FBO & Ground Support',
    'Gifts & Toys',
    'Hand Cleaner',
    'Hand Soap',
    'Hand Towels',
    'Markers',
    'Oil Absorbent',
    'Pilot Supplies',
    'Plastic Cleaner',
    'Refrigerants',
    'Shipping Boxes',
    'Shop Towels',
    'Upholstery Cleaner',
]

logger = logging.getLogger(__name__)


class SkyGeekScraper:
    """
    Получение информации с SkyGeek.
    """
    fields = ['href', 'category', 'processed', 'page', 'get_all_items', 'row']
    def __init__(self):
        if not os.path.exists('media/categories.csv'):
            self.section_hrefs()
        self.item_hrefs()
        self.get_offers()
        self.csv_to_excel()
        self.cleen_directory()

    def section_hrefs(self):
        """
        Получение и запись urls для категорий
        :return:
        """

        with requests.Session() as session:
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
                              'Chrome/51.0.2704.106 Safari/537.36 OPR/38.0.2220.41'
            })
            response = session.get('https://skygeek.com/shop-hangar-supplies/')
            html_page = BeautifulSoup(response.text, 'html.parser')
            categories = html_page.find_all(
                'div',
                {
                    'class': 'category__subcat-grid-item',
                }
            )

        categories_to_parse = []
        for category in categories:
            if category.text.replace('\n', '') not in NOT_PARSE:
                categories_to_parse.append(category)

        if not os.path.isdir('media'):
            os.mkdir('media')

        with open('media/categories.csv', 'w', newline='') as f:
            csv_writer = csv.writer(f, delimiter=';', quotechar='|')
            csv_writer.writerow(self.fields)
            for category in categories_to_parse:
                href = category.find_next('a').attrs['href']
                csv_writer.writerow([href, 'media/' + href.split('/')[-2] + '.csv', False, 1, False, 0])

    def item_hrefs(self):
        """
        Получение и запись urls для объектов
        :return:
        """
        categories_file = pd.read_csv('media/categories.csv', delimiter=';')

        if LOCAL_CHROMEDRIVER:
            service = Service(PATH_TO_LOCAL_CHROMEDRIVER)
        else:
            service = None
        with webdriver.Chrome(options=self.driver_options(), service=service) as driver:
            driver.implicitly_wait(3)
            for row in categories_file.itertuples():
                start = datetime.datetime.now()
                if not row.processed:
                    with open(row.category, 'a', newline='') as hrefs_file:
                        writer = csv.writer(hrefs_file, delimiter=';', quotechar='|')
                        page = row.page
                        while page < 100:
                            start_get_page_time = datetime.datetime.now()
                            href_page = row.href + f'?p={page}#/perpage:100/sort:name:asc'
                            logger.info(href_page)
                            driver.get(href_page)
                            sleep(1)
                            items = driver.find_elements(By.CSS_SELECTOR, 'figure.card-figure')
                            hrefs_on_page = []
                            if items:
                                for item in items:
                                    item_tag_with_href = item.find_element(By.TAG_NAME, 'a')
                                    href = item_tag_with_href.get_attribute('href')
                                    hrefs_on_page.append(href)
                            else:
                                categories_file.loc[categories_file['href'] == row.href, 'processed'] = True
                                categories_file.to_csv('media/categories.csv', index=False, sep=';')
                                break
                            for href in hrefs_on_page:
                                writer.writerow([href])
                            page += 1
                            categories_file.loc[categories_file['href'] == row.href, 'page'] = page
                            categories_file.to_csv('media/categories.csv', index=False, sep=';')
                            logger.info('time to get page: ', datetime.datetime.now() - start_get_page_time)
                            sleep(random.randint(1, 4))
                logger.info(datetime.datetime.now() - start)

    def get_offers(self):
        """
        Обработка и добавление новых записей в media/items.csv
        """
        if not os.path.exists('media/items.csv'):
            with open('media/items.csv', 'w', newline='') as csvfile:
                csvwriter = csv.writer(csvfile, delimiter=';', quotechar='|')
                csvwriter.writerow(['Part Number'])
        categories_file = pd.read_csv('media/categories.csv', delimiter=';', quotechar='|')

        if LOCAL_CHROMEDRIVER:
            service = Service(PATH_TO_LOCAL_CHROMEDRIVER)
        else:
            service = None
        with webdriver.Chrome(options=self.driver_options(), service=service) as driver:
            driver.implicitly_wait(1)

            for category in categories_file.itertuples():
                if category.get_all_items:
                    continue
                row = category.row
                item_hrefs_df = pd.read_csv(category.category, delimiter=';', quotechar='|', header=None)
                item_hrefs_slice = item_hrefs_df.iloc[row:]
                for item_href in item_hrefs_slice.itertuples():
                    start = datetime.datetime.now()
                    logger.info(item_href[1])
                    try:
                        driver.get(item_href[1])
                    except TimeoutException:
                        driver.get(item_href[1])
                    attrs = {}
                    attrs['Part Number'] = [self._get_item(driver)]
                    if not attrs['Part Number'][0]:
                        row += 1
                        continue
                    attrs['Manufacture Part'] = [self._get_manufacture_part(driver)]
                    un_details = driver.find_elements(By.CSS_SELECTOR, 'div.un-details')
                    if un_details:
                        attrs['un number'] = [self._get_un_number(un_details[0])]
                        attrs['un class'] = [self._get_un_class(un_details[0])]
                    attributes = self._get_attributes(driver)
                    if attributes:
                        attrs.update(attributes)
                    approvals_and_conformities = self._get_approvals_and_conformities(driver)
                    if approvals_and_conformities:
                        attrs.update(approvals_and_conformities)
                    if 'Size' in attrs and '"' in attrs['Size'][0]:
                        attrs['Size'] = [attrs['Size'][0].replace('"', 'in')]
                    new_line = pd.DataFrame(attrs)
                    df = pd.read_csv('media/items.csv', delimiter=';', low_memory=False)
                    d = pd.concat([df, new_line], ignore_index=True, )
                    d.to_csv('media/items.csv', sep=';', index=False, na_rep='')

                    row += 1
                    categories_file.loc[categories_file['category'] == category.category, 'row'] = row
                    categories_file.to_csv('media/categories.csv', index=False, sep=';')
                    logger.info(datetime.datetime.now() - start)
                    sleep(random.randint(5, 15))
                else:
                    categories_file.loc[categories_file['category'] == category.category, 'get_all_items'] = True
                    categories_file.to_csv('media/categories.csv', index=False, sep=';')

    def csv_to_excel(self):
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

    def cleen_directory(self):
        categories_file = pd.read_csv('media/categories.csv', delimiter=';')
        for row in categories_file.itertuples():
            try:
                os.remove(row.category)
            except FileNotFoundError:
                continue
        os.remove('media/categories.csv')

    def _get_item(self, driver: webdriver) -> str | None:
        """
        Получение part_number записи на странице
        :param driver: вебдрайвер
        :return: part_number
        """
        item = driver.find_elements(By.CSS_SELECTOR, 'div.productView-sku')
        if item:
            return item[0].find_elements(By.CSS_SELECTOR, 'span')[1].text

    def _get_manufacture_part(self, driver: webdriver) -> str:
        """
        Получение manufacture_part записи на странице
        :param driver: вебдрайвер
        :return: manufacture_part
        """
        return driver.find_elements(By.CSS_SELECTOR, 'div.mpn-value.italic-content')[0].find_elements(By.CSS_SELECTOR, 'span')[1].text

    def _get_un_number(self, driver: webdriver) -> str | None:
        """
        Получение un_number записи на странице
        :param driver: вебдрайвер
        :return: un_number
        """
        un_number = driver.find_elements(By.CSS_SELECTOR, 'p.un_number')
        if un_number:
            return un_number[0].text.split()[2]

    def _get_un_class(self, driver: webdriver) -> str | None:
        """
        Получение un_class записи на странице
        :param driver: вебдрайвер
        :return: un_class
        """
        un_class = driver.find_elements(By.CSS_SELECTOR, 'p.un_class')
        if un_class:
            return un_class[0].text.split()[2]

    def _get_attributes(self, driver: webdriver) -> dict:
        """
        Получение атрибутов записи на странице
        :param driver: вебдрайвер
        :return:
        """
        attrs = {}
        attribute_panel = driver.find_elements(
            By.CSS_SELECTOR, 'div.its-tab__content-container[data-its-tab="product-attributes"]'
        )
        if attribute_panel:
            attributes = attribute_panel[0].find_elements(
                By.CSS_SELECTOR, 'div.ProductAttributeItem'
            )
            for attribute in attributes:
                attr_name = attribute.find_element(By.CSS_SELECTOR, 'div.ProductAttributeName').text
                attr_value = attribute.find_element(By.CSS_SELECTOR, 'div.ProductAttributeValue').text
                if attr_name:
                    attr_name = attr_name.strip()
                else:
                    continue
                if attr_value:
                    attr_value = attr_value.strip()
                else:
                    continue
                attrs[attr_name] = [attr_value]
        return attrs

    def _get_approvals_and_conformities(self, driver: webdriver) -> dict:
        """
        Получение approvals and conformities записи на странице
        :param driver: вебдрайвер
        :return:
        """
        apprs = {}
        approval_panel = driver.find_elements(
            By.CSS_SELECTOR, 'div.its-tab__content-container[data-its-tab="approvals-and-conformities"]'
        )
        if approval_panel:
            approvals = approval_panel[0].find_elements(
                By.CSS_SELECTOR, 'div.ApprovalsConformitiesItem'
            )
            for approval in approvals:
                appr_name = approval.find_element(By.CSS_SELECTOR, 'div.ApprovalsConformitiesName').text
                appr_value = approval.find_element(By.CSS_SELECTOR, 'div.ApprovalsConformitiesValue').text
                if appr_name:
                    appr_name = appr_name.strip()
                else:
                    continue
                if appr_value:
                    appr_value = appr_value.strip()
                else:
                    continue
                apprs[appr_name] = [appr_value]
        return apprs

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
            'Mozilla/5.0 (X11; CrOS x86_64 8172.45.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.64 Safari/537.36',
        ]
        random_user_agent = random.choice(user_agents)
        options.add_argument(f"--user-agent={random_user_agent}")
        return options


if __name__ == '__main__':
    logger.info('Start scraper')
    SkyGeekScraper()
