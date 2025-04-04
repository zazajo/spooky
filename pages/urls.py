# from django.contrib import admin
# from django.urls import path, include
# from pages import views
# from .views import ticket_list
# from .views import transaction_history
# from django.contrib.auth import views as auth_views  # Add this import
# from django.contrib.auth.views import LogoutView
# from pages.views import verify_ticket

from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views
from django.contrib.auth.views import LogoutView
from . import views
from pages.views import (
    home,
    ticket_list,
    transaction_history,
    signup_view,
    login_view,
    account_view,
    brands_shopping,
    notify_me,
    purchase_ticket,
    initiate_payment,
    verify_payment,
    payment_success,
    payment_failed,
    validate_ticket,
    verify_ticket,
)

urlpatterns = [
    # Core Pages
    path("", home, name="home"),
    path('tickets/', ticket_list, name='ticket_list'),
    
    # Authentication
    path('signup/', signup_view, name='signup'),
    path('login/', login_view, name='login'),
    path('accounts/logout/', LogoutView.as_view(), name='logout'),
    path('account/', account_view, name='account'),
    
    # Password Management
    path('password-change/',
         auth_views.PasswordChangeView.as_view(
             template_name='account/password_change.html'
         ),
         name='password_change'),
    path('password-change/done/',
         auth_views.PasswordChangeDoneView.as_view(
             template_name='account/password_change_done.html'
         ),
         name='password_change_done'),
    
    # Shopping & Transactions
    path('brands/', brands_shopping, name='brands_shopping'),
    path('notify-me/', notify_me, name='notify_me'),
    path('transactions/', transaction_history, name='transaction_history'),
    path('my-tickets/', views.my_tickets, name='my_tickets'),
    path('receipt/<int:ticket_id>/', views.download_receipt, name='download_receipt'),
    
    # Payment Flow
    path('purchase/<int:ticket_id>/', purchase_ticket, name='purchase_ticket'),
    path('initiate-payment/<int:ticket_id>/', initiate_payment, name='initiate_payment'),
    path('verify-payment/', verify_payment, name='verify_payment'),
    path('payment/success/', payment_success, name='payment_success'),
    path('payment/failed/', payment_failed, name='payment_failed'),
    path('api/create-transaction/', views.create_transaction, name='create_transaction'),
    
    # Ticket Verification
    path('validate-ticket/<str:code>/', validate_ticket, name='validate_ticket'),  # Changed barcode to code
    path('verify-ticket/', views.verify_ticket, name='verify_ticket'),
]  