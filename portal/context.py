from django.conf import settings


def deployment(request):
    return {
        "development_environment": settings.DEBUG,
        "notification_transport": settings.NOTIFICATION_TRANSPORT,
    }
