from django.shortcuts import render, redirect
from .models import Task, Employee
from django.contrib.auth import get_user_model
User = get_user_model()
import requests
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from datetime import datetime, timedelta
from django.core.exceptions import ObjectDoesNotExist
from django.http import JsonResponse
import json
from django.views.decorators.http import require_POST
from django.db import transaction

BACKLOG_USER_ID = 864

# WEBHOOK_URL = "https://vpseo.bitrix24.ru/rest/860/g91ta8jxbf74bpsz/"  # Замените на ваш вебхук
WEBHOOK_URL = "https://vpseo.bitrix24.ru/rest/1/7b1lfh5fvgk4ecag/"
def seconds_to_hhmm(total_seconds: int) -> str:
    """Конвертирует секунды в строку формата 'ЧАСЫ:МИНУТЫ'."""
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    return f"{hours}:{minutes:02d}"

def get_lists() -> list:
    METHOD = "tasks.task.list"
    # BACKLOG ID = 864
    params = {
        "order": {"ID": "desc"},
        "filter": {"RESPONSIBLE_ID": "864"}
    }

    # params = {
    #     "order": {"ID": "desc"},
    #     'filter': {">=ID": "268434", "<=ID": "268442"},
    #     # Дополнительные параметры можно раскомментировать
    #     # "select": ["ID", "TITLE", "CREATED_DATE", "RESPONSIBLE_ID", "TIME_ESTIMATE", "STATUS"],
    # }

    response = requests.post (
        url=f"{WEBHOOK_URL}{METHOD}",
        json=params,
        timeout=3
    )

    if response.status_code != 200:
        return {"error": "Failed to fetch tasks from Bitrix24"}

    tasks_data = response.json ().get ("result", {}).get ("tasks", [])
    processed_tasks = []

    for task_data in tasks_data:
        # Преобразование данных для фронтенда
        print(task_data['id'], task_data['createdBy'],task_data['responsible']['id'], task_data['title'])
        task_data['stringTimeEstimate'] = seconds_to_hhmm (int (task_data.get ('timeEstimate', 0)))
        task_data['stringCreatedDate'] = '.'.join (list (reversed (task_data['createdDate'][:10].split ("-"))))

        # Сохранение/обновление задачи в базе
        save_task_from_bitrix (task_data)

        processed_tasks.append (task_data)

    waited_tasks = Task.objects.filter(employee__isnull=True).order_by('id')

    return waited_tasks


def save_task_from_bitrix(task_data: dict):
    """
    Импортирует задачу из Bitrix в БД ТОЛЬКО ОДИН РАЗ.
    Если 'holder' (employee IS NULL, date IS NULL) уже существует для bitrix_id — НИЧЕГО НЕ ОБНОВЛЯЕМ.
    Рабочие сплиты (с employee/date) не затрагиваем.
    """
    # 1) Автор
    creator_data = task_data['creator']
    creator_id = int(creator_data['id'])
    creator, _ = Employee.objects.get_or_create(
        bitrix_id=creator_id,
        defaults={
            'name': creator_data.get('name', '') or '',
            'email': creator_data.get('email') or None,
            'icon': creator_data.get('icon') or None,
        }
    )

    bitrix_id = int(task_data['id'])

    # 2) Проверяем, есть ли уже holder этой задачи в бэклоге
    holder_qs = Task.objects.filter(
        bitrix_id=bitrix_id,
        employee__isnull=True,
        date__isnull=True
    ).order_by('id')

    if holder_qs.exists():
        # Если по ошибке несколько — оставим самую старую, остальные удалим
        # holder = holder_qs.first()
        # extra_ids = list(holder_qs.values_list('id', flat=True))[1:]
        # if extra_ids:
        #     Task.objects.filter(id__in=extra_ids).delete()
        # ⚠️ НИЧЕГО НЕ ОБНОВЛЯЕМ — данные «замораживаем» после первого импорта
        return holder_qs.first()

    # 3) Создаём holder (первичный импорт из Bitrix)
    fields = {
        'title': task_data.get('title', '') or '',
        'description': task_data.get('description', '') or '',
        'creator': creator,
        'status': map_bitrix_status(task_data.get('status', 2)),
        'original_time_estimate': int(task_data.get('timeEstimate') or 0),
    }
    if task_data.get('createdDate'):
        fields['created_at'] = task_data['createdDate']
    if task_data.get('deadline'):
        fields['deadline'] = task_data['deadline']

    return Task.objects.create(
        bitrix_id=bitrix_id,
        employee=None,
        date=None,
        **fields
    )

