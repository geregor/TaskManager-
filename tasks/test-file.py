import requests
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tasks.settings')
django.setup()

from .models import Employee
employees_data = [
    {
            'bitrix_id': 1,
            'name': "Павел",
            'is_active': True
    },
    {
            'bitrix_id': 840,
            'name': "Александр",
    }
]

created = []
for emp_data in employees_data:
    employee, created_flag = Employee.objects.get_or_create(
        bitrix_id=emp_data['bitrix_id'],
        defaults=emp_data
    )
    if created_flag:
        created.append(employee.name)

    print(f"Созданы сотрудники: {', '.join(created)}")


# Настройки подключения
# WEBHOOK_URL = "https://vpseo.bitrix24.ru/rest/860/g91ta8jxbf74bpsz/"  # Замените на ваш вебхук
# METHOD = "tasks.task.list"  # Метод API
#
# # Параметры запроса (можно настроить по необходимости)
# params = {
#     "order": {"ID": "desc"},  # Сортировка по ID в обратном порядке
#     # "filter": {"CREATED_BY": '860'}
#     'filter': {">=ID": "268434", "<=ID": "268442"}
#     # "FILTER": {
#     #     ">=CREATED_DATE": "2024-01-01",  # Задачи с 2024 года
#     #     "!STATUS": "5"  # Исключить завершенные задачи (статус 5)
#     # },
#     # "select": ["ID", "TITLE", "CREATED_DATE", "RESPONSIBLE_ID"],  # Какие поля выбрать
#     # "start": 0  # Пагинация - начать с 0
# }
#
# # Отправка запроса
# response = requests.post(
#     url=f"{WEBHOOK_URL}{METHOD}",
#     json=params
# )
#
# # Обработка ответа
# if response.status_code == 200:
#     print(response.json())
#     for task in response.json()['result']['tasks']:
#         print(task['id'], task['createdBy'], task['title'])
#     tasks = response.json().get("result", {}).get("tasks", [])
#     print(f"Найдено задач: {len(tasks)}")
#     for task in tasks:
#         print(f"ID: {task['ID']}, Заголовок: {task['TITLE']}, Ответственный: {task['RESPONSIBLE_ID']}")
# else:
#     print(f"Ошибка: {response.status_code}, {response.text}")



#----------------------------------
# WEBHOOK_URL = "https://vpseo.bitrix24.ru/rest/860/g91ta8jxbf74bpsz/"  # Замените на ваш вебхук
# METHOD = "user.get"  # Метод API
#
# # Параметры запроса (можно настроить по необходимости)
# params = {
#     # "order": {"ID": "desc"},  # Сортировка по ID в обратном порядке
#     # "filter": {"CREATED_BY": '860'}
#     # 'filter': {">=ID": "268434", "<=ID": "268442"}
#     # "FILTER": {
#     #     ">=CREATED_DATE": "2024-01-01",  # Задачи с 2024 года
#     #     "!STATUS": "5"  # Исключить завершенные задачи (статус 5)
#     # },
#     # "select": ["ID", "TITLE", "CREATED_DATE", "RESPONSIBLE_ID"],  # Какие поля выбрать
#     # "start": 0  # Пагинация - начать с 0
# }
#
# # Отправка запроса
# response = requests.post(
#     url=f"{WEBHOOK_URL}{METHOD}",
#     json=params
# )
#
# # Обработка ответа
# if response.status_code == 200:
#     print(response.json())
# else:
#     print(f"Ошибка: {response.status_code}, {response.text}")