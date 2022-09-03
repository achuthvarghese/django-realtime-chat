from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


class BaseForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super(BaseForm, self).__init__(*args, **kwargs)

        self.label_suffix = ""

        for field_name, field in self.fields.items():
            if "required" in field.error_messages:
                field.error_messages["required"] = f"{field.label} is required."

    def clean(self):
        super(BaseForm, self).clean()

        for field_name in self.errors:
            field = self.fields.get(field_name)
            field_css_class = field.widget.attrs.get("class")
            field.widget.attrs.update({"class": f"{field_css_class} border-danger"})
        return self.cleaned_data


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
            raise forms.ValidationError("Please check your credentials.")
        return username

    def clean(self):
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        if username and password:
            user = authenticate(username=username, password=password)
            if user is None:
                self.add_error(
                    "password", forms.ValidationError("Please check your credentials.")
                )
        return super(UserLoginForm, self).clean()


class UserSignUpForm(BaseForm):
    first_name = forms.CharField(
        label="First Name",
        max_length=50,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "First Name",
            }
        ),
    )
    last_name = forms.CharField(
        label="Last Name",
        max_length=50,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Last Name",
            }
        ),
    )
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
    email = forms.EmailField(
        label="Email",
        max_length=75,
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "Email",
            }
        ),
    )
    password1 = forms.CharField(
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
    password2 = forms.CharField(
        label="Confirm Password",
        max_length=50,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Confirm Password",
                "autocomplete": "off",
            }
        ),
    )

    def clean_username(self):
        username = self.cleaned_data.get("username")

        user = User.objects.filter(username=username).exists()

        if user:
            raise forms.ValidationError("Username already exists.", code="exists")
        return username

    def clean_password1(self):
        first_name = self.cleaned_data.get("first_name")
        last_name = self.cleaned_data.get("last_name")
        username = self.cleaned_data.get("username")
        password1 = self.cleaned_data.get("password1")
        email = self.cleaned_data.get("email")

        user = User(
            username=username,
            first_name=first_name,
            last_name=last_name,
            email=email,
        )

        try:
            validate_password(password1, user=user)
        except forms.ValidationError as validation_errors:
            raise validation_errors
        return password1

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")

        if not self.errors.get("password1"):
            if password1 != password2:
                raise forms.ValidationError(
                    "Passwords does not match.", code="mismatch"
                )
        return password2
