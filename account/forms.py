from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.password_validation import (
    password_validators_help_texts,
    validate_password,
)

from core import theme

User = get_user_model()


def text_input(autocomplete, **attrs):
    return forms.TextInput(
        attrs={"class": "input", "autocomplete": autocomplete, **attrs}
    )


def password_input(autocomplete):
    return forms.PasswordInput(
        attrs={"class": "input", "autocomplete": autocomplete, "data-password": ""}
    )


class BaseForm(forms.Form):
    """Shared behaviour: plain labels, friendly required messages, and
    aria-invalid on fields with errors so CSS and screen readers see them."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ""
        for field in self.fields.values():
            if "required" in field.error_messages:
                field.error_messages["required"] = f"{field.label} is required."

    def full_clean(self):
        super().full_clean()
        for name in self.errors:
            field = self.fields.get(name)
            if field is not None:
                field.widget.attrs["aria-invalid"] = "true"
                field.widget.attrs["aria-describedby"] = f"{name}-error"


class UserLoginForm(BaseForm):
    username = forms.CharField(
        label="Username",
        max_length=150,
        widget=text_input("username", autocapitalize="none", autofocus=True),
    )
    password = forms.CharField(
        label="Password",
        max_length=128,
        strip=False,
        widget=password_input("current-password"),
    )

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        self.user = None
        super().__init__(*args, **kwargs)

    def clean(self):
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        if username and password:
            self.user = authenticate(self.request, username=username, password=password)
            if self.user is None:
                # Same message whether the username or the password is wrong.
                self.add_error(
                    "password", forms.ValidationError("Please check your credentials.")
                )
        return super().clean()


class UserSignUpForm(BaseForm):
    username = forms.CharField(
        label="Username",
        max_length=150,
        help_text="Letters, digits and @ . + - _ only.",
        validators=[User.username_validator],
        widget=text_input("username", autocapitalize="none"),
    )
    email = forms.EmailField(
        label="Email",
        max_length=254,
        widget=forms.EmailInput(attrs={"class": "input", "autocomplete": "email"}),
    )
    first_name = forms.CharField(
        label="First name", max_length=150, widget=text_input("given-name")
    )
    last_name = forms.CharField(
        label="Last name", max_length=150, widget=text_input("family-name")
    )
    password1 = forms.CharField(
        label="Password",
        max_length=128,
        strip=False,
        widget=password_input("new-password"),
    )
    password2 = forms.CharField(
        label="Confirm password",
        max_length=128,
        strip=False,
        widget=password_input("new-password"),
    )

    # Field groups shown as nodes on the signup spine.
    groups = (
        ("Account", ("username", "email")),
        ("Name", ("first_name", "last_name")),
        ("Password", ("password1", "password2")),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].help_text = " ".join(password_validators_help_texts())

    def grouped_fields(self):
        return [(title, [self[name] for name in names]) for title, names in self.groups]

    def clean_username(self):
        username = self.cleaned_data.get("username")
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Username already exists.", code="exists")
        return username

    def clean_password1(self):
        password1 = self.cleaned_data.get("password1")
        user = User(
            username=self.cleaned_data.get("username"),
            first_name=self.cleaned_data.get("first_name"),
            last_name=self.cleaned_data.get("last_name"),
            email=self.cleaned_data.get("email"),
        )
        validate_password(password1, user=user)
        return password1

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if not self.errors.get("password1") and password1 != password2:
            raise forms.ValidationError("Passwords do not match.", code="mismatch")
        return password2


class ProfileForm(BaseForm, forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email")
        labels = {"first_name": "First name", "last_name": "Last name"}
        widgets = {
            "first_name": text_input("given-name"),
            "last_name": text_input("family-name"),
            "email": forms.EmailInput(
                attrs={"class": "input", "autocomplete": "email"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True


class StyledPasswordChangeForm(PasswordChangeForm):
    """Django's password change form with the design system's widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        autocomplete = {
            "old_password": "current-password",
            "new_password1": "new-password",
            "new_password2": "new-password",
        }
        for name, field in self.fields.items():
            field.widget = password_input(autocomplete[name])
            field.widget.attrs.pop("autofocus", None)
        self.label_suffix = ""

    def full_clean(self):
        super().full_clean()
        for name in self.errors:
            if name in self.fields:
                self.fields[name].widget.attrs["aria-invalid"] = "true"
                self.fields[name].widget.attrs["aria-describedby"] = f"{name}-error"


class AppearanceForm(forms.Form):
    """Any subset of palette, mode and density."""

    palette = forms.ChoiceField(
        required=False, choices=[(p.key, p.name) for p in theme.PALETTES]
    )
    mode = forms.ChoiceField(required=False, choices=theme.MODES)
    density = forms.ChoiceField(required=False, choices=theme.DENSITIES)

    def changes(self):
        return {k: v for k, v in self.cleaned_data.items() if v}
