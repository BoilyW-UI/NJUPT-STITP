# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import random

from django.db import migrations, models


def regenerate_join_codes(apps, schema_editor):
    """将已有班级码统一为唯一的6位数字。"""
    BanJi = apps.get_model('work', 'BanJi')
    used_codes = set()
    for banji in BanJi.objects.all().order_by('pk'):
        while True:
            code = '%06d' % random.randint(100000, 999999)
            if code not in used_codes:
                used_codes.add(code)
                break
        banji.join_code = code
        banji.save(update_fields=['join_code'])


class Migration(migrations.Migration):

    dependencies = [
        ('work', '0026_populate_banji_join_code'),
    ]

    operations = [
        migrations.AlterField(
            model_name='banji',
            name='join_code',
            field=models.CharField(blank=True, max_length=6, null=True, unique=True, verbose_name='班级码'),
        ),
        migrations.RunPython(regenerate_join_codes, migrations.RunPython.noop),
    ]
