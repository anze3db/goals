from django.conf import settings  # import the settings file


def template_settings(request):
    # return the value you want as a dictionnary. you may add multiple values in there.
    return {"CLIENT_DNS": settings.CLIENT_DNS, "RELEASE": settings.RELEASE}
