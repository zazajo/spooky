from decimal import Decimal
from reportlab.pdfgen import canvas
from django.utils.crypto import get_random_string
import json
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
from PIL import Image
from io import BytesIO
import base64
import string
import secrets
from django.contrib.admin.views.decorators import staff_member_required
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

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
    
    return render(request, 'pages/ticket_list.html', {'ticket': ticket})


@csrf_exempt
@login_required
def create_transaction(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            ticket = PartyTicket.objects.get(id=data['ticket_id'])
            quantity = int(data.get('quantity', 1))
            
            # Convert price to Decimal before multiplication
            price = Decimal(str(ticket.price))  # Ensure proper decimal conversion
            total_price = price * Decimal(quantity)
            
            transaction = TicketTransaction.objects.create(
                user=request.user,
                ticket=ticket,
                quantity=quantity,
                total_price=total_price,  # Use the calculated Decimal
                status='pending',
                paystack_reference=f"TKT-{timezone.now().timestamp()}-{uuid.uuid4().hex[:4]}"
            )
            
            return JsonResponse({
                'success': True,
                'reference': transaction.paystack_reference,
                'transaction_id': transaction.id,
                'amount': float(total_price)  # Convert to float for JavaScript
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=400)


@login_required
def initiate_payment(request, ticket_id):
    print("🔥 INITIATE PAYMENT CALLED")  # Debug 1
    ticket = get_object_or_404(PartyTicket, id=ticket_id)
    print(f"🎟️ Ticket found: {ticket.id}")  # Debug 2

    try:
        paystack_ref = f"TKT-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        print(f"📝 Creating transaction with ref: {paystack_ref}")  # Debug 3
        
        transaction = TicketTransaction.objects.create(
            user=request.user,
            ticket=ticket,
            quantity=1,
            total_price=ticket.price,
            status='pending',
            paystack_reference=paystack_ref,
            date=timezone.now()  # Explicit date for your template
        )
        print(f"✅ Transaction created! ID: {transaction.id}")  # Debug 4

        return render(request, 'pages/payment_page.html', {
            'ticket': ticket,
            'PAYSTACK_PUBLIC_KEY': settings.PAYSTACK_PUBLIC_KEY,
            'reference': paystack_ref,
            'email': request.user.email,
            'amount': int(ticket.price * 100)
        })

    except Exception as e:
        print(f"❌ Transaction creation failed: {str(e)}")  # Debug 5
        messages.error(request, "Failed to initialize payment")
        return redirect('ticket_list', ticket_id=ticket.id)


@csrf_exempt
def verify_payment(request):
    reference = request.GET.get('reference', '')
    
    try:
        # Try to get transaction if reference exists
        transaction = None
        if reference:
            transaction = TicketTransaction.objects.filter(
                paystack_reference=reference,
                user=request.user
            ).first()
            
            # Verify with Paystack if reference exists
            verify_url = f"https://api.paystack.co/transaction/verify/{reference}"
            headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
            response = requests.get(verify_url, headers=headers, timeout=10)
            data = response.json()

            if data.get('data', {}).get('status') == 'success' and transaction:
                # Generate secure token
                token = f"{get_random_string(3).upper()}-{get_random_string(6).upper()}"
                
                # Generate QR code
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=10,
                    border=4,
                )
                qr.add_data(f"TKT:{token}:{transaction.id}")
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                
                # Convert to base64
                buffer = BytesIO()
                img.save(buffer, format="PNG")
                qr_base64 = base64.b64encode(buffer.getvalue()).decode()
                
                # Update transaction
                transaction.status = 'completed'
                transaction.ticket_code = token
                transaction.qr_code = qr_base64
                transaction.date_completed = timezone.now()
                transaction.save()
                
                # Update ticket inventory
                transaction.ticket.tickets_sold += transaction.quantity
                transaction.ticket.save()

        # Always redirect to success
        return redirect(reverse('payment_success') + f'?reference={reference}' if reference else reverse('payment_success'))

    except Exception as e:
        logger.error(f"Payment verification error: {str(e)}")
        # Still redirect to success page
        return redirect('payment_success')
    
def payment_success(request):
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
    transactions = TicketTransaction.objects.filter(
        user=request.user
    ).select_related('ticket').order_by('-date_created')
    
    # Debug check
    print(f"Found {transactions.count()} transactions")  # Check console
    
    return render(request, 'pages/transaction_history.html', {
        'transactions': transactions,
        'now': timezone.now()
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
@staff_member_required
def verify_ticket(request):
    if request.method == 'POST':
        ticket_code = request.POST.get('ticket_code', '').strip().upper()
        
        try:
            ticket = TicketTransaction.objects.get(
                ticket_code=ticket_code,
                status='completed'
            )
            
            if ticket.is_checked_in:
                messages.warning(request, f'Ticket {ticket_code} was already used')
            else:
                ticket.is_checked_in = True
                ticket.checked_in_at = timezone.now()
                ticket.checked_in_by = request.user
                ticket.save()
                messages.success(request, f'Ticket {ticket_code} verified successfully!')
            
            return redirect('verify_ticket')
            
        except TicketTransaction.DoesNotExist:
            messages.error(request, 'Invalid ticket code')
            return redirect('verify_ticket')
    
    # GET request - show empty form
    return render(request, 'staff/verify_ticket.html')



@login_required
def my_tickets(request):
    tickets = TicketTransaction.objects.filter(
        user=request.user,
        status='completed'
    ).select_related('ticket').order_by('-date_completed')
    
    return render(request, 'pages/my_tickets.html', {
        'tickets': tickets
    })



@login_required
def download_receipt(request, ticket_id):
    ticket = get_object_or_404(TicketTransaction, id=ticket_id, user=request.user)
    
    # Create PDF buffer
    buffer = BytesIO()
    p = canvas.Canvas(buffer)
    
    # PDF Content
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 800, "OFFICIAL RECEIPT")
    
    p.setFont("Helvetica", 12)
    p.drawString(100, 770, f"Event: {ticket.ticket.name}")
    p.drawString(100, 750, f"Ticket Code: {ticket.ticket_code}")
    p.drawString(100, 730, f"Date: {ticket.ticket.date.strftime('%B %d, %Y')}")
    p.drawString(100, 710, f"Location: {ticket.ticket.location}")
    
    p.drawString(100, 680, "-" * 50)
    
    p.drawString(100, 650, f"Amount Paid: {ticket.formatted_price}")
    p.drawString(100, 630, f"Payment Reference: {ticket.paystack_reference}")
    p.drawString(100, 610, f"Purchase Date: {ticket.date_completed.strftime('%B %d, %Y %H:%M')}")
    
    # QR Code - Modified implementation
    if ticket.qr_code:
        try:
            qr_img = qrcode.make(f"TKT:{ticket.ticket_code}:{ticket.id}")
            qr_buffer = BytesIO()
            qr_img.save(qr_buffer, format="PNG")
            qr_buffer.seek(0)
            
            # Use ReportLab's ImageReader to properly handle the image
            from reportlab.lib.utils import ImageReader
            img_reader = ImageReader(qr_buffer)
            p.drawImage(img_reader, 400, 700, width=100, height=100, preserveAspectRatio=True)
        except Exception as e:
            print(f"Error adding QR code: {e}")  # Log error but continue
    
    p.showPage()
    p.save()
    
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="receipt_{ticket.ticket_code}.pdf"'
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def verify_ticket_api(request):
    """
    API endpoint for ticket verification
    Usage: /api/verify-ticket/?code=TICKET_CODE
    """
    ticket_code = request.GET.get('code', '').strip().upper()
    if not ticket_code:
        return Response({'error': 'Ticket code required'}, status=400)

    try:
        ticket = TicketTransaction.objects.get(
            ticket_code=ticket_code,
            status='completed'
        )
        
        is_valid, message, details = ticket.verify(request.user if request.user.is_staff else None)
        
        return Response({
            'success': is_valid,
            'message': message,
            'data': details
        })
        
    except TicketTransaction.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Invalid ticket code'
        }, status=404)