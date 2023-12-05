from django.http import JsonResponse
from NoBC.commons import Commons


def response(code=Commons.SUCCESS, msg='', data=None):
    return JsonResponse({
        'code': code,
        'msg': msg,
        'data': data
    })
