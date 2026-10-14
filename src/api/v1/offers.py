import json

from starlette.requests import Request
from fastapi import APIRouter, Depends
from starlette.responses import Response

from models.offers import OffersRequest, DASIRequest, LoginTriesRequest
from services.offers import DASICookiesService, set_dasi_cookies, ResetLoginTriesService, reset_login_tries_service
from tasks.tasks import get_offers_task

router = APIRouter()


@router.post('/',
             description='Create task to parse part_numbers from sites')
async def offers(
        request: Request,
        content: OffersRequest,
):
    host = request.client.host

    context = content.context
    get_offers_task.delay(content.part_numbers, context.model_dump(), host)

    response_message = {'message': 'Start tasks'}
    response_message = json.dumps(response_message)
    return Response(response_message, media_type='application/json')


@router.post('/dasi_cookies/',
             description='Update cookies for DASI')
async def dasi_cookies(
        request: Request,
        content: DASIRequest,
        dasi_cookies: DASICookiesService = Depends(set_dasi_cookies)
):
    cookies = content.cookies.model_dump()

    message, status_code = await dasi_cookies.set_data(cookies)
    response_message = json.dumps({'message': message})

    return Response(response_message, status_code=status_code, media_type='application/json')


@router.patch('/login_tries/',
             description='Reset login tries for sites',)
async def reset_login_tries(
        request: Request,
        content: LoginTriesRequest,
        reset_login: ResetLoginTriesService = Depends(reset_login_tries_service)
):
    sites = content.model_dump()

    message, status_code = await reset_login.reset_data(sites)
    response_message = json.dumps({'message': message})

    return Response(response_message, status_code=status_code, media_type='application/json')
