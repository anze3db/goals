from django import forms

from goals import models


class BoardForm(forms.ModelForm):
    class Meta:
        model = models.Board
        fields = ["name"]


class GoalForm(forms.Form):
    name = forms.CharField(required=True)
    amount = forms.DecimalField(required=True)
    group = forms.CharField(required=True)
