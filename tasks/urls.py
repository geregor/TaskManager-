from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('login', views.login_page, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('api/delegate/', views.task_delegate, name='task delegate'),
    path('api/split-task/', views.split_task, name='split task'),
    path('api/task-start/', views.start_task, name='task started'),
    path('api/change-time/', views.change_time, name='change time'),
    path('api/load-calendary/', views.load_calendar, name='load calendary'),
    path('api/submit-review/', views.submit_for_review, name='submit_for_review'),
    path('api/review-decision/', views.review_decision, name='review_decision'),
]