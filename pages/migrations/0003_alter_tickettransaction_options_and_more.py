# Generated by Django 5.1.7 on 2025-04-04 02:05

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0002_remove_tickettransaction_pages_ticke_barcode_46907f_idx_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='tickettransaction',
            options={'ordering': ['-date_created']},
        ),
        migrations.RemoveIndex(
            model_name='tickettransaction',
            name='pages_ticke_paystac_66f970_idx',
        ),
        migrations.RemoveIndex(
            model_name='tickettransaction',
            name='pages_ticke_date_cr_3963de_idx',
        ),
        migrations.RemoveField(
            model_name='tickettransaction',
            name='currency',
        ),
        migrations.RemoveField(
            model_name='tickettransaction',
            name='date_updated',
        ),
        migrations.RemoveField(
            model_name='tickettransaction',
            name='device_info',
        ),
        migrations.RemoveField(
            model_name='tickettransaction',
            name='ip_address',
        ),
        migrations.RemoveField(
            model_name='tickettransaction',
            name='payment_method',
        ),
        migrations.RemoveField(
            model_name='tickettransaction',
            name='transaction_id',
        ),
        migrations.AlterField(
            model_name='tickettransaction',
            name='checked_in_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='verified_tickets', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='tickettransaction',
            name='paystack_reference',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name='tickettransaction',
            name='quantity',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AlterField(
            model_name='tickettransaction',
            name='status',
            field=models.CharField(choices=[('pending', 'Pending'), ('completed', 'Completed'), ('failed', 'Failed')], default='pending', max_length=20),
        ),
        migrations.AlterField(
            model_name='tickettransaction',
            name='ticket_code',
            field=models.CharField(blank=True, max_length=20, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name='tickettransaction',
            name='total_price',
            field=models.DecimalField(decimal_places=2, max_digits=10),
        ),
    ]