@require_POST
def review_decision(request):
    """
    Руководитель принимает/отклоняет:
    - approve  -> tasks.task.approve (итог: Completed)
    - reject   -> tasks.task.disapprove (итог: не выполнено / ожидание). Fallback -> tasks.task.pause
    Локально:
      approve:  status='completed', is_timer_running=False
      reject:   status='pending',   is_timer_running=False
    """
    decision = (request.POST.get('decision') or '').strip().lower()
    if decision not in ('approve', 'reject'):
        return JsonResponse({'status': 'error', 'message': 'Invalid decision'}, status=400)

    # Принимаем либо local id, либо bitrix_id
    bitrix_id = request.POST.get('bitrix_id')
    local_id = request.POST.get('task_id')

    if not bitrix_id and local_id:
        try:
            t = Task.objects.get(id=int(local_id))
            bitrix_id = t.bitrix_id
        except Exception:
            return JsonResponse({'status': 'error', 'message': 'Task not found'}, status=404)

    try:
        bitrix_id = int(bitrix_id)
    except (TypeError, ValueError):
        return JsonResponse({'status': 'error', 'message': 'Invalid bitrix_id'}, status=400)

    # Карта методов Bitrix
    method = 'tasks.task.approve' if decision == 'approve' else 'tasks.task.disapprove'

    try:
        # 1) Пытаемся выполнить основное действие
        resp = requests.post (f"{WEBHOOK_URL}{method}", json={"taskId": bitrix_id}, timeout=3)
        err_text = None
        if resp.status_code != 200:
            err_text = f"HTTP {resp.status_code}"
        else:
            try:
                jr = resp.json ()
            except Exception:
                jr = {}
            if isinstance (jr, dict) and jr.get ('error'):
                err_text = f"{jr.get ('error')}: {jr.get ('error_description') or ''}".strip ()

        # 2) Если reject не сработал (например, задача не в AWAITING CONTROL) — fallback pause
        if decision == 'reject' and err_text:
            requests.post (f"{WEBHOOK_URL}tasks.task.pause", json={"taskId": bitrix_id}, timeout=3)
            # локально считаем «вернули в работу»
            with transaction.atomic ():
                group = Task.objects.filter (bitrix_id=bitrix_id)
                group.update (status='pending', is_timer_running=False)
                affected_ids = list (group.values_list ('id', flat=True))
            return JsonResponse ({
                'status': 'success',
                'message': 'Отправлено на доработку (fallback)',
                'data': {'group_ids': affected_ids, 'bitrix_id': bitrix_id, 'status': 'pending'}
            })

        # 3) Если была ошибка и это approve — отдадим её на фронт
        if err_text and decision == 'approve':
            return JsonResponse ({'status': 'error', 'message': f'Bitrix error: {err_text}'}, status=502)

        # 4) Успешный сценарий — обновим локально
        with transaction.atomic ():
            group = Task.objects.filter (bitrix_id=bitrix_id)
            if decision == 'approve':
                group.update (status='completed', is_timer_running=False)
                st = 'completed'
            else:
                group.update (status='pending', is_timer_running=False)
                st = 'pending'
            affected_ids = list (group.values_list ('id', flat=True))

        return JsonResponse ({
            'status': 'success',
            'message': 'Решение применено',
            'data': {'group_ids': affected_ids, 'bitrix_id': bitrix_id, 'status': st}
        })

    except requests.Timeout:
        return JsonResponse ({'status': 'error', 'message': 'Bitrix timeout (3s)'}, status=504)
    except Exception as e:
        return JsonResponse ({'status': 'error', 'message': str (e)}, status=500)



def calendar_view():
    today = datetime.now().date()

    months_ru = [
        "январь", "февраль", "март", "апрель", "май", "июнь",
        "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"
    ]
    weekdays_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

    first_day_of_month = today.replace(day=1)
    if today.month == 12:
        first_day_next_month = today.replace(year=today.year + 1, month=1, day=1)
    else:
        first_day_next_month = today.replace(month=today.month + 1, day=1)

    extended_first_day = first_day_of_month - timedelta(days=14)
    extended_last_day = first_day_next_month + timedelta(days=14)

    tasks_in_period = (Task.objects
        .filter(date__gte=extended_first_day, date__lte=extended_last_day)
        .select_related('employee'))

    # Группируем задачи по дате и исполнителю
    tasks_by_date = {}
    for task in tasks_in_period:
        if not task.date:
            continue
        day_bucket = tasks_by_date.setdefault(task.date, {})
        if task.employee:
            day_bucket.setdefault(task.employee.bitrix_id, []).append(task)

    # Если сегодня выходной — целимся в ближайший рабочий день
    if today.weekday() >= 5:  # 5=Сб, 6=Вс
        next_monday = today + timedelta(days=(7 - today.weekday()))
        prev_friday = today - timedelta(days=(today.weekday() - 4))
        target_date = next_monday if next_monday <= extended_last_day else prev_friday
    else:
        target_date = today

    days_in_month = {}
    current_day_index = 0
    idx = 0
    d = extended_first_day
    while d <= extended_last_day:
        if d.weekday() < 5:  # только будни
            idx += 1
            if d == target_date:
                current_day_index = idx
            day_tasks = tasks_by_date.get(d, {})
            days_in_month[idx] = {
                "week_day": f"{d.day} {weekdays_ru[d.weekday()]}",
                "tasks": day_tasks,
                "full_date": d.strftime("%Y-%m-%d"),
            }
        d += timedelta(days=1)

    # На всякий случай — если target_date выпал из диапазона
    if current_day_index == 0 and days_in_month:
        current_day_index = 1

    return {
        "current_month": today.month,
        "current_year": today.year,
        "current_month_name": months_ru[today.month - 1].capitalize(),
        "days_in_month": days_in_month,
        "current_day": current_day_index,
        "day_and_month": f"{today.day} {months_ru[today.month - 1]}",
    }



