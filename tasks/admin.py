from django.contrib import admin, messages
from unfold.admin import ModelAdmin
from .models import Task, Employee, _gen_password  # Импортируем ваши модели

# Создаем классы администратора для каждой модели
class TaskAdmin(ModelAdmin):
    list_display = ('id', 'title', 'status', 'created_at')  # Поля для отображения в списке
    list_filter = ('status',)  # Фильтры
    search_fields = ('title', 'description')  # Поля для поиска

from django.contrib.auth import get_user_model
User = get_user_model()

class EmployeeAdmin(ModelAdmin):
    list_display = ("id", "name", "email", "bitrix_id", "user", "password")
    search_fields = ("name", "email")
    fields = ("name", "email", "bitrix_id", "password", "user", "icon")
    readonly_fields = ("user",)

    actions = ["generate_new_password"]

    @admin.action(description="Сгенерировать новый пароль и применить")
    def generate_new_password(self, request, queryset):
        updated = 0
        for e in queryset:
            e.password = _gen_password(10)
            self.save_model(request, e, form=None, change=bool(e.pk))  # применим к User тоже
            updated += 1
        self.message_user(request, f"Сгенерированы новые пароли: {updated}", level=messages.SUCCESS)

    def save_model(self, request, obj, form, change):
        """Синхронизация Employee → User: создание, имя/email, пароль."""
        creating = obj.pk is None

        # Если создаём и пароль не указан — сгенерируем и покажем админу
        if creating and not obj.password:
            obj.password = _gen_password(10)

        # Сохраняем Employee сначала (чтобы был pk)
        super().save_model(request, obj, form, change)

        # 1) Гарантируем наличие User
        if not obj.user:
            # username: bx<ID> или slug имени; обеспечим уникальность
            base = f"bx{obj.bitrix_id}" if obj.bitrix_id else (obj.name or "user")
            username = base[:150]
            i = 1
            while User.objects.filter(username=username).exists():
                suffix = str(i)
                username = (base[:150 - len(suffix)] + suffix)
                i += 1

            user = User(
                username=username,
                email=obj.email or "",
                first_name=obj.name or "",
                is_staff=False,
                is_superuser=False,
            )
            # Пароль берём из Employee (или уже сгенерённый)
            user.set_password(obj.password or _gen_password(10))
            user.save()
            obj.user = user
            super().save_model(request, obj, form, change)  # обновим связь

            self.message_user(
                request,
                f"Создан User {user.username}. Пароль: {obj.password}",
                level=messages.SUCCESS
            )
        else:
            # 2) Обновляем имя/email
            fields = []
            if obj.name and obj.user.first_name != obj.name:
                obj.user.first_name = obj.name; fields.append("first_name")
            if obj.email is not None and obj.user.email != (obj.email or ""):
                obj.user.email = obj.email or ""; fields.append("email")

            # 3) Если пароль в форме изменили — применим его к User
            if (form and 'password' in form.changed_data and obj.password) or (not form and obj.password):
                obj.user.set_password(obj.password)
                fields.append("password")

            if fields:
                obj.user.save(update_fields=fields)
                if 'password' in fields:
                    self.message_user(request, "Пароль пользователя обновлён.", level=messages.SUCCESS)

# Регистрируем модели с их административными классами
admin.site.register(Task, TaskAdmin)
admin.site.register(Employee, EmployeeAdmin)

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.models import User, Group

from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm
from unfold.admin import ModelAdmin

admin.site.unregister(User)
admin.site.unregister(Group)

@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    # Forms loaded from `unfold.forms`
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass