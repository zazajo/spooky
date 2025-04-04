# models.py in pages app

from django.db import models
from django.contrib.auth.models import User
from django.contrib.auth.models import AbstractUser
import uuid
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from decimal import Decimal, InvalidOperation
from django.core.validators import MinValueValidator
from django.conf import settings
from django.utils.crypto import get_random_string
import qrcode
from io import BytesIO
import base64


User = get_user_model()

def generate_transaction_id():
    return f"TXN-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

class TicketTransaction(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]

    # Required Fields
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ticket_transactions'
    )
    ticket = models.ForeignKey(
        'PartyTicket',
        on_delete=models.PROTECT,
        related_name='transactions'
    )
    quantity = models.PositiveIntegerField(default=1)
    total_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        default=Decimal('0.00')
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    # Verification Fields
    ticket_code = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        null=True,
        help_text="Unique ticket identifier for verification"
    )
    qr_code = models.TextField(
        blank=True, 
        null=True,
        help_text="Base64 encoded QR code image"
    )
    
    # Payment Fields
    paystack_reference = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        help_text="Reference ID from Paystack"
    )
    paystack_data = models.JSONField(
        default=dict, 
        blank=True,
        help_text="Raw payment data from Paystack"
    )
    
    # Check-in Fields
    is_checked_in = models.BooleanField(
        default=False,
        help_text="Whether ticket has been used for entry"
    )
    checked_in_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When ticket was verified"
    )
    checked_in_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='verified_tickets',
        help_text="Staff member who verified this ticket"
    )
    
    # Timestamps
    date_created = models.DateTimeField(
        auto_now_add=True,
        help_text="When transaction was initiated"
    )
    date_completed = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When payment was completed"
    )
    date_modified = models.DateTimeField(
        auto_now=True,
        help_text="Last modification timestamp"
    )

    class Meta:
        ordering = ['-date_created']
        indexes = [
            models.Index(fields=['ticket_code']),
            models.Index(fields=['status']),
            models.Index(fields=['is_checked_in']),
        ]
        verbose_name = "Ticket Transaction"
        verbose_name_plural = "Ticket Transactions"

    def __str__(self):
        return f"{self.ticket_code} - {self.user.email} ({self.status})"

    def save(self, *args, **kwargs):
        """
        Custom save logic:
        - Generate ticket code when status changes to completed
        - Generate QR code if not exists
        - Calculate total price if not set
        """
        if not self.pk or self.status == 'completed':
            if not self.ticket_code:
                self.generate_ticket_code()
            if not self.qr_code:
                self.generate_qr_code()
        
        if not self.total_price:
            self.total_price = self.ticket.price * self.quantity
            
        super().save(*args, **kwargs)

    def generate_ticket_code(self):
        """Generate a unique ticket code"""
        prefix = self.ticket.event.code if hasattr(self.ticket, 'event') else 'TKT'
        random_part = get_random_string(8, allowed_chars='ABCDEFGHJKLMNPQRSTUVWXYZ23456789')
        self.ticket_code = f"{prefix}-{random_part}"
        return self.ticket_code

    def generate_qr_code(self):
        """Generate QR code for this ticket and save as base64"""
        if not self.ticket_code:
            return
            
        verification_url = f"{settings.SITE_URL}/verify-ticket/?token={self.ticket_code}"
        
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(verification_url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        self.qr_code = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return self.qr_code

    @property
    def formatted_price(self):
        """Formatted price with currency symbol"""
        return f"₦{self.total_price:,.2f}"

    @property
    def verification_status(self):
        """Returns human-readable verification status"""
        if self.status != 'completed':
            return 'invalid'
        return 'used' if self.is_checked_in else 'valid'

    @property
    def verification_details(self):
        """Returns all verification data in a structured format"""
        return {
            'ticket_id': self.id,
            'ticket_code': self.ticket_code,
            'event': self.ticket.name,
            'event_date': self.ticket.date.strftime('%Y-%m-%d'),
            'event_time': self.ticket.time.strftime('%H:%M') if hasattr(self.ticket, 'time') else None,
            'event_location': self.ticket.location,
            'buyer': {
                'name': self.user.get_full_name(),
                'email': self.user.email
            },
            'quantity': self.quantity,
            'status': self.verification_status,
            'checked_in_at': self.checked_in_at.isoformat() if self.is_checked_in else None,
            'checked_in_by': self.checked_in_by.get_full_name() if self.is_checked_in else None,
            'qr_code_url': f"data:image/png;base64,{self.qr_code}" if self.qr_code else None,
        }

    def mark_as_used(self, verifying_user=None):
        """
        Marks ticket as used/verified
        Returns tuple: (success: bool, message: str)
        """
        if self.status != 'completed':
            return False, "Cannot verify - payment not completed"
            
        if self.is_checked_in:
            return False, "Ticket already used"
            
        self.is_checked_in = True
        self.checked_in_at = timezone.now()
        self.checked_in_by = verifying_user
        self.save()
        return True, "Ticket successfully verified"

    def get_verification_url(self):
        """Returns the full verification URL for this ticket"""
        return f"{settings.SITE_URL}/verify-ticket/?token={self.ticket_code}"

    def send_confirmation_email(self):
        """Sends ticket confirmation email to buyer"""
        # Implementation depends on your email service
        pass



class PartyTicket(models.Model):
    TICKET_TYPES = [
        ('early_bird', 'Early Bird'),
        ('regular', 'Regular'),
        ('vip', 'VIP'),
    ]

    # Basic Ticket Info
    name = models.CharField(max_length=200)
    description = models.TextField()
    price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    date = models.DateField()
    location = models.CharField(max_length=255)
    image = models.ImageField(upload_to='tickets/', blank=True, null=True)
    
    # Inventory Management
    available_tickets = models.PositiveIntegerField(default=0)
    tickets_sold = models.PositiveIntegerField(default=0)
    
    # Ticket Type
    ticket_type = models.CharField(
        max_length=20,
        choices=TICKET_TYPES,
        default='regular'
    )
    
    # Barcode System
    barcode = models.CharField(max_length=50, blank=True, unique=True)
    is_scanned = models.BooleanField(default=False)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.available_tickets < self.tickets_sold:
            raise ValidationError("Tickets sold cannot exceed available tickets")

    def save(self, *args, **kwargs):
        if not self.barcode:
            self.barcode = self._generate_barcode()
        super().save(*args, **kwargs)

    def _generate_barcode(self):
        prefix = {
            'early_bird': 'EB',
            'regular': 'RG', 
            'vip': 'VIP'
        }.get(self.ticket_type, 'TK')
        return f"{prefix}-{timezone.now().timestamp():.0f}-{self.id or 'NEW'}"

    @property
    def tickets_remaining(self):
        return max(0, self.available_tickets - self.tickets_sold)

    def __str__(self):
        return f"{self.name} ({self.get_ticket_type_display()})"
    


class BrandNotification(models.Model):
    email = models.EmailField(unique=True)
    date_subscribed = models.DateTimeField(auto_now_add=True)
    notified = models.BooleanField(default=False)

    def __str__(self):
        return self.email
        
        
    

    


    



# class PartyTicket(models.Model):
#     TICKET_TYPES = [
#         ('early_bird', 'Early Bird'),
#         ('regular', 'Regular'),
#     ]

#     name = models.CharField(max_length=200)
#     description = models.TextField()
#     price = models.DecimalField(max_digits=10, decimal_places=2)
#     event_date = models.DateField()
#     location = models.CharField(max_length=255)
#     image = models.ImageField(upload_to='tickets/', blank=True, null=True)
    
#     # New field for ticket type
#     ticket_type = models.CharField(
#         max_length=20,
#         choices=TICKET_TYPES,
#         default='regular'
#     )

#     def __str__(self):
#         return f"{self.title} - {self.get_ticket_type_display()}"

        