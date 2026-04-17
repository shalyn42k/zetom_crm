from django import forms


class CrispyDemoForm(forms.Form):
    PRIORITY_CHOICES = (
        ("medium", "Medium"),
        ("low", "Low"),
        ("high", "High"),
    )
    DEPARTMENT_CHOICES = (
        ("sales", "Sales"),
        ("marketing", "Marketing"),
        ("development", "Development"),
        ("hr", "Human Resources"),
        ("other", "Other"),
    )
    CATEGORY_CHOICES = (
        ("general", "General Inquiry"),
        ("support", "Technical Support"),
        ("feedback", "Feedback"),
        ("other", "Other"),
    )

    name = forms.CharField(required=True)
    email = forms.EmailField(required=True)
    age = forms.IntegerField(required=True, min_value=0)
    url = forms.URLField(required=True)
    salary = forms.DecimalField(required=True, min_value=0, decimal_places=2, max_digits=10)
    currency = forms.ChoiceField(choices=(("eur", "Euro"), ("usd", "USD"), ("pln", "PLN")))
    priority = forms.ChoiceField(choices=PRIORITY_CHOICES, initial="medium")

    subscribe_newsletter = forms.BooleanField(required=False, initial=True)
    receive_notifications = forms.BooleanField(required=False)
    department = forms.ChoiceField(choices=DEPARTMENT_CHOICES, widget=forms.RadioSelect)
    category = forms.MultipleChoiceField(choices=CATEGORY_CHOICES, widget=forms.CheckboxSelectMultiple)

    file = forms.FileField(required=True)
    image = forms.ImageField(required=True)

    date = forms.DateField(required=True, widget=forms.DateInput(attrs={"type": "date"}))
    time = forms.TimeField(required=True, widget=forms.TimeInput(attrs={"type": "time"}))
    datetime_date = forms.DateField(required=True, widget=forms.DateInput(attrs={"type": "date"}))
    datetime_time = forms.TimeField(required=True, widget=forms.TimeInput(attrs={"type": "time"}))

    title = forms.CharField(required=True, widget=forms.Textarea(attrs={"rows": 2}))
    message = forms.CharField(required=True, widget=forms.Textarea(attrs={"rows": 8}))
