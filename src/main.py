from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from redis.asyncio import Redis

from api.v1 import offers
from core.config import settings
from core.logger import LOGGING
from db import redis


@asynccontextmanager
async def lifespan(app: FastAPI):

    redis.redis = Redis(host=settings.REDIS_SETTINGS.HOST, port=settings.REDIS_SETTINGS.PORT)

    yield

    await redis.redis.close()


app = FastAPI(
    title='Парсер информации с сайтов',
    docs_url='/api/openapi',
    openapi_url='/api/openapi.json',
    default_response_class=ORJSONResponse,
    version="0.0.1",
    lifespan=lifespan
)

Instrumentator().instrument(app).expose(app)


app.include_router(offers.router, prefix='/api/v1/orders', tags=['orders'])


if __name__ == '__main__':
    uvicorn.run(
        'main:app',
        host='0.0.0.0',
        port=8000,
        log_config=LOGGING,
        log_level=settings.LOG_LEVEL
    )
