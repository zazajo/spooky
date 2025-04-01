from django import forms

class PurchaseForm(forms.Form):
    quantity = forms.IntegerField(
        min_value=1,
        max_value=10,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'style': 'background: rgba(255,255,255,0.1); color: white; border: 1px solid #00f2ff;'
        })
    )