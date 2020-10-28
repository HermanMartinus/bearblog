from django.conf import settings
from django.contrib.auth import get_user_model
from django.dispatch import receiver
from django.utils import timezone
from paypal.standard.ipn.signals import valid_ipn_received
from paypal.standard.models import ST_PP_COMPLETED

from blogs.models import Blog


@receiver(valid_ipn_received)
def payment(sender, **kwargs):
    ipn_obj = sender
    print('Payment notification received')
    if ipn_obj.payment_status == ST_PP_COMPLETED:
        blog = Blog.objects.get(pk=int(ipn_obj.custom))
        blog.upgraded = True
        blog.save()
        print(f'Payment success for {blog.subdomain}')
