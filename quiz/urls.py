from django.conf.urls import url

from . import secure_views

urlpatterns = [
    url(r'^$', secure_views.kp_tree, name='quiz_kp_tree'),
    url(r'^join/$', secure_views.join_banji, name='quiz_join_banji'),
    url(r'^kp2/(?P<kp2_id>\d+)/$', secure_views.answer_question, name='quiz_answer'),
    url(r'^kp2/(?P<kp2_id>\d+)/submit/$', secure_views.submit_answer, name='quiz_submit'),
    url(r'^points/$', secure_views.my_points, name='quiz_points'),
    url(r'^leaderboard/$', secure_views.leaderboard, name='quiz_leaderboard'),
    url(r'^teacher/class/(?P<banji_id>\d+)/$', secure_views.teacher_class_progress, name='quiz_teacher_class'),
    url(r'^teacher/class/(?P<banji_id>\d+)/code/$', secure_views.teacher_class_code_update, name='quiz_teacher_class_code'),
    url(r'^teacher/kp/$', secure_views.teacher_kp_manage, name='quiz_teacher_kp_manage'),
    url(r'^teacher/kp/(?P<kp2_id>\d+)/$', secure_views.teacher_kp_questions, name='quiz_teacher_kp_questions'),
]
