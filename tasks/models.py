from django.db import models, transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Q, Index, UniqueConstraint
import secrets, string

User = get_user_model()

def _gen_password(length: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

class Employee(models.Model):
    bitrix_id = models.PositiveIntegerField(unique=True, db_index=True, verbose_name="ID в Bitrix24")
    # Хранить пароль здесь небезопасно; используем только для одноразовой установки и чистим
    password = models.CharField(
        max_length=30, verbose_name="Пароль", blank=True, null=True,
        help_text="Используется один раз для установки пароля User и затем очищается."
    )
    name = models.CharField(max_length=100, verbose_name="Имя сотрудника", unique=True)
    email = models.EmailField(unique=True, verbose_name="Email", blank=True, null=True, db_index=True)
    icon = models.URLField(max_length=500, blank=True, null=True, verbose_name="Фото профиля")
    user = models.OneToOneField (
        User, on_delete=models.CASCADE, null=True, blank=True,
        related_name='employee', verbose_name="Пользователь Django"
    )

    def __str__(self):
        return self.name

    def get_linked_user(self):
        """Возвращает связанного пользователя, при отсутствии — ищет по email."""
        return self.user or User.objects.filter(email=self.email).first()

    def save(self, *args, **kwargs):
        creating = self.pk is None

        # Если создаём и пароль не задан — генерируем и сохраняем в модели (видимый в админке)
        if creating and not self.password:
            self.password = _gen_password (10)

        super ().save (*args, **kwargs)  # сначала сохранить Employee, чтобы был pk

        # Создать/привязать Django User и синхронизировать имя/email/пароль
        with transaction.atomic ():
            user = self.user
            if not user:
                # Пытаемся найти по email
                if self.email:
                    user = User.objects.filter (email=self.email).first ()

                # Если не нашли — создаём
                if not user:
                    base_username = f"bx{self.bitrix_id}" if self.bitrix_id else (self.name or "user")
                    username = base_username[:150]
                    i = 1
                    while User.objects.filter (username=username).exists ():
                        suffix = str (i)
                        username = (base_username[:150 - len (suffix)] + suffix)
                        i += 1

                    user = User.objects.create (
                        username=username,
                        email=self.email or "",
                        first_name=self.name or "",
                        is_staff=False,
                        is_superuser=False,
                    )

                # Привязать
                if not self.user_id:
                    self.user = user
                    super ().save (update_fields=["user"])

            # Обновить имя/email
            fields_to_update = []
            if self.name and user.first_name != self.name:
                user.first_name = self.name
                fields_to_update.append ("first_name")
            if self.email is not None and user.email != (self.email or ""):
                user.email = self.email or ""
                fields_to_update.append ("email")

            # Если пароль в Employee указан — применить его в User (хранится хеш)
            if self.password:
                user.set_password (self.password)
                fields_to_update.append ("password")

            if fields_to_update:
                user.save (update_fields=fields_to_update)

class TaskStatus(models.TextChoices):
    NEW = 'new', 'Новая'                # 1
    IN_PROGRESS = 'in_progress', 'В работе'  # 3
    PENDING = 'pending', 'На паузе'     # 2
    COMPLETED = 'completed', 'Завершена'  # 5
    DELETED = 'deleted', 'Удалена'
    DEFERRED = 'deferred', 'Отложена'   # 6


class Task(models.Model):
    bitrix_id = models.PositiveIntegerField(verbose_name="ID в Bitrix24", null=True, blank=True, db_index=True)
    title = models.CharField(max_length=255, verbose_name="Название")
    description = models.TextField(blank=True, null=True, verbose_name="Описание")

    creator = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, blank=True, null=True,
        related_name='created_tasks', verbose_name="Создатель"
    )
    employee = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, blank=True, null=True,
        related_name='assigned_tasks', verbose_name="Исполнитель"
    )

    date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")
    deadline = models.DateTimeField(blank=True, null=True, verbose_name="Срок выполнения", db_index=True)

    status = models.CharField(
        max_length=20, choices=TaskStatus.choices,
        default=TaskStatus.NEW, verbose_name="Статус", db_index=True
    )

    original_time_estimate = models.PositiveIntegerField(
        default=0, verbose_name="План (секунды)"
    )
    is_timer_running = models.BooleanField(default=False, verbose_name="Таймер запущен")
    last_start_time = models.DateTimeField(null=True, blank=True, verbose_name="Последний запуск таймера")
    accumulated_time = models.PositiveIntegerField(default=0, verbose_name="Накопленное время (сек)")

    @property
    def time_spent(self) -> int:
        """Общее затраченное время, учитывая текущую сессию."""
        if self.is_timer_running and self.last_start_time:
            seconds_since_start = int((timezone.now() - self.last_start_time).total_seconds())
            return self.accumulated_time + max(0, seconds_since_start)
        return self.accumulated_time

    def start_timer(self):
        if not self.is_timer_running:
            self.is_timer_running = True
            self.last_start_time = timezone.now()
            self.status = TaskStatus.IN_PROGRESS
            self.save(update_fields=['is_timer_running', 'last_start_time', 'status'])

    def pause_timer(self):
        if self.is_timer_running:
            now = timezone.now()
            elapsed = int((now - self.last_start_time).total_seconds())
            self.accumulated_time += max(0, elapsed)
            self.is_timer_running = False
            self.last_start_time = None
            self.status = TaskStatus.PENDING
            self.save(update_fields=['accumulated_time', 'is_timer_running', 'last_start_time', 'status'])

    def stop_timer(self):
        if self.is_timer_running:
            self.pause_timer()
        self.status = TaskStatus.COMPLETED
        self.save(update_fields=['status'])

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "Задача"
        verbose_name_plural = "Задачи"
        ordering = ['-created_at']
        indexes = [
            Index(fields=['bitrix_id']),
            Index(fields=['status']),
            Index(fields=['employee', 'status']),
            Index(fields=['deadline']),
            Index(fields=['-created_at']),
        ]
        constraints = [
        ]


