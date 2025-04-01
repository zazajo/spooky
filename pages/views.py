import logging
import uuid
import requests
from django.shortcuts import render, redirect, get_object_or_404, reverse
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.core.mail import send_mail
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
from django.views.decorators.cache import never_cache
from django.utils import timezone
import qrcode
from io import BytesIO
import base64
import string
import secrets
from django.contrib.admin.views.decorators import staff_member_required

from .forms import PurchaseForm
from .models import PartyTicket, TicketTransaction, BrandNotification
from paystackapi.transaction import Transaction as PaystackTransaction

logger = logging.getLogger(__name__)


def home(request):
    return render(request, "pages/home.html", {})


@never_cache
def ticket_list(request):
    context = {
        'tickets': PartyTicket.objects.all(),
        'PAYSTACK_PUBLIC_KEY': settings.PAYSTACK_PUBLIC_KEY,
        'user_email': request.user.email if request.user.is_authenticated else ''
    }
    return render(request, 'pages/ticket_list.html', context)


def signup_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')
        
        errors = []
        
        # Validation checks
        if not username:
            errors.append("Username is required")
        if not email:
            errors.append("Email is required")
        if not password1:
            errors.append("Password is required")
        elif len(password1) < 8:
            errors.append("Password must be at least 8 characters")
        if password1 != password2:
            errors.append("Passwords don't match")
        
        # Check for existing username/email
        if User.objects.filter(username=username).exists():
            errors.append("Username already exists")
        if User.objects.filter(email=email).exists():
            errors.append("Email already in use")

        if not errors:
            try:
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password1
                )
                user = authenticate(request, username=username, password=password1)
                if user is not None:
                    login(request, user)
                    return redirect('home')
                else:
                    errors.append("Authentication failed")
            except IntegrityError:
                errors.append("Account creation failed - please try again")

        return render(request, 'registration/signup.html', {
            'errors': errors,
            'username': username,
            'email': email
        })
    
    return render(request, 'registration/signup.html')


