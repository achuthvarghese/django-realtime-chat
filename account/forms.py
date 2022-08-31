from django import forms
from django.contrib.auth import authenticate, get_user_model

User = get_user_model()


class BaseForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super(BaseForm, self).__init__(*args, **kwargs)
        self.label_suffix = ""

        for k, field in self.fields.items():
            if "required" in field.error_messages:
                field.error_messages["required"] = f"{field.label} is required."


class UserLoginForm(BaseForm):
    username = forms.CharField(
        label="Username",
        max_length=50,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Username",
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        max_length=50,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Password",
                "autocomplete": "off",
            }
        ),
    )

    def clean_username(self):
        username = self.cleaned_data["username"]
        user = User.objects.filter(username=username).exists()
        if not user:
            username_field_css_class = self.fields.get("username").widget.attrs.get(
                "class"
            )
            self.fields.get("username").widget.attrs.update(
                {"class": f"{username_field_css_class} border-danger"}
            )
            raise forms.ValidationError("Please check your credentials.")
        return username

    def clean(self):
        super(UserLoginForm, self).clean()
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")
        if username and password:
            user = authenticate(username=username, password=password)
            if user is None:
                password_field_css_class = self.fields.get("username").widget.attrs.get(
                    "class"
                )
                self.fields.get("password").widget.attrs.update(
                    {"class": f"{password_field_css_class} border-danger"}
                )
                self.add_error(
                    "password", forms.ValidationError("Please check your credentials.")
                )
