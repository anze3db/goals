from django import forms

from goals import models


class BoardForm(forms.ModelForm):
    class Meta:
        model = models.Board
        fields = ["name"]
