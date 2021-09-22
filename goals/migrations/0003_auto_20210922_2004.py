# Generated by Django 3.2.7 on 2021-09-22 20:04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('goals', '0002_auto_20210907_0029'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='result',
            options={'ordering': ['goal', 'index']},
        ),
        migrations.RemoveField(
            model_name='result',
            name='name',
        ),
        migrations.AddField(
            model_name='result',
            name='index',
            field=models.IntegerField(default=0),
        ),
    ]
