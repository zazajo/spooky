# pages/context_processors.py
from django.conf import settings

def paystack_keys(request):
    return {
        'PAYSTACK_PUBLIC_KEY': settings.PAYSTACK_PUBLIC_KEY,
        'PAYSTACK_SECRET_KEY': settings.PAYSTACK_SECRET_KEY
    }