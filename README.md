Dev environemnt set up:

```
cp .env.example .env
pipenv install --dev
npm install
docker compose up -d
```

pipenv shell
python manage.py createsuperuser
python manage.py collectstatic
python manage.py runserver
python manage.py tailwind start
ptw
```

Run all tests and checks:

```
isort . && black . && mypy . && pylint almograve goals index users && pytest
```


