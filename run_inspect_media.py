import os
import sys

sys.path.insert(0, r'e:\E\CardFlow')
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'

import django
django.setup()

from django.db import connection

cur = connection.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'mediafiles_cardmedia'")
print("mediafiles_cardmedia columns:", [r[0] for r in cur.fetchall()])
