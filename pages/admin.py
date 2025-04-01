from django.contrib import admin
from .models import PartyTicket
from .models import TicketTransaction
from .models import BrandNotification
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html

@admin.register(PartyTicket)
class PartyTicketAdmin(admin.ModelAdmin):
    list_display = ('name', 'ticket_type', 'price', 'available_tickets', 'tickets_sold', 'tickets_remaining', 'is_sold_out')
    list_filter = ('ticket_type', 'date')
    readonly_fields = ('created_at', 'updated_at', 'tickets_remaining_display')
    search_fields = ('name', 'location')
    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'ticket_type', 'price')
        }),
        ('Event Details', {
            'fields': ('date', 'location', 'image')
        }),
        ('Inventory', {
            'fields': ('available_tickets', 'tickets_sold')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at')
        })
    )

    def tickets_remaining(self, obj):
        return obj.tickets_remaining
    tickets_remaining.short_description = 'Remaining'

    def is_sold_out(self, obj):
        return obj.tickets_remaining <= 0
    is_sold_out.boolean = True
    is_sold_out.short_description = 'Sold Out'

    def tickets_remaining_display(self, obj):
        return f"{obj.tickets_remaining} / {obj.available_tickets}"
    tickets_remaining_display.short_description = 'Tickets Remaining'

@admin.register(TicketTransaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'user', 'ticket', 'status', 'formatted_price', 'date_created', 'qr_code_preview')
    list_filter = ('status', 'date_created', 'ticket__ticket_type')
    search_fields = ('paystack_reference', 'user__username', 'ticket_code', 'transaction_id')
    readonly_fields = ('date_created', 'date_updated', 'paystack_reference', 'transaction_id', 
                     'qr_code_display', 'ticket_code', 'date_completed')
    fieldsets = (
        ('Transaction Details', {
            'fields': ('transaction_id', 'user', 'ticket', 'status', 'quantity', 'total_price')
        }),
        ('Payment Information', {
            'fields': ('paystack_reference', 'paystack_data', 'payment_method', 'currency')
        }),
        ('Verification', {
            'fields': ('ticket_code', 'qr_code_display', 'is_checked_in', 'checked_in_at', 'checked_in_by')
        }),
        ('Timestamps', {
            'fields': ('date_created', 'date_updated', 'date_completed')
        }),
        ('Metadata', {
            'fields': ('ip_address', 'device_info')
        })
    )

    def qr_code_preview(self, obj):
        if obj.qr_code:
            return format_html(
                '<img src="data:image/png;base64,{}" style="max-width: 50px; max-height: 50px;" />',
                obj.qr_code
            )
        return "-"
    qr_code_preview.short_description = 'QR Code'

    def qr_code_display(self, obj):
        if obj.qr_code:
            return format_html(
                '<img src="data:image/png;base64,{}" style="max-width: 200px; max-height: 200px;" /><br>'
                '<small>Ticket Code: {}</small>',
                obj.qr_code,
                obj.ticket_code
            )
        return "Not generated yet"
    qr_code_display.short_description = 'QR Ticket'
    qr_code_display.allow_tags = True

    def formatted_price(self, obj):
        return obj.formatted_price
    formatted_price.short_description = 'Price'

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status == 'completed':
            # Make all fields readonly for completed transactions
            return [f.name for f in obj._meta.fields if f.name != 'is_checked_in']
        return super().get_readonly_fields(request, obj)

    def has_delete_permission(self, request, obj=None):
        # Prevent deletion of completed transactions
        if obj and obj.status == 'completed':
            return False
        return super().has_delete_permission(request, obj)
    

@admin.register(BrandNotification)
class BrandNotificationAdmin(admin.ModelAdmin):
    list_display = ('email', 'date_subscribed', 'notified')
    list_filter = ('notified',)
    search_fields = ('email',)