def start_task(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST allowed'}, status=405)

    try:
        local_id = int(request.POST.get('task_id'))  # ЛОКАЛЬНЫЙ id сплита
    except (TypeError, ValueError):
        return JsonResponse({"error": "Некорректный task_id"}, status=400)

    try:
        task = Task.objects.select_related('employee').get(id=local_id)
    except Task.DoesNotExist:
        return JsonResponse({"error": "Задача не найдена"}, status=404)

    if task.status in ['completed', 'deleted']:
        return JsonResponse({"error": "Нельзя менять время для завершенной/удаленной задачи"}, status=400)

    # Всегда работаем по bitrix_id
    bitrix_id = task.bitrix_id
    if not bitrix_id:
        return JsonResponse({"error": "У задачи отсутствует bitrix_id"}, status=409)

    if task.is_timer_running:
        task.pause_timer()                # локально
        change_task_status(bitrix_id, 2)  # Bitrix pause
        task.status = compute_local_status(task)
        task.save(update_fields=['status'])
        action = "paused"
    else:
        # Стартуя новый таймер — останавливаем прочие таймеры этого сотрудника
        if task.employee_id:
            Task.objects.filter(
                employee_id=task.employee_id,
                is_timer_running=True
            ).exclude(id=task.id).update(is_timer_running=False)

        task.start_timer()                # локально
        task.status = compute_local_status(task)  # будет 'in_progress'
        task.save(update_fields=['status'])
        change_task_status(bitrix_id, 3)  # Bitrix start
        action = "started"

    return JsonResponse({
        "status": "success",
        "action": action,
        "time_spent": task.time_spent,
        "task_status": task.status,
        "task_id": task.id,
        "bitrix_id": bitrix_id,
    })

def compute_local_status(task) -> str:
    """
    Правила:
    - если completed / deferred / under_review — оставляем как есть
    - если запущен таймер ИЛИ уже есть списанное время — 'in_progress'
    - иначе — 'new' (для только что созданных) или 'pending' по ситуации
    """
    if task.status in ('completed', 'deferred', 'under_review'):
        return task.status
    if task.is_timer_running:
        return 'in_progress'
    if (task.time_spent or 0) > 0:
        return 'in_progress'
    # если хочешь, можешь вернуть 'pending' вместо 'new'
    return 'new'

def change_task_status(bitrix_task_id: int, task_status: int) -> JsonResponse:
    """
    bitrix_task_id — внешний идентификатор родительской задачи в Bitrix (общий для всех наших сплитов).
    task_status — целевой статус для вызова Bitrix API.
    """
    available_statuses = {
        2: "tasks.task.pause",
        3: "tasks.task.start",
        5: "tasks.task.complete",
        6: "tasks.task.defer",
    }
    method = available_statuses.get(task_status)
    if method is None:
        return JsonResponse({"status": "error", "message": "Неверный статус для таски!"}, status=400)

    # локальная «родительская группа» — все сплиты с данным bitrix_id
    group_qs = Task.objects.filter(bitrix_id=bitrix_task_id)

    if not group_qs.exists():
        return JsonResponse({"status": "error", "message": "Задачи с таким bitrix_id не найдены"}, status=404)

    # вызов Bitrix
    resp = requests.post(url=f"{WEBHOOK_URL}{method}", json={"taskId": bitrix_task_id}, timeout=3)
    if resp.status_code != 200:
        return JsonResponse({"status": "error", "message": "Bitrix24 вернул ошибку"}, status=502)

    # опционально — локально синхронизируем «групповой» статус:
    new_local_status = map_bitrix_status(task_status)
    # group_qs.update(status=new_local_status)

    return JsonResponse({"status": "success", "message": "Статус в Bitrix обновлён"})


def change_time(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST allowed'}, status=405)

    try:
        task_id = int(request.POST.get("task_id"))
        time_minutes = int(request.POST.get("time"))
    except (TypeError, ValueError):
        return JsonResponse({'status': 'error', 'message': 'Invalid parameters'}, status=400)

    try:
        task = Task.objects.get(id=task_id)
    except Task.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Task not found'}, status=404)

    # ✅ БЭКЛОГ: просто обновляем время и шлём change с '0000-00-00'
    if task.employee_id is None and task.date is None:
        task.original_time_estimate = time_minutes * 60
        task.save (update_fields=['original_time_estimate'])
        return JsonResponse ({
            'status': 'success',
            'data': {
                'add': {},
                'change': {task.id: {'time': int (task.original_time_estimate), 'date': '0000-00-00'}},
                'delete': []
            }
        }, status=200)

    task.original_time_estimate = time_minutes * 60
    task.save(update_fields=['original_time_estimate'])

    employee_id = task.employee.bitrix_id if task.employee else 0
    date = task.date or datetime.today ().date ()

    result = autosplit (task.id, employee_id, date, seed_mode='change')
    return JsonResponse ({'status': 'success', 'data': result}, status=200)


from django.db import transaction

from django.db import transaction

def split_task(request):
    """
    Сплит по правилам:
    - time(min) <= исходное → исходная уменьшается (CHANGE), создаётся вторая на time → autosplit (ADD)
    - time(min) >  исходное → исходная без изменений (CHANGE с теми же значениями), создаётся вторая на time → autosplit (ADD)
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST allowed'}, status=405)

    try:
        task_id = int(request.POST.get("task_id"))
        minutes = int(request.POST.get("time"))
    except (TypeError, ValueError):
        return JsonResponse({'status': 'error', 'message': 'Invalid parameters'}, status=400)

    if minutes < 0:
        return JsonResponse({'status': 'error', 'message': 'time must be non-negative minutes'}, status=400)

    try:
        base = Task.objects.select_related('employee', 'creator').get(id=task_id)
    except Task.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Task not found'}, status=404)

    date_str = request.POST.get ("date")
    if date_str:
        try:
            start_date = datetime.strptime (date_str, "%Y-%m-%d").date ()
        except ValueError:
            start_date = base.date or datetime.today ().date ()
    else:
        start_date = base.date or datetime.today ().date ()

    split_seconds = minutes * 60

    patch = {'add': {}, 'change': {}, 'delete': []}

    is_backlog = (base.employee_id is None and base.date is None)
    if is_backlog:
        with transaction.atomic():
            if split_seconds <= int(base.original_time_estimate):
                new_time = int(base.original_time_estimate) - split_seconds
                if new_time != int(base.original_time_estimate):
                    base.original_time_estimate = new_time
                    base.save(update_fields=['original_time_estimate'])

            # исходная всегда как change (в бэклог)
            patch['change'][base.id] = {
                'time': int(base.original_time_estimate),
                'date': '0000-00-00',
            }

            # новая часть — тоже в бэклог
            new_task = Task.objects.create(
                bitrix_id=base.bitrix_id,
                title=base.title,
                description=base.description,
                creator=base.creator,
                employee=None,
                date=None,
                status='pending',
                original_time_estimate=split_seconds,
                is_timer_running=False,
                last_start_time=None,
            )
            patch['add'][new_task.id] = {
                'time': split_seconds,
                'date': '0000-00-00',
                'title': base.title,
            }

        return JsonResponse({'status': 'success', 'message': 'Задача разделена', 'data': patch}, status=200)

    user_id = base.employee.bitrix_id if base.employee else 0
    with transaction.atomic():
        # 1) исходная часть — уменьшаем, если надо
        if split_seconds <= int(base.original_time_estimate):
            new_time = int(base.original_time_estimate) - split_seconds
            if new_time != int(base.original_time_estimate):
                base.original_time_estimate = new_time
                base.save(update_fields=['original_time_estimate'])
        # CHANGE для исходной — всегда (в т.ч. если не изменилось)
        patch['change'][base.id] = {
            'time': int(base.original_time_estimate),
            'date': (base.date or start_date).strftime('%Y-%m-%d')
        }

        # 2) вторая задача на split_seconds (может быть и 0 — ок)
        new_task = Task.objects.create(
            bitrix_id=base.bitrix_id,
            title=base.title,
            description=base.description,
            creator=base.creator,
            employee=base.employee,
            date=start_date,
            status=base.status if base.status in ('new', 'pending', 'in_progress') else 'pending',
            original_time_estimate=split_seconds,
            is_timer_running=False,
            last_start_time=None,
        )

        # 3) autosplit для второй — seed_mode='add', чтобы фронт получил именно ADD
        res_new = autosplit(new_task.id, user_id, start_date, seed_mode='add')
        # сливаем
        if res_new:
            patch['add'].update(res_new.get('add', {}))
            patch['change'].update(res_new.get('change', {}))

    return JsonResponse({'status': 'success', 'message': 'Задача разделена', 'data': patch}, status=200)

def load_calendar(request):
    if request.method != 'POST':
        return JsonResponse ({'status': 'error', 'message': 'Only POST allowed'}, status=405)

    try:
        date = request.POST.get ("date")
        if not date:
            return JsonResponse ({'status': 'error', 'message': 'Date parameter is required'}, status=400)

        # Преобразуем полученную дату
        current_date = datetime.strptime (date, "%Y-%m-%d").date ()
        # Названия месяцев на русском
        months_ru = [
            "январь", "февраль", "март", "апрель", "май", "июнь",
            "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"
        ]
        current_month_name = months_ru[current_date.month - 1]

        # Названия дней недели на русском
        weekdays_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

        # Определяем границы периода (текущая дата +14 дней)
        first_day = current_date + timedelta(days=1)
        last_day = current_date + timedelta (days=15)

        print(first_day, last_day)
        # Получаем все задачи для периода
        tasks_in_period = Task.objects.filter (
            date__gte=first_day,
            date__lte=last_day
        ).select_related ('employee')

        # Формируем структуру данных для календаря
        days_data = {}
        gap = 0
        current_day = None

        while first_day + timedelta (days=gap) <= last_day:
            day = first_day + timedelta (days=gap)
            weekday_number = day.weekday ()

            # Пропускаем выходные
            if weekday_number < 5:
                search_date = day
                found_tasks = tasks_in_period.filter (date=search_date)
                tasks = {}

                # Текущий день
                if day == current_date:
                    current_day = gap

                # Группируем задачи по исполнителям
                for task in found_tasks:
                    if task.employee:
                        if task.employee.bitrix_id not in tasks:
                            tasks[task.employee.bitrix_id] = [{'title': task.title, 'time': task.original_time_estimate, 'employee_id': task.employee.bitrix_id, 'task_id': task.id, 'accumulated_time': task.time_spent, 'bitrix_id': task.bitrix_id}]
                        else:
                            tasks[task.employee.bitrix_id].append ({'title': task.title, 'time': task.original_time_estimate, 'employee_id': task.employee.bitrix_id, 'task_id': task.id, 'accumulated_time': task.time_spent, 'bitrix_id': task.bitrix_id})

                # Добавляем день в результат
                print(day)
                days_data[gap + 1] = {
                    "week_day": f"{day.day} {weekdays_ru[weekday_number]}",
                    "tasks": tasks,
                    "full_date": f"{day.year}-{day.month:02d}-{day.day:02d}"
                }
            gap += 1

        # Форматированный вывод текущей даты (например, "15 мая")
        day_and_month = f"{current_date.day} {current_month_name}"

        return JsonResponse ({
            "status": "success",
            "data": {
                "current_month": current_date.month,
                "current_year": current_date.year,
                "current_month_name": current_month_name.capitalize (),
                "days_in_month": days_data,
                "current_day": current_day,
                "day_and_month": day_and_month
            }
        })

    except ValueError:
        return JsonResponse ({'status': 'error', 'message': 'Invalid date format. Use YYYY-MM-DD'}, status=400)
    except Exception as e:
        return JsonResponse ({'status': 'error', 'message': str (e)}, status=500)

@require_POST
def submit_for_review(request):
    """
    Исполнитель отправляет задачу на проверку:
    - Bitrix: tasks.task.complete (если включен контроль — задача станет 'Awaiting control')
    - Локально: останавливаем таймеры по группе, помечаем все сплиты как 'under_review'
    """
    try:
        local_id = int(request.POST.get('task_id'))
    except (TypeError, ValueError):
        return JsonResponse({'status': 'error', 'message': 'Invalid task_id'}, status=400)

    try:
        t = Task.objects.get(id=local_id)
    except Task.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Task not found'}, status=404)

    if not t.bitrix_id:
        return JsonResponse({'status': 'error', 'message': 'Task has no bitrix_id'}, status=409)

    bitrix_id = int(t.bitrix_id)

    # Внешний вызов (3с таймаут)
    resp = requests.post(f"{WEBHOOK_URL}tasks.task.complete", json={"taskId": bitrix_id}, timeout=3)
    if resp.status_code != 200:
        return JsonResponse({'status': 'error', 'message': 'Bitrix24 error on complete'}, status=502)

    # Локально: останавливаем таймеры и помечаем «на проверке»
    group = Task.objects.filter(bitrix_id=bitrix_id)
    group.update(is_timer_running=False, status='under_review')

    affected_ids = list(group.values_list('id', flat=True))
    return JsonResponse({
        'status': 'success',
        'message': 'Задача отправлена на проверку',
        'data': {'group_ids': affected_ids, 'bitrix_id': bitrix_id, 'status': 'under_review'}
    })

def task_delegate(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST allowed'}, status=405)

    METHOD = "tasks.task.delegate"
    bitrix_request = None
    bitrix_response = None

    try:

        task_id_raw = request.POST.get("task_id")
        user_id_raw = request.POST.get("user_id")      # Bitrix USER_ID; 0 = backlog
        date_str = request.POST.get("date")            # YYYY-MM-DD (обязателен, если user_id != 0)

        try:
            task_id = int(task_id_raw)
            user_id = int(user_id_raw)
        except (TypeError, ValueError):
            return JsonResponse({'status': 'error', 'message': 'Invalid task_id or user_id'}, status=400)

        try:
            t = Task.objects.select_related('employee').get(id=task_id)
        except Task.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Task not found'}, status=404)

        if not t.bitrix_id:
            return JsonResponse({'status': 'error', 'message': 'Task has no bitrix_id'}, status=409)

        # целевой исполнитель/дата
        target_employee = None
        if user_id != 0:
            target_employee = Employee.objects.filter(bitrix_id=user_id).first()
            if not target_employee:
                return JsonResponse({'status': 'error', 'message': 'Employee not found'}, status=404)
            if not date_str:
                return JsonResponse({'status': 'error', 'message': 'date is required when user_id != 0'}, status=400)
            try:
                target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                return JsonResponse({'status': 'error', 'message': 'Invalid date format. Use YYYY-MM-DD'}, status=400)
        else:
            target_date = None  # backlog

        # если ничего не меняется — выходим
        same_assignee = (
                (t.employee is None and user_id == 0) or
                (t.employee and target_employee and t.employee_id == target_employee.id)
        )
        if same_assignee and (target_date is None or t.date == target_date):
            return JsonResponse({'status': 'success', 'message': 'No changes needed', 'data': {}}, status=200)

        # ❷ ПЕРЕНОС МЕЖДУ ДНЯМИ ТОГО ЖЕ СОТРУДНИКА → НЕТ МЕРДЖА, НЕТ BITRIX.DELEGATE
        if user_id != 0 and t.employee and target_employee and t.employee_id == target_employee.id:
            # Просто разложим ЭТУ задачу по дням, учитывая лимит (остальные сплиты не трогаем)
            with transaction.atomic():
                returned_data = autosplit(t.id, user_id, target_date, seed_mode='change') or {
                    'add': {}, 'change': {}, 'delete': []
                }
            return JsonResponse({
                'status': 'success',
                'message': 'Дата для задачи изменена',
                'data': returned_data,
                'bitrix': {'request': None, 'response': None}  # исполнителя не меняли — в Bitrix не звоним
            }, status=200)

        # --- ❸ ИНАЧЕ: БЭКЛОГ ИЛИ СМЕНА ИСПОЛНИТЕЛЯ ---
        with transaction.atomic ():
            group = Task.objects.filter (bitrix_id=t.bitrix_id).order_by ('id')

            if user_id == 0:
                # --- BACKLOG ---
                # Берём/создаём holder (employee/date = NULL) ДО удаления
                holder = group.filter (employee__isnull=True, date__isnull=True).first ()
                if not holder:
                    holder = Task.objects.create (
                        bitrix_id=t.bitrix_id,
                        title=t.title,
                        description=t.description or "",
                        creator=t.creator,
                        employee=None,
                        date=None,
                        status='pending',
                        original_time_estimate=0,
                        is_timer_running=False,
                        last_start_time=None,
                        deadline=t.deadline,
                        created_at=t.created_at,
                    )

                # Сумма времени по всей группе (пока все ещё на месте)
                total = int (sum (st.original_time_estimate for st in group))
                holder.original_time_estimate = total
                holder.employee = None
                holder.date = None
                holder.save (update_fields=['original_time_estimate', 'employee', 'date'])

                # ФИКСИРУЕМ СПИСОК К УДАЛЕНИЮ ДО удаления
                deleted_ids = list (group.exclude (id=holder.id).values_list ('id', flat=True))
                if deleted_ids:
                    Task.objects.filter (id__in=deleted_ids).delete ()

                # Патч: add holder, delete остальное
                returned_data = {
                    'add': {
                        str (holder.id): {
                            'time': int (holder.original_time_estimate),
                            'date': '0000-00-00',
                            'title': holder.title,
                        }
                    },
                    'change': {},
                    'delete': deleted_ids,
                }
                delegate_to = BACKLOG_USER_ID

            else:
                # --- НАЗНАЧЕНИЕ ПОЛЬЗОВАТЕЛЮ ---
                main = group.first ()  # консолидируем в первую
                total = int (sum (st.original_time_estimate for st in group))

                # обновим main
                main.original_time_estimate = total
                main.employee = target_employee
                main.date = target_date
                main.save (update_fields=['original_time_estimate', 'employee', 'date'])

                # удалить ВСЕ старые сплиты, кроме main (ФИКСИРУЕМ ids ДО удаления)
                deleted_ids = list (group.exclude (id=main.id).values_list ('id', flat=True))
                if deleted_ids:
                    Task.objects.filter (id__in=deleted_ids).delete ()

                # новое распределение → только ADD; плюс сообщаем delete старых
                returned_data = autosplit (main.id, user_id, target_date, seed_mode='add') or {'add': {}, 'change': {},
                                                                                               'delete': []}
                returned_data['delete'] = list (set (returned_data.get ('delete', [])) | set (deleted_ids))

                delegate_to = user_id

            # --- ВЫЗОВ BITRIX ДЛЯ ОБЕИХ ВЕТОК ---
            bitrix_request = {'taskId': int (t.bitrix_id), 'userId': int (delegate_to)}
            resp = requests.post (f"{WEBHOOK_URL}{METHOD}", json=bitrix_request, timeout=3)
            bitrix_response = {'status_code': resp.status_code, 'text': resp.text[:1000]}
            ok_http = (resp.status_code == 200)
            try:
                resp_json = resp.json ()
            except Exception:
                resp_json = {}
            if not ok_http or ('error' in resp_json):
                err_code = resp_json.get ('error') if isinstance (resp_json, dict) else None
                err_msg = resp_json.get ('error_description') if isinstance (resp_json, dict) else None
                raise RuntimeError (f"Bitrix error: code={err_code} message={err_msg or resp.text[:500]}")

        # --- 3) успех
        return JsonResponse({
            'status': 'success',
            'message': 'Исполнитель был изменен',
            'data': returned_data,
            'bitrix': {'request': bitrix_request, 'response': bitrix_response}
        }, status=200)

    except Exception as e:
        import traceback
        return JsonResponse({
            'status': 'error',
            'message': 'Произошла ошибка при изменении исполнителя',
            'error': str(e),
            'trace': traceback.format_exc(),
            'bitrix_request': bitrix_request,
            'bitrix_response': bitrix_response
        }, status=500)


MAX_DAILY_TIME = 28800  # 8 часов в секундах

def autosplit(task_id, user_id, date, seed_mode: str = 'change'):
    """
    Раскладывает задачу по рабочим дням с суточным лимитом.
    Возвращает patch:
      {'add': {<id>:{time,title,date}}, 'change': {<id>:{time,date}}, 'delete': []}

    seed_mode:
      - 'change' — для базовой задачи вернём change (перетаскивание / change_time)
      - 'add'    — для базовой задачи вернём add (split_task / task_delegate)
    Новые созданные куски ВСЕГДА идут как add.
    """
    patch = {'add': {}, 'change': {}, 'delete': []}

    try:
        task = Task.objects.get(id=task_id)
    except Task.DoesNotExist:
        return patch

    # переносим на ближайший рабочий день
    while date.weekday() >= 5:
        date += timedelta(days=1)

    # занятость дня (без самой задачи)
    tasks_on_date = Task.objects.filter(
        date=date, employee__bitrix_id=user_id
    ).exclude(id=task_id)
    busy = sum(
        t.original_time_estimate
        for t in tasks_on_date
        if t.status not in ['completed', 'deleted']
    )
    remaining = MAX_DAILY_TIME - busy

    def put_result(mode: str, t: Task, time_val: int, d: datetime.date):
        payload = {'time': int(time_val), 'date': d.strftime('%Y-%m-%d')}
        if mode == 'add':
            payload['title'] = t.title
            patch['add'][t.id] = payload
        else:
            patch['change'][t.id] = payload

    # 1) Всё влезает сегодня → просто ставим дату и возвращаем seed_mode для базовой
    if task.original_time_estimate <= remaining:
        if task.date != date:
            task.date = date
            task.save(update_fields=['date'])
        put_result(seed_mode, task, task.original_time_estimate, date)
        return patch

    # 2) День забит → переносим дату дальше, seed остаётся текущей задачей
    if remaining <= 0:
        next_date = date + timedelta(days=1)
        if task.date != next_date:
            task.date = next_date
            task.save(update_fields=['date'])
        put_result(seed_mode, task, task.original_time_estimate, next_date)
        # продолжаем раскладку дальше (seed остаётся change/add как заданно)
        sub = autosplit(task.id, user_id, next_date, seed_mode=seed_mode)
        if sub:
            patch['add'].update(sub.get('add', {}))
            # избегаем дублирования собственного id в change, если seed_mode='add'
            for k, v in (sub.get('change') or {}).items():
                if seed_mode == 'add' and k == task.id:
                    # если дочерний вызов вернул change по seed — конвертировать в add
                    v2 = {'time': v['time'], 'date': v['date'], 'title': task.title}
                    patch['add'][k] = v2
                else:
                    patch['change'][k] = v
        return patch

    # 3) Помещается только часть → текущей карточке даём piece, остаток — новыми add
    place_now = remaining
    remainder = int(task.original_time_estimate) - place_now

    # обновим текущую
    task.original_time_estimate = place_now
    task.date = date
    task.save(update_fields=['original_time_estimate', 'date'])

    put_result(seed_mode, task, place_now, date)

    # создаём новый кусок на остаток (это НОВАЯ задача → всегда как add)
    new_task = Task.objects.create(
        bitrix_id=task.bitrix_id,
        title=task.title,
        description=task.description,
        creator=task.creator,
        employee=task.employee,
        date=date + timedelta(days=1),  # будет уточнено рекурсией
        created_at=task.created_at,
        deadline=task.deadline,
        status='new',  # pending
        original_time_estimate=remainder,
        is_timer_running=False,
        last_start_time=None,
    )

    # разложим остаток, причём для new_task seed_mode ВСЕГДА 'add'
    sub = autosplit(new_task.id, user_id, new_task.date, seed_mode='add')
    if sub:
        patch['add'].update(sub.get('add', {}))
        patch['change'].update(sub.get('change', {}))

    return patch


def map_bitrix_status(bitrix_status: int) -> str:
    """Преобразует статус Bitrix24 в наш формат"""
    available_statuses = {
        "2":  "tasks.task.pause", # Переводит в статус "ждет выполнения"
        "3":  "tasks.task.start", # Переводит в статус "выполняется"
        # "4":  "", # Ожидает контроля
        "5":  "tasks.task.complete", # Переводит в статус "завершена"
        "6":  "tasks.task.defer" # Переводит в статус "отложена"
    } # По умолчанию 2

    status_map = {
        2: 'pending',  # Ждет выполнения (по умолчанию)
        3: 'in_progress',  # Выполняется
        4: 'pending',  # Ожидает контроля
        5: 'completed',  # Завершена
        6: 'deferred',  # Отложена
    }
    return status_map.get (bitrix_status, 'new')

def return_employee(user):
    # 1) Если есть OneToOne — используем её
    emp = getattr(user, 'employee', None)
    if emp:
        return emp

    # 2) Фолбэк по email (если он задан)
    email = (user.email or '').strip()
    if email:
        emp = Employee.objects.filter(email__iexact=email).first()
        if emp:
            # Автопривязка, чтобы в следующий раз работало через user.employee
            if not emp.user_id:
                emp.user = user
                emp.save(update_fields=['user'])
            return emp

    # 3) Ничего не нашли — возвращаем None (шаблон/вьюха должны это терпеть)
    return None


def get_timers(user):
    try:
        tasks = Task.objects.filter (
            status='in_progress',
            is_timer_running=True
        )

        active_tasks = [[task.id, task.time_spent] for task in tasks]
        print(active_tasks)

        employee = Employee.objects.get (email=user.email)
        self_timer = list (Task.objects.filter (
            employee=employee,
            status='in_progress',
            is_timer_running=True
        ).values_list ('id', flat=True))
        return {
            'all': list (active_tasks),
            'self': self_timer,
            'status': 'success'
        }

    except ObjectDoesNotExist:
        return {
            'all': list (active_tasks) if 'active_tasks' in locals () else [],
            'self': [],
            'status': 'employee_not_found'
        }
    except Exception as e:
        return {
            'all': [],
            'self': [],
            'status': 'error',
            'message': str (e)
        }

def logout_view(request):
    logout(request)
    return redirect('login')

@login_required
def index(request):
    user_list = Employee.objects.all()

    return render(request,'tasks/index.html', {
        'waiting_tasks': get_lists(),
        'calendar': calendar_view(),
        'users': user_list,
        'timers': json.dumps(get_timers(request.user)),
        'employee': return_employee(request.user)
    })

def login_page(request):
    """
    Логин по email ИЛИ username + пароль.
    Поле формы может называться 'login', 'email' или 'username'.
    """
    if request.method == 'POST':
        identifier = (request.POST.get('login')
                      or request.POST.get('email')
                      or request.POST.get('username') or '').strip()
        password = (request.POST.get('password') or '').strip()

        print(identifier, password)

        if not identifier or not password:
            return render(request, 'tasks/login.html', {'error': 'Введите логин и пароль'})

        # 1) Пробуем как username
        user = authenticate(request, username=identifier, password=password)

        # 2) Если не вышло — пробуем как email
        if not user:
            u = User.objects.filter(email__iexact=identifier).first()
            if u:
                user = authenticate(request, username=u.username, password=password)

        if user:
            login(request, user)
            return redirect('index')

        return render(request, 'tasks/login.html', {'error': 'Неверный логин или пароль'})

    return render(request, 'tasks/login.html')
