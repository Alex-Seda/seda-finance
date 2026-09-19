from django import forms

from .models import (
    Account,
    BudgetPeriod,
    BudgetSettings,
    Category,
    Envelope,
    Paycheck,
    RecurringBill,
)


class BudgetPeriodForm(forms.ModelForm):
    class Meta:
        model = BudgetPeriod
        fields = ("start_date", "end_date", "reset_day")
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        if (
            cleaned.get("start_date")
            and cleaned.get("end_date")
            and cleaned["end_date"] < cleaned["start_date"]
        ):
            raise forms.ValidationError("The end date must be on or after the start date.")
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.owner = self.user
        if commit:
            instance.save()
        return instance


class EnvelopeForm(forms.ModelForm):
    class Meta:
        model = Envelope
        fields = ("budget_period", "category", "assigned_amount", "rollover_amount")

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["budget_period"].queryset = BudgetPeriod.objects.filter(owner=user)
        self.fields["category"].queryset = Category.objects.filter(
            owner=user, is_active=True, is_envelope=True
        )

    def clean(self):
        cleaned = super().clean()
        period = cleaned.get("budget_period")
        category = cleaned.get("category")
        if period and category and Envelope.objects.filter(
            owner=self.user, budget_period=period, category=category
        ).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("That category already has an envelope in this period.")
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.owner = self.user
        if commit:
            instance.save()
        return instance


class PaycheckForm(forms.ModelForm):
    class Meta:
        model = Paycheck
        fields = ("pay_date", "expected_amount", "received_amount", "status", "notes")
        widgets = {"pay_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.owner = self.user
        if commit:
            instance.save()
        return instance


class RecurringBillForm(forms.ModelForm):
    class Meta:
        model = RecurringBill
        fields = (
            "name",
            "category",
            "account",
            "expected_amount",
            "due_day",
            "is_essential",
            "notes",
        )

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(
            owner=user, is_active=True
        )
        self.fields["account"].queryset = Account.objects.filter(owner=user)

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.owner = self.user
        if commit:
            instance.save()
        return instance


class BudgetSettingsForm(forms.ModelForm):
    class Meta:
        model = BudgetSettings
        exclude = ("owner", "updated_at")

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.owner = self.user
        if commit:
            instance.save()
        return instance