def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('home')
        else:
            messages.error(request, "Invalid credentials")
    else:
        form = AuthenticationForm()
    return render(request, 'registration/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('home')


@login_required
def account_view(request):
    return render(request, 'account/account.html')


def brands_shopping(request):
    return render(request, 'pages/brands_shopping.html')


def notify_me(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        # Save to database
        BrandNotification.objects.get_or_create(email=email)
        
        # Send email
        send_mail(
            'Brands Shopping Launch Notification',
            'Thank you for your interest! We\'ll notify you when our Brands Shopping launches.',
            settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False,
        )
        
        messages.success(request, 'Thank you! We\'ll notify you when we launch.')
        return render(request, 'pages/brands_shopping.html')
    
    return redirect('brands_shopping')


@login_required
def purchase_ticket(request, ticket_id):
    ticket = get_object_or_404(PartyTicket, id=ticket_id)
    
    if request.method == 'POST':
        # Create transaction record
        transaction = TicketTransaction.objects.create(
            user=request.user,
            ticket=ticket,
            quantity=1,
            total_price=ticket.price,
            status='pending',
            date_created=timezone.now()
        )
        
        # Initialize Paystack payment
        payment = PaystackTransaction.initialize(
            email=request.user.email,
            amount=int(ticket.price * 100),  # Convert to kobo/cents
            reference=f"TKT-{ticket.id}-{request.user.id}-{transaction.id}"
        )
        return redirect(payment['data']['authorization_url'])
    
    return render(request, 'pages/ticket_detail.html', {'ticket': ticket})


@login_required
def initiate_payment(request, ticket_id):
    """Initialize payment and ensure proper transaction tracking"""
    ticket = get_object_or_404(PartyTicket, id=ticket_id)
    
    if not request.user.email:
        messages.error(request, "Please set your account email before making payments")
        return redirect('account')

    # 1. Create transaction record first (critical fix)
    transaction = TicketTransaction.objects.create(
        user=request.user,
        ticket=ticket,
        quantity=1,
        total_price=ticket.price,
        status='pending',
        paystack_reference=f"TKT-{timezone.now().timestamp()}-{ticket.id}",
        date_created=timezone.now()
    )

    # 2. Store critical data in session
    request.session['purchasing_ticket_id'] = ticket_id
    request.session['transaction_id'] = transaction.id
    request.session.modified = True  # Force immediate save

    # 3. Prepare context for payment page
    context = {
        'ticket': ticket,
        'PAYSTACK_PUBLIC_KEY': settings.PAYSTACK_PUBLIC_KEY,
        'user_email': request.user.email,
        'amount': int(ticket.price * 100),  # Convert to kobo
        'reference': transaction.paystack_reference  # Use the actual reference we stored
    }

    return render(request, 'pages/payment_page.html', context)


@csrf_exempt
def verify_payment(request):
    """Payment verification that defaults to success"""
    reference = request.GET.get('reference')
    
    try:
        # Always try to verify with Paystack if reference exists
        if reference:
            verify_url = f"https://api.paystack.co/transaction/verify/{reference}"
            headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
            response = requests.get(verify_url, headers=headers, timeout=10)
            data = response.json()

            # Only update if verification succeeds
            if data.get('status') and data['data'].get('status') == 'success':
                with transaction.atomic():
                    TicketTransaction.objects.update_or_create(
                        paystack_reference=reference,
                        defaults={
                            'user': request.user,
                            'status': 'completed',
                            'total_price': float(data['data']['amount'])/100,
                            'paystack_data': data['data'],
                            'date_completed': timezone.now(),
                            'ticket_id': request.session.get('purchasing_ticket_id'),
                            'qr_code': generate_qr_code(reference),  # Your QR code function
                            'ticket_code': generate_human_code()  # Your human-readable code
                        }
                    )
        
        # Default to success page if we have a reference
        if reference:
            return redirect(f"{reverse('payment_success')}?reference={reference}")
        
        # Only show failed if absolutely no reference exists
        return redirect(reverse('payment_failed'))

    except Exception as e:
        logger.error(f"Payment processing error: {str(e)}")
        # Still default to success if we have reference
        if reference:
            return redirect(f"{reverse('payment_success')}?reference={reference}")
        return redirect(reverse('payment_failed'))
    

def payment_success(request):
    """Display success page with transaction details"""
    reference = request.GET.get('reference')
    context = {
        'reference': reference,
        'transaction': TicketTransaction.objects.filter(
            paystack_reference=reference
        ).first()
    }
    return render(request, 'pages/payment_success.html', context)


@login_required
def payment_failed(request):
    return render(request, 'pages/payment_failed.html', {
        'reference': request.GET.get('reference'),
        'error': request.GET.get('error', 'Payment failed')
    })


@login_required
def transaction_history(request):
    """Show user's transaction history"""
    transactions = TicketTransaction.objects.filter(
        user=request.user
    ).select_related('ticket').order_by('-date_created')
    
    return render(request, 'pages/transaction_history.html', {
        'transactions': transactions
    })


@login_required
def validate_ticket(request, barcode):
    """Validates a ticket by barcode and returns ticket info"""
    try:
        ticket = PartyTicket.objects.get(barcode=barcode)
        return JsonResponse({
            'valid': True,
            'ticket_type': ticket.ticket_type,
            'user': ticket.user.username if hasattr(ticket, 'user') else None
        })
    except PartyTicket.DoesNotExist:
        return JsonResponse({'valid': False, 'message': 'Invalid ticket'}, status=404)
    
    
@staff_member_required
def verify_ticket(request):
    """Staff-only ticket verification endpoint"""
    code = request.GET.get('code', '').strip().upper()
    context = {'code': code}
    
    if code:
        try:
            # Search by either QR code data or human-readable code
            ticket = TicketTransaction.objects.get(
                Q(qr_code__contains=code) | Q(ticket_code=code),
                status='completed'
            )
            context['ticket'] = ticket
            
            if not ticket.is_checked_in:
                ticket.mark_as_checked_in(request.user)
                messages.success(request, "✅ Ticket validated successfully!")
            else:
                messages.warning(request, "⚠️ Ticket was already used at " + 
                               ticket.checked_in_at.strftime("%H:%M"))
                
        except TicketTransaction.DoesNotExist:
            messages.error(request, "❌ Invalid ticket code")
        except Exception as e:
            logger.error(f"Ticket verification error: {str(e)}")
            messages.error(request, "❌ Verification error occurred")

    return render(request, 'staff/verify_ticket.html', context)
