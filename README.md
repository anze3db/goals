# Goals 🎯

A site for tracking yearly goals 

## Dev set up

```
cp .env.example .env
python -m venv .venv
pip install -r requirements.txt
```

```
python manage.py createsuperuser
python manage.py collectstatic
python manage.py runserver
ptw
```

Run all tests and checks:

```
ruff . && mypy . && djlint . && pylint almograve goals index users && pytest
```