class TaskReassignment(models.Model):
    task = models.ForeignKey(
        Task, on_delete=models.CASCADE,
        related_name='reassignments', verbose_name="Задача"
    )
    old_assignee = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True,
        related_name='old_reassignments', verbose_name="Предыдущий исполнитель"
    )
    new_assignee = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True,
        related_name='new_reassignments', verbose_name="Новый исполнитель"
    )
    reassigned_by = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True,
        related_name='initiated_reassignments', verbose_name="Кто переназначил"
    )
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Время изменения")
    comment = models.TextField(blank=True, null=True, verbose_name="Комментарий")

    class Meta:
        verbose_name = "Переназначение задачи"
        verbose_name_plural = "Переназначения задач"
        indexes = [
            Index(fields=['task', 'timestamp']),
        ]


class SyncLog(models.Model):
    ACTION_CHOICES = [
        ('create', 'Создание'),
        ('update', 'Обновление'),
        ('delete', 'Удаление'),
        ('error', 'Ошибка'),
    ]

    action = models.CharField(max_length=10, choices=ACTION_CHOICES, verbose_name="Действие", db_index=True)
    model_name = models.CharField(max_length=50, verbose_name="Модель", db_index=True)
    bitrix_id = models.PositiveIntegerField(null=True, verbose_name="ID в Bitrix24", db_index=True)
    details = models.TextField(blank=True, null=True, verbose_name="Детали")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Время события", db_index=True)
    is_success = models.BooleanField(default=False, verbose_name="Успешно")

    class Meta:
        verbose_name = "Лог синхронизации"
        verbose_name_plural = "Логи синхронизации"
        indexes = [
            Index(fields=['model_name', 'bitrix_id']),
            Index(fields=['timestamp']),
        ]

from django.utils.text import slugify
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=Employee)
def ensure_user_for_employee(sender, instance: Employee, created: bool, **kwargs):
    """
    При создании Employee автоматически создаёт/привязывает Django User.
    По умолчанию: не staff и не superuser.
    Также поддерживает последующие изменения имени/email.
    """
    # 1) Только что создан — убедимся, что есть связанный User
    if created and not instance.user:
        # если есть User с таким email — привяжем его
        user = None
        if instance.email:
            user = User.objects.filter(email=instance.email).first()

        if not user:
            # сгенерируем уникальный username
            base = f"bx{instance.bitrix_id}" if instance.bitrix_id else slugify(instance.name) or "user"
            username = base[:150]
            i = 1
            while User.objects.filter(username=username).exists():
                suffix = str(i)
                username = (base[:150-len(suffix)] + suffix)
                i += 1

            user = User(username=username, email=instance.email or "", first_name=instance.name)
            # пароля пока нет — заставим установить позже
            user.set_unusable_password()
            user.is_staff = False
            user.is_superuser = False
            user.save()

        # привяжем к сотруднику
        instance.user = user
        instance.save(update_fields=["user"])

    # 2) На обновлениях синхронизируем имя/email в связанном User
    elif instance.user:
        fields = []
        if instance.email and instance.user.email != instance.email:
            instance.user.email = instance.email
            fields.append("email")
        if instance.user.first_name != instance.name:
            instance.user.first_name = instance.name
            fields.append("first_name")
        # не меняем is_staff/is_superuser — это вручную в админке
        if fields:
            instance.user.save(update_fields=fields)

