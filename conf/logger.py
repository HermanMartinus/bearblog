from django.http import HttpResponse
from django.contrib.admin.views.decorators import staff_member_required

import time


@staff_member_required
def logger_test(request):
    x = 100/0


@staff_member_required
def timout_test(request):
    time.sleep(31)
    return HttpResponse("You're at the timeout test.")


