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


User = get_user_model()

def generate_transaction_id():
    return f"TXN-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

class TicketTransaction(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
        ('cancelled', 'Cancelled'),
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
    quantity = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)]
    )
    total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    # Identification Fields
    paystack_reference = models.CharField(
        max_length=100,
        unique=True,
        blank=True,
        null=True
    )
    transaction_id = models.CharField(
        max_length=50,
        unique=True,
        default=generate_transaction_id,
        editable=False
    )
    
    # QR Code Verification
    qr_code = models.TextField(blank=True, null=True)  # Base64 encoded QR image
    ticket_code = models.CharField(
        max_length=20,
        unique=True,
        blank=True
    )  # Human-readable code
    
    # Timestamps
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)
    date_completed = models.DateTimeField(blank=True, null=True)
    
    # Payment Details
    currency = models.CharField(max_length=3, default='NGN')
    paystack_data = models.JSONField(default=dict, blank=True)
    payment_method = models.CharField(max_length=50, blank=True)
    
    # Ticket Fulfillment
    is_checked_in = models.BooleanField(default=False)
    checked_in_at = models.DateTimeField(blank=True, null=True)
    checked_in_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='checked_in_tickets'
    )
    
    # Metadata
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    device_info = models.JSONField(default=dict, blank=True)
    
    class Meta:
        ordering = ['-date_created']
        verbose_name = 'Ticket Transaction'
        verbose_name_plural = 'Ticket Transactions'
        indexes = [
            models.Index(fields=['paystack_reference']),
            models.Index(fields=['status']),
            models.Index(fields=['date_created']),
            models.Index(fields=['ticket_code']),
        ]
    
    def __str__(self):
        return f"{self.transaction_id} - {self.user.email} ({self.status})"
    
    def save(self, *args, **kwargs):
        # Generate ticket code if not set
        if not self.ticket_code:
            self.ticket_code = self.generate_human_code()
        
        # Update completion date if status changed to completed
        if self.status == 'completed' and not self.date_completed:
            self.date_completed = timezone.now()
        
        # Calculate total price if not set
        if not self.total_price and hasattr(self, 'ticket'):
            self.total_price = Decimal(self.ticket.price) * self.quantity
        
        super().save(*args, **kwargs)
    
    def generate_qr_code(self):
        """Generate and store QR code if not exists"""
        if not self.qr_code:
            import qrcode
            from io import BytesIO
            import base64
            
            qr_data = f"TKT-{self.transaction_id}-{self.user.id}"
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(qr_data)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            self.qr_code = base64.b64encode(buffer.getvalue()).decode()
        return self.qr_code
    
    def generate_human_code(self):
        """Generate human-readable ticket code"""
        import secrets
        import string
        chars = string.ascii_uppercase + string.digits
        return f"{secrets.choice(chars)}{secrets.choice(chars)}-{''.join(secrets.choice(chars) for _ in range(6))}"
    
    def mark_as_checked_in(self, user):
        self.is_checked_in = True
        self.checked_in_at = timezone.now()
        self.checked_in_by = user
        self.save()
    
    @property
    def is_active(self):
        return self.status == 'completed' and not self.is_checked_in
    
    @property
    def formatted_price(self):
        return f"{self.currency} {self.total_price:,.2f}"
    
    def clean(self):
        if self.quantity < 1:
            raise ValidationError("Quantity must be at least 1")
        
        if hasattr(self, 'ticket') and self.ticket:
            if self.quantity > self.ticket.tickets_available:
                raise ValidationError(
                    f"Only {self.ticket.tickets_available} tickets available"
                )



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

        