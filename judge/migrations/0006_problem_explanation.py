# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('judge', '0005_auto_20260731_1659')]
    operations = [migrations.AddField(
        model_name='problem', name='explanation',
        field=models.TextField(blank=True, max_length=2000, null=True, verbose_name='题目解析'),
    )]
