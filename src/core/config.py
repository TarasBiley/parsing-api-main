import logging
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

from logging import config as logging_config
from core.logger import LOGGING

BASE_DIR = Path(__file__).resolve().parent.parent.parent

logging_config.dictConfig(LOGGING)

load_dotenv(f'{BASE_DIR}/.env')


class AviatorSettings(BaseSettings):
    AUTHORISATION_TOKEN: str | None = Field(default_factory=lambda: '')
    USER_NAME: str = Field(validation_alias='AVIATOR_USER_NAME')
    PASSWORD: str = Field(validation_alias='AVIATOR_PASSWORD')
    CODE: str | None = Field(validation_alias='AVIATOR_CODE', default_factory=lambda: '')


class AerobaySettings(BaseSettings):
    JSESSIONID: str | None = Field(default_factory=lambda: '')
    USER_NAME: str | None = Field(validation_alias='AEROBAY_USER_NAME', default_factory=lambda: '')
    PASSWORD: str | None = Field(validation_alias='AEROBAY_PASSWORD', default_factory=lambda: '')


class AviosupportSettings(BaseSettings):
    USER_NAME: str | None = Field(validation_alias='AVIOSUPPORT_USER_NAME', default_factory=lambda: '')
    PASSWORD: str | None = Field(validation_alias='AVIOSUPPORT_PASSWORD', default_factory=lambda: '')


class EcsatSettings(BaseSettings):
    USER_NAME: str | None = Field(validation_alias='ECSAT_USER_NAME', default_factory=lambda: '')
    PASSWORD: str | None = Field(validation_alias='ECSAT_PASSWORD', default_factory=lambda: '')


class DASICookiesSettings(BaseSettings):
    ASPXANONYMOUS: str | None = Field(default_factory=lambda: '')
    ASP_NET_SessionId: str | None = Field(default_factory=lambda: '')
    DASI_CustomerSessionGUIDCookie: str | None = Field(default_factory=lambda: '')
    NOPCOMMERCE_AUTH: str | None = Field(default_factory=lambda: '')


class DASISettings(BaseSettings):
    USER_NAME: str | None = Field(validation_alias='DASI_USER_NAME', default_factory=lambda: '')
    PASSWORD: str | None = Field(validation_alias='DASI_PASSWORD', default_factory=lambda: '')
    # COOKIES: DASICookiesSettings = DASICookiesSettings()  # Cookies saved in Redis


class ProponentSettings(BaseSettings):
    USER_NAME: str | None = Field(validation_alias='PROPONENT_USER_NAME', default_factory=lambda: '')
    PASSWORD: str | None = Field(validation_alias='PROPONENT_PASSWORD', default_factory=lambda: '')


class SatairSettings(BaseSettings):
    USER_NAME: str | None = Field(validation_alias='SATAIR_USER_NAME', default_factory=lambda: '')
    PASSWORD: str | None = Field(validation_alias='SATAIR_PASSWORD', default_factory=lambda: '')


class WencorSettings(BaseSettings):
    USER_NAME: str | None = Field(validation_alias='WENCOR_USER_NAME', default_factory=lambda: '')
    PASSWORD: str | None = Field(validation_alias='WENCOR_PASSWORD', default_factory=lambda: '')


class AviallSettings(BaseSettings):
    USER_NAME: str | None = Field(validation_alias='AVIALL_USER_NAME', default_factory=lambda: '')
    PASSWORD: str | None = Field(validation_alias='AVIALL_PASSWORD', default_factory=lambda: '')


class BDSISettings(BaseSettings):
    USER_NAME: str | None = Field(validation_alias='BDSI_USER_NAME', default_factory=lambda: '')
    PASSWORD: str | None = Field(validation_alias='BDSI_PASSWORD', default_factory=lambda: '')


class RedisSettings(BaseSettings):
    HOST: str = Field(validation_alias='REDIS_HOST', default='localhost')
    PORT: int = Field(validation_alias='REDIS_PORT', default=6379)


class Settings(BaseSettings):
    LOG_LEVEL: int | str = Field(default=logging.INFO)
    MAIN_SERVER: str = Field(default='')
    REDIS: str | None = Field(default='redis://localhost:6379')
    AIRPORTS: str | None = Field(default='parsers/airports.json')
    TELEGRAM_TOKEN: str | None = Field(default='')
    CHAT_ID: str | None = Field(default='')
    TAGGED_TELEGRAM_ACCS: str | None = Field(default='')
    REDIS_SETTINGS: RedisSettings = RedisSettings()
    AVIATOR_SETTINGS: AviatorSettings = AviatorSettings()
    AEROBAY_SETTINGS: AerobaySettings = AerobaySettings()
    AVIOSUPPORT_SETTINGS: AviosupportSettings = AviosupportSettings()
    ECSAT_SETTINGS: EcsatSettings = EcsatSettings()
    DASI_SETTINGS: DASISettings = DASISettings()
    PROPONENT_SETTINGS: ProponentSettings = ProponentSettings()
    SATAIR_SETTINGS: SatairSettings = SatairSettings()
    WENCOR_SETTINGS: WencorSettings = WencorSettings()
    AVIALL_SETTINGS: AviallSettings = AviallSettings()
    BDSI_SETTINGS: BDSISettings = BDSISettings()


settings = Settings()
